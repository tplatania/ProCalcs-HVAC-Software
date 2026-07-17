"""
usage_event.py — Adoption + learning-loop telemetry.

Day-25. Gerald's monitoring questions ("is Richard's team actually
using it, and is the app actually learning from them?") need events,
not vibes. One row per meaningful interaction:

    bom_generated        — a BOM run finished (detail: override_hits,
                           override_ids that auto-applied)
    chat_message         — a Review Assistant message was sent
                           (detail: snipes, attachments, actions_proposed)
    attachment_uploaded  — files staged into the chat
    override_saved       — a correction was written (price / SKU)
    proposal_applied     — a chat proposal was accepted into the BOM

Provenance discipline (same rule as the rules ledger): inputs from
test actors — Gerald and dev accounts, who are explicitly NOT HVAC
experts — are stored but tagged provenance='test' and excluded from
every adoption/impact metric. Configure via TEST_ACTOR_EMAILS
(comma-separated, case-insensitive; default covers Gerald + dev).

Storage: same Postgres/SQLAlchemy/Alembic stack as bom_runs. Writes
are best-effort — telemetry failures must never poison a BOM response
or a chat turn (callers wrap in try/except).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_JSONType = JSON().with_variant(JSONB(), "postgresql")

_DEFAULT_TEST_ACTORS = "gerald@procalcs.net,dev@procalcs.net,dev"


def test_actor_emails() -> set[str]:
    """Lowercased set of actor emails whose inputs are test-provenance.
    Env-driven so adding a QA account never needs a deploy of code."""
    raw = os.environ.get("TEST_ACTOR_EMAILS", _DEFAULT_TEST_ACTORS)
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def provenance_for(actor_email: Optional[str]) -> str:
    if actor_email and actor_email.strip().lower() in test_actor_emails():
        return "test"
    return "real"


class UsageEvent(db.Model):
    """One meaningful user interaction with the BOM tooling."""

    __tablename__ = "usage_events"

    id = db.Column(db.Integer, primary_key=True)

    created_at  = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)
    event       = db.Column(db.String(40),  nullable=False, index=True)
    actor_email = db.Column(db.String(255), nullable=True,  index=True)
    # 'real' | 'test' — test rows never count toward adoption/impact.
    provenance  = db.Column(db.String(8),   nullable=False, index=True, default="real")

    client_id = db.Column(db.String(100), nullable=True, index=True)
    job_id    = db.Column(db.String(255), nullable=True)
    run_id    = db.Column(db.Integer,     nullable=True, index=True)

    detail = db.Column(_JSONType, nullable=True)

    @classmethod
    def record(
        cls,
        *,
        event: str,
        actor_email: Optional[str] = None,
        client_id: Optional[str] = None,
        job_id: Optional[str] = None,
        run_id: Optional[int] = None,
        detail: Optional[dict[str, Any]] = None,
        commit: bool = True,
    ) -> "UsageEvent":
        row = cls(
            event=event,
            actor_email=actor_email,
            provenance=provenance_for(actor_email),
            client_id=client_id,
            job_id=job_id,
            run_id=run_id,
            detail=detail,
        )
        db.session.add(row)
        if commit:
            db.session.commit()
        return row

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "created_at":  self.created_at.isoformat() + "Z" if self.created_at else None,
            "event":       self.event,
            "actor_email": self.actor_email,
            "provenance":  self.provenance,
            "client_id":   self.client_id,
            "job_id":      self.job_id,
            "run_id":      self.run_id,
            "detail":      self.detail,
        }
