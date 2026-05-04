"""
user.py — Persistent user record for billing + usage tracking.

Distinct from the OAuth identity in designer-desktop's signed cookie:
that cookie carries email/name/picture for UI purposes; this row
carries everything billing needs to make a decision (tier, Stripe IDs,
usage counts).

JIT-provisioned: the first authenticated request from a new email
creates the row via `User.upsert_from_email`. Internal accounts
(@procalcs.net by default; configurable via INTERNAL_DOMAIN) get
tier='internal' automatically and never go through Stripe.

Adapted from Ask-Your-HVAC-Pro's user.py — stripped of homeowner-
specific fields (user_type, voice, response_detail) and re-fit for
ProCalcs Designer's BOM-counting metric. No password column because
auth still happens upstream in designer-desktop via Google OAuth.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from extensions import db
from config import TIER_LIMITS, Config


def _utcnow() -> datetime:
    """Naive UTC datetime — SQLAlchemy + SQLite handle naive better."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    """One row per authenticated identity. Created on first request."""

    __tablename__ = "users"

    id    = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name  = db.Column(db.String(255), nullable=True)

    # Billing
    subscription_tier      = db.Column(db.String(20), default='trial', nullable=False)
    stripe_customer_id     = db.Column(db.String(100), nullable=True, index=True)
    stripe_subscription_id = db.Column(db.String(100), nullable=True, index=True)

    # Subscription state mirror — populated from webhooks. The Stripe API
    # is the source of truth; this is the local cache for read paths that
    # don't want to round-trip Stripe on every request.
    subscription_status   = db.Column(db.String(20), nullable=True)  # active|past_due|canceled|trialing|...
    trial_ends_at         = db.Column(db.DateTime, nullable=True)
    current_period_end    = db.Column(db.DateTime, nullable=True)
    cancel_at_period_end  = db.Column(db.Boolean, default=False, nullable=False)

    # Usage tracking — ProCalcs counts BOMs, not questions.
    bom_count_total   = db.Column(db.Integer, default=0, nullable=False)  # lifetime
    bom_count_monthly = db.Column(db.Integer, default=0, nullable=False)  # current period
    last_reset_date   = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def upsert_from_email(cls, email: str, name: Optional[str] = None) -> "User":
        """Find or create the user record for an authenticated email.

        Called from middleware on every authenticated request. Bumps
        last_login on existing rows. New rows for the configured
        internal domain (e.g. @procalcs.net) get tier='internal'
        automatically and skip the trial.
        """
        email = (email or "").strip().lower()
        if not email:
            raise ValueError("upsert_from_email: empty email")

        user = cls.query.filter_by(email=email).first()
        if user is None:
            internal = email.endswith("@" + Config.INTERNAL_DOMAIN.lower())
            user = cls(
                email                = email,
                name                 = name,
                subscription_tier    = 'internal' if internal else 'trial',
                trial_ends_at        = None if internal else _trial_end(),
                subscription_status  = 'internal' if internal else 'trialing',
                last_login           = _utcnow(),
            )
            db.session.add(user)
            db.session.commit()
        else:
            user.last_login = _utcnow()
            if name and user.name != name:
                user.name = name
            db.session.commit()
        return user

    # ------------------------------------------------------------------
    # Tier / usage decisions
    # ------------------------------------------------------------------

    def tier_config(self) -> dict:
        """Resolve the tier dict, falling back to trial if unknown."""
        return TIER_LIMITS.get(self.subscription_tier, TIER_LIMITS['trial'])

    def can_generate_bom(self) -> bool:
        """Master gate for the /generate endpoint. Honors:
            - billing disabled (always True — internal MVP mode)
            - internal tier (always True)
            - tier-specific monthly cap (honors -1 = unlimited)
        Triggers a 30-day usage reset if the last_reset_date is stale.
        """
        if not Config.BILLING_ENABLED:
            return True
        if self.subscription_tier == 'internal':
            return True
        # Cancelled subscriptions still get access until period end.
        if self.subscription_status == 'canceled' and not self.cancel_at_period_end:
            return False
        self._maybe_reset_monthly()
        cap = self.tier_config().get('bom_limit', 0)
        if cap == -1:
            return True
        return self.bom_count_monthly < cap

    def boms_remaining(self) -> int:
        """For UI display. -1 sentinel for unlimited tiers."""
        cap = self.tier_config().get('bom_limit', 0)
        if cap == -1:
            return -1
        self._maybe_reset_monthly()
        return max(0, cap - self.bom_count_monthly)

    def record_bom_generated(self) -> None:
        """Bump counters after a successful /generate. Caller commits."""
        self.bom_count_total += 1
        if self.subscription_tier not in ('internal', 'trial'):
            self.bom_count_monthly += 1
        elif self.subscription_tier == 'trial':
            # Trial uses monthly bucket too — the cap is the trial allowance.
            self.bom_count_monthly += 1

    def reset_monthly_counts(self) -> None:
        """Called by Stripe invoice.paid webhook on the billing cycle."""
        self.bom_count_monthly = 0
        self.last_reset_date   = _utcnow()

    def _maybe_reset_monthly(self) -> None:
        """30-day safety net for missed invoice.paid webhooks. Mirrors
        Ask-Your-HVAC-Pro's check_and_reset_monthly pattern."""
        if self.subscription_tier == 'internal':
            return
        now = _utcnow()
        if self.last_reset_date is None:
            self.last_reset_date = now
            return
        if (now - self.last_reset_date).days >= 30:
            self.reset_monthly_counts()

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self, include_sensitive: bool = False) -> dict:
        cfg = self.tier_config()
        out = {
            "id":                 self.id,
            "email":              self.email,
            "name":               self.name,
            "subscription_tier":  self.subscription_tier,
            "tier_label":         cfg.get('label', self.subscription_tier),
            "subscription_status": self.subscription_status,
            "trial_ends_at":      self.trial_ends_at.isoformat() if self.trial_ends_at else None,
            "current_period_end": self.current_period_end.isoformat() if self.current_period_end else None,
            "cancel_at_period_end": self.cancel_at_period_end,
            "bom_count_total":    self.bom_count_total,
            "bom_count_monthly":  self.bom_count_monthly,
            "bom_limit":          cfg.get('bom_limit', 0),
            "boms_remaining":     self.boms_remaining(),
            "features":           cfg.get('features', []),
            "created_at":         self.created_at.isoformat() if self.created_at else None,
            "last_login":         self.last_login.isoformat() if self.last_login else None,
        }
        if include_sensitive:
            out["stripe_customer_id"]     = self.stripe_customer_id
            out["stripe_subscription_id"] = self.stripe_subscription_id
        return out

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.subscription_tier})>"


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _trial_end() -> datetime:
    """Compute trial expiry for new signups: now + TRIAL_DAYS."""
    from datetime import timedelta
    return _utcnow() + timedelta(days=Config.TRIAL_DAYS)
