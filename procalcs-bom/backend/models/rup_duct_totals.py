"""
rup_duct_totals.py — Day-14 Phase 4 cache for user-entered duct LF totals.

Why: re-uploading the same RUP shouldn't force the user to re-type the
Wrightsoft Supply Actual Ln numbers every time. Saving them by SHA-256
of the RUP bytes gives us per-file persistence shared across the team
(Richard + anyone else who runs the same project gets the totals back).

Schema is intentionally narrow — just (hash, blob, audit). The blob
is the same shape the SPA sends in design_data.duct_summary.known_lengths_ft:

    {
      "round_supply": {"4": 524.1, "6": 50.0, ...},
      "round_return": {"6": 80.0, ...},
      "rect_supply":  {"12x10": 350.0, ...},
      "rect_return":  {...},
    }
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def compute_rup_hash(rup_bytes: bytes) -> str:
    """SHA-256 of the raw RUP bytes — the cache key. 64 hex chars.
    Pulled into a helper so the /parse-rup endpoint, the upsert
    endpoint, and the tests all agree on the same digest."""
    return hashlib.sha256(rup_bytes).hexdigest()


_JSONType = JSON().with_variant(JSONB(), "postgresql")


class RupDuctTotals(db.Model):
    """One row per RUP file we've ever seen totals entered for."""

    __tablename__ = "rup_duct_totals"

    id = db.Column(db.Integer, primary_key=True)

    # SHA-256 of the .rup bytes. 64 hex chars — index for fast lookup.
    rup_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)

    # The full known_lengths_ft blob — stored verbatim so the SPA
    # round-trips its input shape without lossy normalization.
    known_lengths_ft = db.Column(_JSONType, nullable=False, default=dict)

    # Optional context for the run-history page
    source_filename = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)
    updated_by = db.Column(db.String(255), nullable=True)

    @classmethod
    def lookup(cls, rup_hash: str) -> Optional["RupDuctTotals"]:
        if not rup_hash:
            return None
        return (
            db.session.query(cls)
            .filter_by(rup_hash=rup_hash.strip().lower())
            .one_or_none()
        )

    @classmethod
    def upsert(
        cls,
        *,
        rup_hash: str,
        known_lengths_ft: dict,
        source_filename: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> "RupDuctTotals":
        """Insert or update the row for this hash. Commit is the
        caller's job — keeps this composable with endpoint-level
        transactions."""
        rup_hash = (rup_hash or "").strip().lower()
        if not rup_hash:
            raise ValueError("rup_hash is required")
        now = _utcnow()
        existing = cls.lookup(rup_hash)
        if existing is None:
            row = cls(
                rup_hash=rup_hash,
                known_lengths_ft=known_lengths_ft or {},
                source_filename=source_filename,
                created_at=now,
                updated_at=now,
                updated_by=updated_by,
            )
            db.session.add(row)
            return row
        existing.known_lengths_ft = known_lengths_ft or {}
        existing.updated_at = now
        if source_filename:
            existing.source_filename = source_filename
        if updated_by:
            existing.updated_by = updated_by
        return existing

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "rup_hash":         self.rup_hash,
            "known_lengths_ft": self.known_lengths_ft,
            "source_filename":  self.source_filename,
            "created_at":       self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at":       self.updated_at.isoformat() + "Z" if self.updated_at else None,
            "updated_by":       self.updated_by,
        }
