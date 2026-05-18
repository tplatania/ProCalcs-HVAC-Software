"""
bom_comparison.py — Persistent record of every sample-BOM comparison.

Created Day-2 (May 2026) of the harness rollout. Every successful call
to POST /api/v1/bom-runs/<id>/compare writes one row here BEFORE
returning. Two reasons:

  1. Audit trail — testers can re-open a sample-BOM result without
     re-uploading the spreadsheet.
  2. Backlog generation — aggregating `missing_skus` across all rows
     (grouped by SKU) gives Richard's team a prioritized list of
     "what to encode next in the catalog" sorted by demand.

Storage: same SQLAlchemy stack as bom_runs / users / subscription_events
(Phase 3 + the Cloud SQL Connector wiring from Phase 4 prep). One row
per comparison; we don't dedupe re-uploads of the same sample for the
same run — the audit value is in seeing every attempt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_JSONType = JSON().with_variant(JSONB(), "postgresql")


class BomComparison(db.Model):
    """One row per /compare call. Append-only."""

    __tablename__ = "bom_comparisons"

    id = db.Column(db.Integer, primary_key=True)

    # When + which run + who uploaded the sample
    created_at      = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)
    created_by_email = db.Column(db.String(255), nullable=True, index=True)

    bom_run_id = db.Column(
        db.Integer,
        db.ForeignKey("bom_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Provenance of the sample BOM — the .xls filename (or "(pasted)"
    # when JSON body was used).
    sample_filename = db.Column(db.String(255), nullable=True)

    # Full metrics roll-up from ComparisonReport.metrics.to_dict().
    # Stored as JSONB so we can add fields later without a migration.
    metrics = db.Column(_JSONType, nullable=False, default=dict)

    # Missing SKUs — the list that drives the backlog aggregation.
    # Stored as a list of {"sku": "...", "description": "...", "qty": N}
    # so we can group by SKU AND surface description+qty without
    # re-running compare. Lowercase SKU for case-insensitive grouping.
    missing_skus = db.Column(_JSONType, nullable=False, default=list)

    # ─── Lifecycle ─────────────────────────────────────────────────

    @classmethod
    def record(
        cls,
        *,
        bom_run_id: int,
        sample_filename: Optional[str],
        report_dict: dict[str, Any],
        created_by_email: Optional[str] = None,
    ) -> "BomComparison":
        """Persist a /compare result. Caller commits the session.

        Extracts the metrics + missing-SKU subset from the full report
        dict so the row stays compact (the per-line outcomes can be
        re-derived by re-running compare on the live run; the missing
        list is the unique-to-this-snapshot data we need to preserve)."""
        missing = []
        for line in (report_dict.get("lines") or []):
            if line.get("status") != "missing":
                continue
            sku = (line.get("sku") or "").strip()
            missing.append({
                "sku":         sku.lower() if sku else None,
                "sku_display": sku or None,
                "description": (line.get("description") or "").strip() or None,
                "qty":         line.get("sample_qty"),
            })
        row = cls(
            bom_run_id      = bom_run_id,
            sample_filename = sample_filename,
            metrics         = report_dict.get("metrics") or {},
            missing_skus    = missing,
            created_by_email= created_by_email,
        )
        db.session.add(row)
        db.session.flush()
        return row

    # ─── Serialization ────────────────────────────────────────────

    def to_summary(self) -> dict[str, Any]:
        return {
            "id":               self.id,
            "bom_run_id":       self.bom_run_id,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
            "created_by_email": self.created_by_email,
            "sample_filename":  self.sample_filename,
            "metrics":          self.metrics or {},
            "missing_count":    len(self.missing_skus or []),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_summary(),
            "missing_skus": self.missing_skus or [],
        }
