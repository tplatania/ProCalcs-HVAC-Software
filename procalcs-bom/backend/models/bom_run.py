"""
bom_run.py — Persistent record of every BOM generation.

Created May 2026 (Phase 3 of the testing-harness rollout). Every call
to bom_service.generate() writes one row here BEFORE returning the
response. Lets Richard:
  - Find a BOM he generated yesterday
  - Mark it good / needs_fix / blocked with notes
  - Regenerate with the same inputs (links to parent for diff)
  - Compare two runs side-by-side (Phase 6)
  - Compare a run against a contractor sample BOM (Phase 7)

Storage: Postgres via the same SQLAlchemy + Alembic stack the billing
layer added (extensions.db / migrations/). Persistence is sync —
the BOM service holds the DB write inside generate() before returning,
so the caller knows the run is recorded. Adds <50ms on a 15-second
generation, invisible to designers.

Privacy: no PII concerns since these are internal-tool runs from
procalcs.net designers against their own contractor projects. Raw
RUP bytes ARE stored so we can re-parse if the parser changes
(deferred — sourced from rup file system today). Raw bytes column
deliberately not added in this first cut to keep row size small;
we'll add it when re-parsing becomes a feature.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from extensions import db


def _utcnow() -> datetime:
    """Naive UTC datetime — matches the rest of the schema (User, etc.)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# JSONB on Postgres, plain JSON on SQLite (tests). The columns hold the
# parsed design_data and the full BOM response — JSONB lets us index/
# query into them later if we want to (e.g., "find all runs where the
# parser caught zero equipment").
_JSONType = JSON().with_variant(JSONB(), "postgresql")


# Reviewer status enum — kept as a string column instead of a Postgres
# enum so adding statuses later doesn't require a migration. The set
# below is the canonical taxonomy; rejecting unknown values is the
# route layer's job, not the DB's.
REVIEWER_STATUSES = ("unset", "good", "needs_fix", "blocked")


