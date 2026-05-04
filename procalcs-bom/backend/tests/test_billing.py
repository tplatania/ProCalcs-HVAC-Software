"""
Tests for the billing layer added in Apr 30 2026 evening session.

Scope:
  - User model: tier defaulting, internal-domain auto-promotion, BOM
    counter rollover, can_generate_bom honoring tier caps + billing flag.
  - billing_routes: /config endpoint shape, /me + /checkout require user,
    webhook idempotency on duplicate event_id, basic checkout/portal flow
    via mocked Stripe SDK.

Stripe SDK is monkeypatched so these tests run without network or
secrets. Existing tests are unaffected — billing routes mount but
require BILLING_ENABLED + Stripe keys which aren't set in CI.
"""
from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Force in-memory SQLite + dummy required env BEFORE importing the app.
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('ANTHROPIC_API_KEY', 'dev-test')
os.environ.setdefault('FIRESTORE_PROJECT_ID', 'dev-test')
os.environ.setdefault('SERVICE_SHARED_SECRET', '')
os.environ.setdefault('BILLING_ENABLED', 'true')
os.environ.setdefault('INTERNAL_DOMAIN', 'procalcs.net')

from app import create_app
from extensions import db
from models import User, SubscriptionEvent
from config import Config, TIER_LIMITS, plan_to_tier


# ─── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRIPE_SECRET_KEY'] = 'sk_test_dummy'
    app.config['STRIPE_PUBLISHABLE_KEY'] = 'pk_test_dummy'
    app.config['STRIPE_WEBHOOK_SECRET'] = 'whsec_dummy'
    app.config['STRIPE_PRICES'] = {
        'starter_monthly': 'price_starter_m',
        'starter_yearly':  'price_starter_y',
        'pro_monthly':     'price_pro_m',
        'pro_yearly':      'price_pro_y',
    }
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _user_headers(email: str, name: str = "Test User") -> dict:
    return {
        'X-Procalcs-User-Email': email,
        'X-Procalcs-User-Name': name,
    }


# ─── User model ─────────────────────────────────────────────────────

class TestUserModel:

    def test_upsert_creates_trial_user_for_external_email(self, app):
        u = User.upsert_from_email('contractor@example.com', name='Contractor')
        assert u.id is not None
        assert u.subscription_tier == 'trial'
        assert u.subscription_status == 'trialing'
        assert u.trial_ends_at is not None
        assert u.trial_ends_at > datetime.utcnow()
        assert u.name == 'Contractor'

    def test_upsert_creates_internal_user_for_procalcs_email(self, app):
        u = User.upsert_from_email('gerald@procalcs.net')
        assert u.subscription_tier == 'internal'
        assert u.subscription_status == 'internal'
        assert u.trial_ends_at is None

    def test_upsert_is_idempotent(self, app):
        a = User.upsert_from_email('same@example.com', name='First')
        b = User.upsert_from_email('same@example.com', name='Updated')
        assert a.id == b.id
        assert b.name == 'Updated'  # name updates on second call

    def test_can_generate_bom_unlimited_for_internal(self, app):
        u = User.upsert_from_email('gerald@procalcs.net')
        u.bom_count_monthly = 10_000
        assert u.can_generate_bom() is True

    def test_can_generate_bom_honors_trial_cap(self, app):
        u = User.upsert_from_email('limited@example.com')
        cap = TIER_LIMITS['trial']['bom_limit']
        u.bom_count_monthly = cap - 1
        assert u.can_generate_bom() is True
        u.bom_count_monthly = cap
        assert u.can_generate_bom() is False

    def test_can_generate_bom_open_when_billing_disabled(self, app):
        with patch.object(Config, 'BILLING_ENABLED', False):
            u = User.upsert_from_email('anyone@example.com')
            u.subscription_tier = 'trial'
            u.bom_count_monthly = 999_999
            assert u.can_generate_bom() is True

    def test_record_bom_increments_total_and_monthly(self, app):
        u = User.upsert_from_email('contractor@example.com')
        u.record_bom_generated()
        u.record_bom_generated()
        assert u.bom_count_total == 2
        assert u.bom_count_monthly == 2  # trial uses monthly bucket

    def test_record_bom_skips_monthly_for_internal(self, app):
        u = User.upsert_from_email('gerald@procalcs.net')
        u.record_bom_generated()
        assert u.bom_count_total == 1
        assert u.bom_count_monthly == 0  # internal doesn't track monthly

    def test_reset_monthly_zeroes_counter_and_stamps_date(self, app):
        u = User.upsert_from_email('contractor@example.com')
        u.bom_count_monthly = 50
        u.reset_monthly_counts()
        assert u.bom_count_monthly == 0
        assert u.last_reset_date is not None

    def test_safety_net_resets_after_30_days(self, app):
        u = User.upsert_from_email('contractor@example.com')
        u.subscription_tier = 'starter'
        u.bom_count_monthly = 50
        u.last_reset_date = datetime.utcnow() - timedelta(days=31)
        # Triggered indirectly via can_generate_bom
        u.can_generate_bom()
        assert u.bom_count_monthly == 0

    def test_to_dict_omits_sensitive_by_default(self, app):
        u = User.upsert_from_email('contractor@example.com')
        u.stripe_customer_id = 'cus_test'
        d = u.to_dict()
        assert 'stripe_customer_id' not in d
        d2 = u.to_dict(include_sensitive=True)
        assert d2['stripe_customer_id'] == 'cus_test'


