"""
discovered_mapping.py — Auto-learned Wrightsoft Src+Name mappings.

Day-12 catalog-coverage strategy. Every time a Wrightsoft .xls/.csv
flows through /from-wrightsoft, the builder upserts one row here for
each (supplier, sku) combo it saw. Over time the table fills with
real-world manufacturer catalogs (Goodman / Broan / Rheia / PGM / …)
WITHOUT us having to encode them by hand.

Read path: when the same SKU shows up on a future run, the builder
checks this table first. If we've seen it before with a verified
description + section, the line is upgraded from 'wrightsoft_passthrough'
to 'wrightsoft_discovered' — counted as catalog-resolved.

Cumulative effect: Goodman's catalog gradually maps itself as
contractors run real projects through the pipeline.

Schema is intentionally narrow — we're indexing what we've seen,
not pretending to be a price catalog. Pricing comes from the
contractor profile / supplier integrations elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DiscoveredMapping(db.Model):
    """One row per (supplier, sku) we've ever seen in a Wrightsoft BOM."""

    __tablename__ = "discovered_mappings"

    id = db.Column(db.Integer, primary_key=True)

    # The (supplier, sku) tuple is what makes this row unique. supplier
    # is the 4-char Wrightsoft Src code (GOOD, BROAN, RHEA, PGM, WSF…).
    supplier = db.Column(db.String(16), nullable=False, index=True)
    sku      = db.Column(db.String(128), nullable=False, index=True)

    # Last-seen description + section from the Wrightsoft export. Used to
    # enrich future lines that have the same SKU. Wrightsoft is fairly
    # consistent so most updates are no-ops; when descriptions diverge
    # we take the most recent one (last-writer-wins, simplest correct).
    description    = db.Column(db.String(512), nullable=True)
    section_hint   = db.Column(db.String(64), nullable=True)

    # Counters — how many distinct runs we've seen this SKU on, plus
    # the cumulative qty across all of them. Powers any future
    # "frequently used parts" surface for Richard's team.
    times_seen     = db.Column(db.Integer, nullable=False, default=1)
    total_quantity = db.Column(db.Float,   nullable=False, default=0.0)

    first_seen_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    last_seen_at  = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)

    # Optional — the run id that introduced this SKU. Convenient for
    # debugging "where did THIS come from?".
    first_seen_run_id = db.Column(db.Integer, nullable=True)
    last_seen_run_id  = db.Column(db.Integer, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("supplier", "sku", name="uq_discovered_supplier_sku"),
    )

    @classmethod
    def upsert_many(
        cls,
        seen: list[dict],
        *,
        run_id: int | None = None,
    ) -> int:
        """Upsert a batch of (supplier, sku, description, section_hint,
        quantity) tuples. Increments times_seen + total_quantity on
        existing rows, inserts new ones with times_seen=1.

        Best-effort — any DB error is swallowed (the caller still
        returns the BOM successfully). Returns how many distinct rows
        were touched (created or updated). Returns 0 if `seen` is empty.

        Caller must commit; this method only flushes its work into the
        current session so it can be batched alongside the bom_runs row.
        """
        if not seen:
            return 0
        now = _utcnow()
        touched = 0
        for entry in seen:
            supplier = (entry.get("supplier") or "").strip().upper()
            sku      = (entry.get("sku") or "").strip()
            if not supplier or not sku:
                continue
            qty = float(entry.get("quantity") or 0)
            existing = (
                db.session.query(cls)
                .filter_by(supplier=supplier, sku=sku)
                .one_or_none()
            )
            if existing is None:
                db.session.add(cls(
                    supplier=supplier,
                    sku=sku,
                    description=(entry.get("description") or None),
                    section_hint=(entry.get("section_hint") or None),
                    times_seen=1,
                    total_quantity=qty,
                    first_seen_at=now,
                    last_seen_at=now,
                    first_seen_run_id=run_id,
                    last_seen_run_id=run_id,
                ))
            else:
                existing.times_seen     = (existing.times_seen or 0) + 1
                existing.total_quantity = (existing.total_quantity or 0.0) + qty
                existing.last_seen_at   = now
                existing.last_seen_run_id = run_id
                # Last-writer-wins on description / section — Wrightsoft
                # is consistent enough that drift is rare; when it
                # happens we'd rather have the newer label.
                if entry.get("description"):
                    existing.description = entry["description"]
                if entry.get("section_hint"):
                    existing.section_hint = entry["section_hint"]
            touched += 1
        return touched

    @classmethod
    def lookup(cls, *, supplier: str, sku: str):
        """Single-row lookup for the read path. Returns the row or None."""
        if not supplier or not sku:
            return None
        return (
            db.session.query(cls)
            .filter_by(supplier=supplier.strip().upper(), sku=sku.strip())
            .one_or_none()
        )

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "supplier":        self.supplier,
            "sku":             self.sku,
            "description":     self.description,
            "section_hint":    self.section_hint,
            "times_seen":      self.times_seen,
            "total_quantity":  self.total_quantity,
            "first_seen_at":   self.first_seen_at.isoformat() + "Z" if self.first_seen_at else None,
            "last_seen_at":    self.last_seen_at.isoformat() + "Z" if self.last_seen_at else None,
            "first_seen_run_id": self.first_seen_run_id,
            "last_seen_run_id":  self.last_seen_run_id,
        }
