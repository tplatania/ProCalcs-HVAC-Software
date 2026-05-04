"""
subscription_event.py — Append-only audit log of Stripe webhook events.

Every webhook the billing routes process gets one row here, regardless
of whether it changed any user state. Lets us answer "what did Stripe
tell us about user X over the last 30 days" without paging through
the Stripe dashboard.

Also serves as idempotency: if Stripe redelivers the same webhook
(network blip on their side), we look up by stripe_event_id and skip.
"""

from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SubscriptionEvent(db.Model):
    """One row per Stripe webhook delivery we accepted."""

    __tablename__ = "subscription_events"

    id               = db.Column(db.Integer, primary_key=True)
    stripe_event_id  = db.Column(db.String(80), unique=True, nullable=False, index=True)
    event_type       = db.Column(db.String(80), nullable=False, index=True)
    user_id          = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    stripe_customer_id     = db.Column(db.String(100), nullable=True, index=True)
    stripe_subscription_id = db.Column(db.String(100), nullable=True, index=True)

    # Compact summary of what changed — full payload kept in raw_payload
    # for any future audit need.
    summary      = db.Column(db.String(500), nullable=True)
    raw_payload  = db.Column(db.Text, nullable=True)

    received_at  = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<SubscriptionEvent {self.event_type} {self.stripe_event_id}>"
