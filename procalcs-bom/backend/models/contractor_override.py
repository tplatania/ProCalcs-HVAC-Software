"""
contractor_override.py — Per-contractor manual corrections on top of
the Wrightsoft pipeline.

Day-13. Closes the loop Tom keeps describing:

  "Everyone's pricing will be different… we'll get it directly from
   the client and put it in."

Each row is one correction Richard (or whoever) applied to a specific
(Src, Name) pair for a specific contractor. The builder consults this
table BEFORE discovered_mappings before falling back to passthrough,
so manual edits beat automatic discoveries beat raw Wrightsoft data.

Correction scope:
  - corrected_sku       — fix a wrong translation (Wrightsoft generic
                          ID → manufacturer SKU)
  - corrected_supplier  — sometimes the right SKU is from a different
                          supplier than what Wrightsoft picked
  - unit_price          — Tom's "we collect prices from each client
                          and put them in" workflow

What we explicitly do NOT carry: qty, description, section. Those
come from Wrightsoft and per Tom's "we use what Wrightsoft produced,
we don't recreate it" stance must not be overridden through this
table on Wrightsoft-sourced lines. AI-sourced lines (a separate
correction path) may carry more fields in a future feature.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ContractorOverride(db.Model):
    """One row per (contractor_id, supplier, sku) correction."""

    __tablename__ = "contractor_overrides"

    id = db.Column(db.Integer, primary_key=True)

    # Identity — which contractor, which Wrightsoft-emitted line.
    # The (Src, Name) tuple is what comes out of a Wrightsoft .xls;
    # contractor_id matches ClientProfile.client_id.
    contractor_id = db.Column(db.String(64),  nullable=False, index=True)
    supplier      = db.Column(db.String(16),  nullable=False, index=True)
    sku           = db.Column(db.String(128), nullable=False, index=True)

    # The correction. Any of these may be null when only one or two
    # fields are being overridden (e.g. price-only entry has
    # corrected_sku=null, corrected_supplier=null).
    corrected_sku      = db.Column(db.String(128), nullable=True)
    corrected_supplier = db.Column(db.String(16),  nullable=True)
    unit_price         = db.Column(db.Float,       nullable=True)

    # Free-form note Richard can leave — e.g. "Goodman discontinued
    # this part Q1; substituted with new SKU"
    notes = db.Column(db.String(512), nullable=True)

    # Audit trail. updated_by is an email string carried in the
    # X-Actor-Email header forwarded by the SPA.
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)
    updated_by = db.Column(db.String(255), nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "contractor_id", "supplier", "sku",
            name="uq_contractor_override_key",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id":                 self.id,
            "contractor_id":      self.contractor_id,
            "supplier":           self.supplier,
            "sku":                self.sku,
            "corrected_sku":      self.corrected_sku,
            "corrected_supplier": self.corrected_supplier,
            "unit_price":         self.unit_price,
            "notes":              self.notes,
            "created_at":         self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at":         self.updated_at.isoformat() + "Z" if self.updated_at else None,
            "updated_by":         self.updated_by,
        }

    @classmethod
    def lookup(
        cls,
        *,
        contractor_id: str,
        supplier: str,
        sku: str,
    ) -> Optional["ContractorOverride"]:
        """Read path called on every Wrightsoft line. Returns the
        single matching row or None. Case-insensitive on supplier (the
        4-char Src code) because Wrightsoft mixes case occasionally."""
        if not contractor_id or not supplier or not sku:
            return None
        return (
            db.session.query(cls)
            .filter_by(
                contractor_id=contractor_id,
                supplier=supplier.strip().upper(),
                sku=sku.strip(),
            )
            .one_or_none()
        )

    @classmethod
    def upsert(
        cls,
        *,
        contractor_id: str,
        supplier: str,
        sku: str,
        corrected_sku: Optional[str] = None,
        corrected_supplier: Optional[str] = None,
        unit_price: Optional[float] = None,
        notes: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> "ContractorOverride":
        """Insert or update by (contractor_id, supplier, sku). Returns
        the persisted row. Caller must commit."""
        if not contractor_id or not supplier or not sku:
            raise ValueError("contractor_id, supplier, sku are required")

        supplier_norm = supplier.strip().upper()
        sku_norm = sku.strip()
        now = _utcnow()

        existing = (
            db.session.query(cls)
            .filter_by(contractor_id=contractor_id, supplier=supplier_norm, sku=sku_norm)
            .one_or_none()
        )
        if existing is None:
            row = cls(
                contractor_id=contractor_id,
                supplier=supplier_norm,
                sku=sku_norm,
                corrected_sku=(corrected_sku or None) and corrected_sku.strip(),
                corrected_supplier=(
                    (corrected_supplier or None) and corrected_supplier.strip().upper()
                ),
                unit_price=unit_price,
                notes=(notes or None) and notes.strip(),
                created_at=now,
                updated_at=now,
                updated_by=updated_by,
            )
            db.session.add(row)
            return row

        # Update only fields the caller passed. None means 'leave alone';
        # explicit empty string means 'clear'.
        if corrected_sku is not None:
            existing.corrected_sku = corrected_sku.strip() or None
        if corrected_supplier is not None:
            existing.corrected_supplier = (corrected_supplier.strip().upper() or None)
        if unit_price is not None:
            existing.unit_price = unit_price
        if notes is not None:
            existing.notes = notes.strip() or None
        existing.updated_at = now
        if updated_by:
            existing.updated_by = updated_by
        return existing

    @classmethod
    def list_for_contractor(cls, contractor_id: str) -> list["ContractorOverride"]:
        """All overrides for a contractor, newest-first. Drives the
        SPA's overrides browser."""
        if not contractor_id:
            return []
        return (
            db.session.query(cls)
            .filter_by(contractor_id=contractor_id)
            .order_by(cls.updated_at.desc())
            .all()
        )