# ─── plan_to_tier helper ────────────────────────────────────────────

class TestPlanToTier:
    def test_extracts_tier_from_plan_key(self):
        assert plan_to_tier('starter_monthly') == 'starter'
        assert plan_to_tier('starter_yearly')  == 'starter'
        assert plan_to_tier('pro_monthly')     == 'pro'
        assert plan_to_tier('pro_yearly')      == 'pro'

    def test_handles_empty_or_unknown(self):
        assert plan_to_tier('') == 'trial'
        assert plan_to_tier(None) == 'trial'


# ─── Billing routes ─────────────────────────────────────────────────

class TestBillingConfigRoute:
    def test_returns_publishable_key_and_tier_table(self, client):
        r = client.get('/api/v1/billing/config')
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert body['data']['publishable_key'] == 'pk_test_dummy'
        assert body['data']['billing_enabled'] is True
        assert 'trial' in body['data']['tiers']
        assert 'pro' in body['data']['tiers']


class TestBillingMeRoute:
    def test_requires_user_header(self, client):
        r = client.get('/api/v1/billing/me')
        assert r.status_code == 401

    def test_returns_user_billing_snapshot(self, client):
        r = client.get('/api/v1/billing/me', headers=_user_headers('a@example.com'))
        assert r.status_code == 200
        body = r.get_json()
        assert body['data']['email'] == 'a@example.com'
        assert body['data']['subscription_tier'] == 'trial'
        assert body['data']['boms_remaining'] == TIER_LIMITS['trial']['bom_limit']

    def test_internal_account_gets_unlimited(self, client):
        r = client.get('/api/v1/billing/me', headers=_user_headers('gerald@procalcs.net'))
        body = r.get_json()
        assert body['data']['subscription_tier'] == 'internal'
        assert body['data']['boms_remaining'] == -1


class TestCheckoutRoute:
    def test_rejects_unknown_plan(self, client):
        r = client.post(
            '/api/v1/billing/checkout',
            headers=_user_headers('a@example.com'),
            json={'plan': 'mystery'},
        )
        assert r.status_code == 400
        assert 'Unknown' in r.get_json()['error']

    def test_internal_users_cannot_checkout(self, client):
        r = client.post(
            '/api/v1/billing/checkout',
            headers=_user_headers('gerald@procalcs.net'),
            json={'plan': 'starter_monthly'},
        )
        assert r.status_code == 400
        assert 'Internal' in r.get_json()['error']

    def test_creates_customer_and_session(self, client, app):
        with patch('routes.billing_routes.stripe') as mock_stripe:
            mock_stripe.api_key = ''  # _ensure_stripe_configured will set it
            mock_stripe.Customer.create.return_value = MagicMock(id='cus_new')
            mock_stripe.checkout.Session.create.return_value = MagicMock(
                id='cs_test', url='https://checkout.stripe.com/test',
            )
            mock_stripe.error = MagicMock()
            mock_stripe.error.StripeError = type('StripeError', (Exception,), {})

            r = client.post(
                '/api/v1/billing/checkout',
                headers=_user_headers('newcontractor@example.com'),
                json={
                    'plan': 'starter_monthly',
                    'success_url': 'http://test/ok',
                    'cancel_url':  'http://test/cancel',
                },
            )
            assert r.status_code == 200, r.get_data(as_text=True)
            body = r.get_json()
            assert body['data']['session_id'] == 'cs_test'
            assert body['data']['url'] == 'https://checkout.stripe.com/test'

            # Verify customer was created with the right metadata
            mock_stripe.Customer.create.assert_called_once()
            call_kwargs = mock_stripe.Customer.create.call_args.kwargs
            assert call_kwargs['email'] == 'newcontractor@example.com'

            # User record should now have the customer ID cached
            with app.app_context():
                u = User.query.filter_by(email='newcontractor@example.com').first()
                assert u.stripe_customer_id == 'cus_new'