class BomRun(db.Model):
    """One row per BOM generation. Append-only by design — edits go
    through reviewer_status / reviewer_notes / tags only."""

    __tablename__ = "bom_runs"

    id = db.Column(db.Integer, primary_key=True)

    # When + who
    created_at       = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)
    created_by_email = db.Column(db.String(255), nullable=True, index=True)

    # Source RUP — filename for display, no raw bytes stored yet
    source_rup_filename = db.Column(db.String(255), nullable=True)

    # Inputs to generate()
    client_id   = db.Column(db.String(100), nullable=False, index=True)
    job_id      = db.Column(db.String(255), nullable=False, index=True)
    output_mode = db.Column(db.String(50), nullable=True)

    # Full design_data JSON the parser produced. Lets us re-parse
    # downstream if needed and inspect what the AI saw.
    parsed_design_data = db.Column(_JSONType, nullable=True)

    # Full /generate response. Single source of truth for line items
    # + provenance (catalog_match_count, rules_engine_count, etc.).
    generated_bom = db.Column(_JSONType, nullable=True)

    # Performance + cost tracking. Anthropic timing in ms; tokens
    # populated when the SDK exposes them on the response object.
    anthropic_duration_ms     = db.Column(db.Integer, nullable=True)
    anthropic_input_tokens    = db.Column(db.Integer, nullable=True)
    anthropic_output_tokens   = db.Column(db.Integer, nullable=True)

    # Code provenance — git SHA at the time of generation. Lets us
    # answer "which BOMs were generated against the pre-Phase-2 prompt
    # vs the post-Phase-2 prompt" at scale.
    bom_service_revision = db.Column(db.String(40), nullable=True)

    # Reviewer state — the workflow Richard runs. Defaults to "unset"
    # so an un-reviewed run is distinguishable from a "good" one.
    reviewer_status = db.Column(db.String(20), default="unset", nullable=False, index=True)
    reviewer_notes  = db.Column(db.Text, nullable=True)
    reviewer_email  = db.Column(db.String(255), nullable=True)
    reviewed_at     = db.Column(db.DateTime, nullable=True)

    # Self-referential FK for regeneration chains (Phase 4). When set,
    # this run was triggered by clicking "Regenerate" on the parent.
    # Null = first generation for this RUP+contractor combination.
    regenerated_from_id = db.Column(
        db.Integer,
        db.ForeignKey("bom_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Loose grouping for Richard's regression-suite curation
    # (Phase 9). Postgres TEXT[] when on Postgres; JSON list elsewhere.
    tags = db.Column(_JSONType, nullable=True, default=list)

    # ─── Lifecycle helpers ─────────────────────────────────────────

    @classmethod
    def record(
        cls,
        *,
        client_id: str,
        job_id: str,
        output_mode: Optional[str],
        parsed_design_data: Optional[dict],
        generated_bom: Optional[dict],
        created_by_email: Optional[str] = None,
        source_rup_filename: Optional[str] = None,
        anthropic_duration_ms: Optional[int] = None,
        anthropic_input_tokens: Optional[int] = None,
        anthropic_output_tokens: Optional[int] = None,
        bom_service_revision: Optional[str] = None,
        regenerated_from_id: Optional[int] = None,
        tags: Optional[list[str]] = None,
    ) -> "BomRun":
        """Persist a generated BOM. Caller is responsible for committing
        the session — we use add+flush so the id is available before
        commit (lets the route layer return run_id in the response)."""
        run = cls(
            client_id=client_id,
            job_id=job_id,
            output_mode=output_mode,
            parsed_design_data=parsed_design_data,
            generated_bom=generated_bom,
            created_by_email=created_by_email,
            source_rup_filename=source_rup_filename,
            anthropic_duration_ms=anthropic_duration_ms,
            anthropic_input_tokens=anthropic_input_tokens,
            anthropic_output_tokens=anthropic_output_tokens,
            bom_service_revision=bom_service_revision,
            regenerated_from_id=regenerated_from_id,
            tags=tags or [],
        )
        db.session.add(run)
        db.session.flush()  # populate run.id without commit
        return run

    def review(
        self,
        *,
        status: str,
        notes: Optional[str] = None,
        email: Optional[str] = None,
    ) -> "BomRun":
        """Set reviewer state. Caller commits."""
        if status not in REVIEWER_STATUSES:
            raise ValueError(
                f"reviewer_status must be one of {REVIEWER_STATUSES}, got {status!r}"
            )
        self.reviewer_status = status
        if notes is not None:
            self.reviewer_notes = notes
        if email is not None:
            self.reviewer_email = email
        self.reviewed_at = _utcnow()
        return self

    # ─── Serialization ─────────────────────────────────────────────

    def to_summary(self) -> dict[str, Any]:
        """Compact dict for list views — drops the heavy JSONB columns
        so the run-history list page loads fast even with hundreds of
        rows. Use to_dict() for the detail view."""
        return {
            "id":                    self.id,
            "created_at":            self.created_at.isoformat() if self.created_at else None,
            "created_by_email":      self.created_by_email,
            "client_id":             self.client_id,
            "job_id":                self.job_id,
            "output_mode":           self.output_mode,
            "source_rup_filename":   self.source_rup_filename,
            "reviewer_status":       self.reviewer_status,
            "reviewer_email":        self.reviewer_email,
            "regenerated_from_id":   self.regenerated_from_id,
            "tags":                  self.tags or [],
            "anthropic_duration_ms": self.anthropic_duration_ms,
            "bom_service_revision":  self.bom_service_revision,
            # Just enough BOM signal for the list view to show a count
            # + total without paying the JSONB-decode cost on every row.
            "item_count":            (self.generated_bom or {}).get("item_count"),
            "total_price":           (self.generated_bom or {}).get("totals", {}).get("total_price"),
        }

    def to_dict(self) -> dict[str, Any]:
        """Full record for the detail view."""
        return {
            **self.to_summary(),
            "parsed_design_data":     self.parsed_design_data,
            "generated_bom":          self.generated_bom,
            "anthropic_input_tokens": self.anthropic_input_tokens,
            "anthropic_output_tokens": self.anthropic_output_tokens,
            "reviewer_notes":         self.reviewer_notes,
            "reviewed_at":            self.reviewed_at.isoformat() if self.reviewed_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<BomRun id={self.id} client_id={self.client_id!r} "
            f"job_id={self.job_id!r} status={self.reviewer_status}>"
        )
