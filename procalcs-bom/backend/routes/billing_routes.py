"""
billing_routes.py — Stripe checkout, customer portal, and webhook handler.

Ported from Ask-Your-HVAC-Pro/backend/routes/stripe_routes.py and adapted
to:
  - The ProCalcs tier model (internal/trial/starter/pro/enterprise)
  - The user-from-header middleware (g.current_user vs JWT @login_required)
  - BOM-counted usage instead of question-counted

Mounted at /api/v1/billing in app.py:
    GET  /api/v1/billing/config             — returns publishable key + tier table
    GET  /api/v1/billing/me                 — current user + subscription summary
    POST /api/v1/billing/checkout           — open Stripe-hosted checkout
    POST /api/v1/billing/portal             — open Stripe customer portal
    POST /api/v1/billing/webhook            — Stripe → us, signature verified

Webhook is the only route that doesn't require g.current_user (Stripe
delivers it). All others require the X-Procalcs-User-Email header
upstream + valid SERVICE_SHARED_SECRET to even reach this handler.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import stripe
from flask import Blueprint, current_app, g, jsonify, request

from extensions import db
from models import User, SubscriptionEvent
from config import Config, TIER_LIMITS, plan_to_tier

logger = logging.getLogger('procalcs_bom.billing')

billing_bp = Blueprint('billing', __name__)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _ensure_stripe_configured():
    """Set the Stripe API key on demand (so importing this module
    doesn't fail when the secret is unset in dev). Returns True if
    Stripe is usable, False otherwise."""
    key = current_app.config.get('STRIPE_SECRET_KEY')
    if not key:
        return False
    if stripe.api_key != key:
        stripe.api_key = key
    return True


def _require_user():
    """Pull the current user from g, set by the user middleware in app.py.
    Returns (user, None) on success, (None, error_response) on failure."""
    user = getattr(g, 'current_user', None)
    if user is None:
        return None, (jsonify({
            "success": False,
            "data": None,
            "error": "X-Procalcs-User-Email header missing or unrecognized",
        }), 401)
    return user, None


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _from_unix(ts):
    """Stripe sends epoch seconds; we store naive UTC datetimes."""
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------

@billing_bp.route('/config', methods=['GET'])
def get_billing_config():
    """Public-ish: returns publishable key + the tier table for /pricing.

    Doesn't return Stripe price IDs to the frontend (those stay server-
    side and are only resolved at checkout). The frontend renders the
    pricing page from the TIER_LIMITS dict's `price_monthly`/`price_yearly`
    fields when Tom sets them.
    """
    return jsonify({
        "success": True,
        "data": {
            "publishable_key": current_app.config.get('STRIPE_PUBLISHABLE_KEY', ''),
            "billing_enabled": Config.BILLING_ENABLED,
            "trial_days":      Config.TRIAL_DAYS,
            "tiers":           TIER_LIMITS,
        },
        "error": None,
    })


@billing_bp.route('/me', methods=['GET'])
def get_current_user_billing():
    """Return the current user's billing snapshot. The SPA polls this
    after checkout success to refresh the UI without waiting for
    webhook propagation."""
    user, err = _require_user()
    if err:
        return err
    return jsonify({
        "success": True,
        "data": user.to_dict(include_sensitive=False),
        "error": None,
    })


@billing_bp.route('/checkout', methods=['POST'])
def create_checkout():
    """Open a Stripe-hosted Checkout session for the requested plan.

    Request body:
        { "plan": "starter_monthly" | "starter_yearly" | "pro_monthly" | "pro_yearly",
          "success_url": str, "cancel_url": str }
    """
    if not _ensure_stripe_configured():
        return jsonify({"success": False, "data": None,
                        "error": "Billing not configured on this deploy"}), 503

    user, err = _require_user()
    if err:
        return err

    if user.subscription_tier == 'internal':
        return jsonify({"success": False, "data": None,
                        "error": "Internal accounts don't go through billing"}), 400

    body = request.get_json(silent=True) or {}
    plan = body.get('plan')
    success_url = body.get('success_url') or f"{request.host_url.rstrip('/')}/billing?status=success"
    cancel_url  = body.get('cancel_url')  or f"{request.host_url.rstrip('/')}/billing?status=canceled"

    price_id = current_app.config.get('STRIPE_PRICES', {}).get(plan)
    if not price_id:
        return jsonify({"success": False, "data": None,
                        "error": f"Unknown or unconfigured plan: {plan}"}), 400

    # Lazily create the Stripe customer record. Stripe is the source of
    # truth for customer existence; we cache the ID on the User row.
    try:
        if not user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=user.email,
                metadata={'procalcs_user_id': user.id},
            )
            user.stripe_customer_id = customer.id
            db.session.commit()

        session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'procalcs_user_id': user.id,
                'plan':             plan,
                'tier':             plan_to_tier(plan),
            },
            # No CC needed during the trial (Phase 0 decision).
            subscription_data={'trial_period_days': Config.TRIAL_DAYS},
        )
        return jsonify({
            "success": True,
            "data": {"session_id": session.id, "url": session.url},
            "error": None,
        })
    except stripe.error.StripeError as e:
        logger.exception("Stripe checkout failed")
        return jsonify({"success": False, "data": None,
                        "error": f"Stripe: {e.user_message or str(e)}"}), 502
    except Exception as e:
        logger.exception("checkout failed (non-Stripe)")
        return jsonify({"success": False, "data": None, "error": str(e)}), 500


@billing_bp.route('/portal', methods=['POST'])
def create_portal():
    """Open the Stripe customer portal so the user can change/cancel
    their plan, update payment method, etc. — no UI for us to build."""
    if not _ensure_stripe_configured():
        return jsonify({"success": False, "data": None,
                        "error": "Billing not configured on this deploy"}), 503

    user, err = _require_user()
    if err:
        return err

    if not user.stripe_customer_id:
        return jsonify({"success": False, "data": None,
                        "error": "No Stripe customer record for this user yet"}), 404

    body = request.get_json(silent=True) or {}
    return_url = body.get('return_url') or f"{request.host_url.rstrip('/')}/billing"

    try:
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=return_url,
        )
        return jsonify({
            "success": True,
            "data": {"url": session.url},
            "error": None,
        })
    except stripe.error.StripeError as e:
        logger.exception("Stripe portal failed")
        return jsonify({"success": False, "data": None,
                        "error": f"Stripe: {e.user_message or str(e)}"}), 502


# ---------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------

@billing_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Receive Stripe events.

    Signature-verified via STRIPE_WEBHOOK_SECRET. Each accepted delivery
    is recorded in subscription_events for auditability and idempotency
    (we skip already-processed event IDs).

    Configured in the Stripe dashboard to send these event types:
      - checkout.session.completed       → grant initial subscription
      - customer.subscription.updated    → tier change / renewal
      - customer.subscription.deleted    → downgrade to trial-ended
      - invoice.paid                     → reset monthly BOM counter
      - invoice.payment_failed           → log + (future) email user
    """
    if not _ensure_stripe_configured():
        return jsonify({"error": "Billing not configured"}), 503

    secret = current_app.config.get('STRIPE_WEBHOOK_SECRET')
    if not secret:
        logger.error("STRIPE_WEBHOOK_SECRET unset — refusing to process webhook")
        return jsonify({"error": "Webhook signing not configured"}), 503

    payload   = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400

    event_id   = event.get('id')
    event_type = event.get('type')

    # Idempotency: if we've already seen this event_id, ack with 200
    # and don't re-process. Stripe will stop retrying.
    existing = SubscriptionEvent.query.filter_by(stripe_event_id=event_id).first()
    if existing:
        return jsonify({"status": "duplicate", "id": event_id})

    # Dispatch by event type. Each handler returns a (user, summary)
    # tuple for the audit row.
    handlers = {
        'checkout.session.completed':      _handle_checkout_completed,
        'customer.subscription.updated':   _handle_subscription_updated,
        'customer.subscription.deleted':   _handle_subscription_deleted,
        'invoice.paid':                    _handle_invoice_paid,
        'invoice.payment_failed':          _handle_payment_failed,
    }
    handler = handlers.get(event_type)
    user = None
    summary = None
    try:
        if handler:
            user, summary = handler(event['data']['object'])
        else:
            summary = f"unhandled event type: {event_type}"
    except Exception as e:
        # Record what we got even on failure so we can replay later.
        logger.exception("webhook handler crashed: %s", event_type)
        summary = f"handler error: {e}"

    audit = SubscriptionEvent(
        stripe_event_id        = event_id,
        event_type             = event_type,
        user_id                = user.id if user else None,
        stripe_customer_id     = (user.stripe_customer_id if user else
                                  event['data']['object'].get('customer')),
        stripe_subscription_id = (user.stripe_subscription_id if user else None),
        summary                = (summary or '')[:500],
        raw_payload            = json.dumps(event['data'], default=str)[:30000],
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify({"status": "ok", "id": event_id})


# ---------------------------------------------------------------------
# Webhook handlers
# ---------------------------------------------------------------------

def _user_from_session(obj):
    """Pull the procalcs user out of a checkout.session or subscription.
    Tries metadata first (set by us at checkout), falls back to customer
    lookup."""
    user_id = None
    metadata = obj.get('metadata') or {}
    if 'procalcs_user_id' in metadata:
        try:
            user_id = int(metadata['procalcs_user_id'])
        except (TypeError, ValueError):
            user_id = None
    if user_id:
        user = User.query.get(user_id)
        if user:
            return user
    # Fallback: lookup by stripe_customer_id
    customer_id = obj.get('customer')
    if customer_id:
        return User.query.filter_by(stripe_customer_id=customer_id).first()
    return None


def _handle_checkout_completed(session):
    """Initial subscription grant after Stripe-hosted checkout success."""
    user = _user_from_session(session)
    if not user:
        return None, "checkout.session.completed: no procalcs user found"

    metadata = session.get('metadata') or {}
    tier = metadata.get('tier') or 'starter'
    subscription_id = session.get('subscription')

    user.subscription_tier      = tier
    user.stripe_subscription_id = subscription_id
    user.subscription_status    = 'active'  # Stripe's actual status comes via subscription.updated
    user.bom_count_monthly      = 0
    user.last_reset_date        = _utcnow()
    db.session.commit()
    return user, f"granted tier={tier} subscription_id={subscription_id}"


def _handle_subscription_updated(subscription):
    """Tier change or renewal. Mirror current state from Stripe."""
    user = _user_from_session(subscription)
    if not user:
        return None, "customer.subscription.updated: no procalcs user found"

    user.subscription_status   = subscription.get('status')
    user.current_period_end    = _from_unix(subscription.get('current_period_end'))
    user.cancel_at_period_end  = bool(subscription.get('cancel_at_period_end'))
    db.session.commit()
    return user, (
        f"status={user.subscription_status} "
        f"cancel_at_period_end={user.cancel_at_period_end}"
    )


def _handle_subscription_deleted(subscription):
    """Subscription canceled (period ended after a cancel-at-period-end,
    or hard-canceled by support). Drop to trial-ended state."""
    user = _user_from_session(subscription)
    if not user:
        return None, "customer.subscription.deleted: no procalcs user found"

    user.subscription_tier      = 'trial'
    user.subscription_status    = 'canceled'
    user.stripe_subscription_id = None
    user.cancel_at_period_end   = False
    db.session.commit()
    return user, "downgraded to trial after subscription deletion"


def _handle_invoice_paid(invoice):
    """Successful billing-cycle payment — primary trigger for monthly
    BOM-counter reset. The 30-day safety net in User._maybe_reset_monthly
    catches missed deliveries."""
    user = _user_from_session(invoice)
    if not user:
        return None, "invoice.paid: no procalcs user found"
    if user.subscription_tier in ('internal', 'trial'):
        return user, "invoice.paid for non-paid tier (no-op)"

    user.reset_monthly_counts()
    db.session.commit()
    return user, f"monthly BOM counter reset (was at start of new cycle)"


def _handle_payment_failed(invoice):
    """Recurring payment failed. Log + (future) email user. Stripe will
    retry per its own retry policy; we don't downgrade until
    subscription.deleted fires."""
    user = _user_from_session(invoice)
    if not user:
        return None, "invoice.payment_failed: no procalcs user found"
    logger.warning("Payment failed for user %s (%s)", user.id, user.email)
    return user, "payment failed — Stripe will retry per its policy"