# ─── Webhook ─────────────────────────────────────────────────────────

class TestWebhookIdempotency:
    def test_duplicate_event_id_acks_without_reprocessing(self, client, app):
        # Pre-record an event ID — simulates Stripe redelivery.
        with app.app_context():
            db.session.add(SubscriptionEvent(
                stripe_event_id='evt_already_seen',
                event_type='checkout.session.completed',
                summary='already processed',
            ))
            db.session.commit()

        with patch('routes.billing_routes.stripe') as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = {
                'id': 'evt_already_seen',
                'type': 'checkout.session.completed',
                'data': {'object': {}},
            }
            mock_stripe.error = MagicMock()
            r = client.post(
                '/api/v1/billing/webhook',
                data='{}',
                headers={'Stripe-Signature': 'sig'},
            )
            assert r.status_code == 200
            assert r.get_json()['status'] == 'duplicate'


class TestWebhookHandlers:

    def _post_event(self, client, event_payload):
        """Send a Stripe-shaped event through the webhook with mocked SDK."""
        with patch('routes.billing_routes.stripe') as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = event_payload
            mock_stripe.error = MagicMock()
            r = client.post(
                '/api/v1/billing/webhook',
                data='{}',
                headers={'Stripe-Signature': 'sig'},
            )
            return r

    def test_checkout_completed_grants_subscription(self, client, app):
        with app.app_context():
            u = User.upsert_from_email('upgrader@example.com')
            uid = u.id

        r = self._post_event(client, {
            'id': 'evt_chk_1',
            'type': 'checkout.session.completed',
            'data': {'object': {
                'metadata': {'procalcs_user_id': str(uid), 'tier': 'starter', 'plan': 'starter_monthly'},
                'subscription': 'sub_test',
                'customer': 'cus_test',
            }},
        })
        assert r.status_code == 200, r.get_data(as_text=True)

        with app.app_context():
            u = User.query.get(uid)
            assert u.subscription_tier == 'starter'
            assert u.stripe_subscription_id == 'sub_test'
            assert u.subscription_status == 'active'
            assert u.bom_count_monthly == 0  # reset on grant

    def test_invoice_paid_resets_monthly_counter(self, client, app):
        with app.app_context():
            u = User.upsert_from_email('payer@example.com')
            u.subscription_tier = 'starter'
            u.stripe_customer_id = 'cus_payer'
            u.bom_count_monthly = 17
            db.session.commit()
            uid = u.id

        r = self._post_event(client, {
            'id': 'evt_inv_1',
            'type': 'invoice.paid',
            'data': {'object': {'customer': 'cus_payer'}},
        })
        assert r.status_code == 200

        with app.app_context():
            u = User.query.get(uid)
            assert u.bom_count_monthly == 0

    def test_subscription_deleted_downgrades_to_trial(self, client, app):
        with app.app_context():
            u = User.upsert_from_email('canceler@example.com')
            u.subscription_tier = 'pro'
            u.stripe_customer_id = 'cus_canceler'
            u.stripe_subscription_id = 'sub_canceler'
            db.session.commit()
            uid = u.id

        r = self._post_event(client, {
            'id': 'evt_sub_del_1',
            'type': 'customer.subscription.deleted',
            'data': {'object': {'customer': 'cus_canceler', 'metadata': {'procalcs_user_id': str(uid)}}},
        })
        assert r.status_code == 200

        with app.app_context():
            u = User.query.get(uid)
            assert u.subscription_tier == 'trial'
            assert u.subscription_status == 'canceled'
            assert u.stripe_subscription_id is None
