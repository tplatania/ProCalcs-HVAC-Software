"""
SKU Catalog — supplier-aware part numbers and quantity rules.

Source of truth is the Firestore collection ``sku_catalog``. The
checked-in JSON at ``data/sku_catalog.json`` is used for two things:
  1. Seeding fresh deploys via ``scripts/seed_sku_catalog.py``.
  2. Read-only fallback when Firestore is unreachable or empty —
     so dev environments without GCP credentials still load the
     same 21 starter SKUs.

Provides typed lookups for the materials rules engine:

    catalog.items_for_section("Rheia Duct System Equipment")
    catalog.get("10-00-190")
    catalog.items_with_trigger("rheia_in_scope")

And CRUD operations for Richard's team to maintain the catalog
through the Designer Desktop UI:

    catalog.create_item(item_dict)        # 409 if SKU already exists
    catalog.update_item(sku, patch)       # partial update
    catalog.delete_item(sku)              # hard delete
    catalog.set_disabled(sku, True/False) # soft hide

Bootstrapped 2026-04-29 from the contractor sample BOM
``Lot 1 T075 Elm ACL BOM.xls`` (21 SKUs, 3 sections, 5 suppliers).
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger('procalcs_bom')

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "sku_catalog.json"
COLLECTION = "sku_catalog"

# Acceptable values for validation. Mirrors the JSON _meta but kept
# in code so route validation doesn't have to read the JSON file.
VALID_SECTIONS = {
    "Equipment",
    "Duct System Equipment",
    "Rheia Duct System Equipment",
    "Labor",
}
VALID_TRIGGERS = {
    "always",
    "ahu_present",
    "condenser_present",
    "erv_present",
    "heat_kit_present",
    "rheia_in_scope",
    "rectangular_duct",
    "round_vinyl_duct",
    "register_count",
}
VALID_QUANTITY_MODES = {
    "fixed",
    "per_unit",
    "per_lf",
    "per_register",
    "rheia_per_lf",
    "rheia_per_takeoff",
    "rheia_per_endpoint",
    "fitting_count",
}
VALID_PHASES = {None, "Rough", "Finish"}


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SKUItem:
    """One catalog entry.

    Schema bumped May 2026 (Phase 3.5) with five additive fields to
    support catalog-augmented BOM generation when the parser surfaces
    equipment with capacity but no SKU. None of the new fields are
    required — existing 21 starter SKUs round-trip unchanged. New
    fields enable:

    - wrightsoft_codes: bridge to generic_ids in Wrightsoft's
      generic_parts.csv (loaded by services/wrightsoft_catalog.py).
      One catalog SKU can cover multiple Wrightsoft generics
      (e.g. one Goodman AHU SKU covers AHU-24K, AHU-30K, AHU-36K).
    - capacity_btu: nominal sizing for equipment SKUs. Used by the
      catalog-augmented BOM generator (Phase 3.7) to pick the right
      SKU when the parser reports "5-ton AHU".
    - capacity_min_btu / capacity_max_btu: tolerance band so a
      "24K AHU" SKU can match RUP equipment in the 22–26K range
      without an exact-match miss.
    - manufacturer: full display name ("Goodman", "Rheia") separate
      from the existing 4-char `supplier` code (GOOD, RHEA).
    - contractor_id: optional scope. When set, this SKU only applies
      to BOMs generated for that contractor's profile. When null,
      the SKU is globally available. Replaces the need for separate
      per-contractor catalogs — designers manage one unified catalog.
    """
    sku: str
    supplier: str
    section: str
    phase: Optional[str]
    description: str
    trigger: str
    quantity: dict[str, Any]
    default_unit_price: float
    notes: str = ""
    disabled: bool = False
    # Phase 3.5 additions — all optional, default to "no constraint".
    wrightsoft_codes: tuple[str, ...] = ()
    capacity_btu: Optional[int] = None
    capacity_min_btu: Optional[int] = None
    capacity_max_btu: Optional[int] = None
    manufacturer: Optional[str] = None
    contractor_id: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: dict) -> "SKUItem":
        # wrightsoft_codes is stored as a list in JSON/Firestore but
        # held as a tuple in Python so the dataclass stays hashable
        # (frozen=True requires immutable fields).
        codes_raw = raw.get("wrightsoft_codes") or []
        if isinstance(codes_raw, str):
            # Tolerate single-string (common from form inputs / CSV cells)
            codes = (codes_raw,) if codes_raw else ()
        else:
            codes = tuple(str(c) for c in codes_raw if c)
        return cls(
            sku=raw["sku"],
            supplier=raw["supplier"],
            section=raw["section"],
            phase=raw.get("phase"),
            description=raw["description"],
            trigger=raw["trigger"],
            quantity=raw.get("quantity") or {},
            default_unit_price=float(raw.get("default_unit_price") or 0),
            notes=raw.get("notes", ""),
            disabled=bool(raw.get("disabled", False)),
            wrightsoft_codes=codes,
            capacity_btu=_coerce_int_or_none(raw.get("capacity_btu")),
            capacity_min_btu=_coerce_int_or_none(raw.get("capacity_min_btu")),
            capacity_max_btu=_coerce_int_or_none(raw.get("capacity_max_btu")),
            manufacturer=(raw.get("manufacturer") or None) or None,
            contractor_id=(raw.get("contractor_id") or None) or None,
        )

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "supplier": self.supplier,
            "section": self.section,
            "phase": self.phase,
            "description": self.description,
            "trigger": self.trigger,
            "quantity": self.quantity,
            "default_unit_price": self.default_unit_price,
            "notes": self.notes,
            "disabled": self.disabled,
            "wrightsoft_codes": list(self.wrightsoft_codes),
            "capacity_btu": self.capacity_btu,
            "capacity_min_btu": self.capacity_min_btu,
            "capacity_max_btu": self.capacity_max_btu,
            "manufacturer": self.manufacturer,
            "contractor_id": self.contractor_id,
        }


def _coerce_int_or_none(value: Any) -> Optional[int]:
    """Cast a raw payload value to int or None. Empty string, None,
    and anything that can't parse become None — used by from_dict to
    accept loose JSON / CSV input."""
    if value is None or value == "":
        return None
    try:
        return int(float(value))  # tolerate "24000.0" style strings
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class CatalogError(Exception):
    """Raised by CRUD ops on validation / not-found / conflict."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def validate_item(payload: dict, *, require_sku: bool = True) -> dict:
    """Normalize + validate an item dict. Returns a clean dict ready
    to persist. Raises CatalogError(status_code=400) on bad input."""
    errors = []

    sku = (payload.get("sku") or "").strip()
    if require_sku and not sku:
        errors.append("sku is required")

    supplier = (payload.get("supplier") or "").strip()
    if not supplier:
        errors.append("supplier is required")

    section = (payload.get("section") or "").strip()
    if section and section not in VALID_SECTIONS:
        errors.append(f"section must be one of {sorted(VALID_SECTIONS)}")
    elif not section:
        errors.append("section is required")

    description = (payload.get("description") or "").strip()
    if not description:
        errors.append("description is required")

    trigger = (payload.get("trigger") or "").strip()
    if trigger and trigger not in VALID_TRIGGERS:
        errors.append(f"trigger must be one of {sorted(VALID_TRIGGERS)}")
    elif not trigger:
        errors.append("trigger is required")

    phase = payload.get("phase")
    if isinstance(phase, str):
        phase = phase.strip() or None
    if phase not in VALID_PHASES:
        errors.append(f"phase must be one of {sorted(p for p in VALID_PHASES if p)} or null")

    quantity = payload.get("quantity")
    if not isinstance(quantity, dict) or not quantity:
        errors.append("quantity must be a non-empty object with at least a 'mode' field")
    else:
        mode = quantity.get("mode")
        if mode not in VALID_QUANTITY_MODES:
            errors.append(f"quantity.mode must be one of {sorted(VALID_QUANTITY_MODES)}")

    try:
        default_unit_price = float(payload.get("default_unit_price") or 0)
    except (TypeError, ValueError):
        errors.append("default_unit_price must be numeric")
        default_unit_price = 0.0

    # Phase 3.5 — validate the new optional fields. All five default to
    # null/empty when missing; specific shape constraints only.
    raw_codes = payload.get("wrightsoft_codes") or []
    if isinstance(raw_codes, str):
        raw_codes = [raw_codes] if raw_codes else []
    if not isinstance(raw_codes, list):
        errors.append("wrightsoft_codes must be a list of strings")
        raw_codes = []
    wrightsoft_codes = [str(c).strip() for c in raw_codes if str(c).strip()]

    capacity_btu     = _coerce_int_or_none(payload.get("capacity_btu"))
    capacity_min_btu = _coerce_int_or_none(payload.get("capacity_min_btu"))
    capacity_max_btu = _coerce_int_or_none(payload.get("capacity_max_btu"))

    # If a tolerance band is given, both endpoints must be present and
    # min <= nominal <= max (when nominal also given).
    if (capacity_min_btu is None) != (capacity_max_btu is None):
        errors.append("capacity_min_btu and capacity_max_btu must be set together")
    elif capacity_min_btu is not None and capacity_max_btu is not None:
        if capacity_min_btu > capacity_max_btu:
            errors.append("capacity_min_btu must be <= capacity_max_btu")
        if capacity_btu is not None and not (capacity_min_btu <= capacity_btu <= capacity_max_btu):
            errors.append("capacity_btu must lie within [capacity_min_btu, capacity_max_btu]")

    manufacturer = (payload.get("manufacturer") or "").strip() or None
    contractor_id = (payload.get("contractor_id") or "").strip() or None

    if errors:
        raise CatalogError("; ".join(errors), status_code=400)

    return {
        "sku": sku,
        "supplier": supplier,
        "section": section,
        "phase": phase,
        "description": description,
        "trigger": trigger,
        "quantity": quantity,
        "default_unit_price": default_unit_price,
        "notes": (payload.get("notes") or "").strip(),
        "disabled": bool(payload.get("disabled", False)),
        # Phase 3.5 additions — null/empty when omitted.
        "wrightsoft_codes": wrightsoft_codes,
        "capacity_btu":     capacity_btu,
        "capacity_min_btu": capacity_min_btu,
        "capacity_max_btu": capacity_max_btu,
        "manufacturer":     manufacturer,
        "contractor_id":    contractor_id,
    }


# ---------------------------------------------------------------------------
# Firestore client (singleton, lazy)
# ---------------------------------------------------------------------------

_db = None
_db_lock = threading.Lock()


def _get_db():
    """Return the Firestore client. None if google-cloud-firestore
    can't initialize (dev without creds). Callers must handle None."""
    global _db
    if _db is not None:
        return _db
    with _db_lock:
        if _db is not None:
            return _db
        try:
            from google.cloud import firestore
            _db = firestore.Client()
            return _db
        except Exception as exc:  # noqa: BLE001
            logger.warning("Firestore unavailable, using JSON fallback: %s", exc)
            return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Cached catalog state — invalidates on every write
# ---------------------------------------------------------------------------

@dataclass
class _CatalogState:
    items: list[SKUItem] = field(default_factory=list)
    by_sku: dict[str, SKUItem] = field(default_factory=dict)
    by_section: dict[str, list[SKUItem]] = field(default_factory=dict)
    by_trigger: dict[str, list[SKUItem]] = field(default_factory=dict)
    source: str = "uninitialized"  # "firestore" | "json_fallback"


_state: Optional[_CatalogState] = None
_state_lock = threading.Lock()


def _build_state(items: list[SKUItem], source: str) -> _CatalogState:
    by_sku: dict[str, SKUItem] = {}
    by_section: dict[str, list[SKUItem]] = {}
    by_trigger: dict[str, list[SKUItem]] = {}
    for it in items:
        by_sku[it.sku] = it
        by_section.setdefault(it.section, []).append(it)
        by_trigger.setdefault(it.trigger, []).append(it)
    return _CatalogState(
        items=items,
        by_sku=by_sku,
        by_section=by_section,
        by_trigger=by_trigger,
        source=source,
    )


def _load_from_firestore() -> Optional[list[SKUItem]]:
    """Return list of items from Firestore, or None if Firestore
    unreachable. Empty list means collection exists but is empty —
    callers may want to fall back to JSON for fresh deploys."""
    db = _get_db()
    if db is None:
        return None
    try:
        docs = db.collection(COLLECTION).stream()
        items = []
        for doc in docs:
            data = doc.to_dict() or {}
            try:
                items.append(SKUItem.from_dict(data))
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping malformed catalog doc %s: %s", doc.id, exc)
        return items
    except Exception as exc:  # noqa: BLE001
        logger.error("Firestore read failed for sku_catalog: %s", exc)
        return None


def _load_from_json() -> list[SKUItem]:
    """Fallback path — read the checked-in JSON. Used when Firestore
    is empty (fresh deploy) or unreachable (dev without creds)."""
    try:
        raw = json.loads(_CATALOG_PATH.read_text())
    except FileNotFoundError:
        logger.error("SKU catalog JSON missing at %s", _CATALOG_PATH)
        return []
    except json.JSONDecodeError as exc:
        logger.error("SKU catalog JSON malformed: %s", exc)
        return []
    return [SKUItem.from_dict(it) for it in raw.get("items", [])]


def _load() -> _CatalogState:
    """Lazy-load catalog state. Idempotent + threadsafe."""
    global _state
    if _state is not None:
        return _state
    with _state_lock:
        if _state is not None:
            return _state

        fs_items = _load_from_firestore()
        if fs_items is None:
            # Firestore unreachable → JSON fallback.
            items = _load_from_json()
            source = "json_fallback"
        elif len(fs_items) == 0:
            # Firestore reachable but empty (fresh deploy / never seeded).
            items = _load_from_json()
            source = "json_fallback_empty_firestore"
            logger.info("Firestore sku_catalog empty — using JSON seed of %d items", len(items))
        else:
            items = fs_items
            source = "firestore"

        _state = _build_state(items, source)
        logger.info(
            "SKU catalog loaded: %d items across %d sections (source=%s)",
            len(items), len(_state.by_section), source,
        )
        return _state


def reload() -> None:
    """Drop the cached state. Called after writes and from tests."""
    global _state
    with _state_lock:
        _state = None


# ---------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------

def all_items(include_disabled: bool = True) -> list[SKUItem]:
    """Every SKU. Set include_disabled=False to exclude soft-hidden items."""
    items = _load().items
    if include_disabled:
        return list(items)
    return [it for it in items if not it.disabled]


def get(sku: str) -> Optional[SKUItem]:
    """Look up a single SKU. Returns None if unknown."""
    return _load().by_sku.get(sku)


def items_for_section(section: str, include_disabled: bool = True) -> list[SKUItem]:
    rows = _load().by_section.get(section, [])
    if include_disabled:
        return list(rows)
    return [it for it in rows if not it.disabled]


def sections() -> list[str]:
    """Distinct output sections, in catalog order (preserves first-seen)."""
    seen: list[str] = []
    for it in _load().items:
        if it.section not in seen:
            seen.append(it.section)
    return seen


def items_with_trigger(trigger: str, include_disabled: bool = False) -> list[SKUItem]:
    """Every SKU whose trigger matches. Defaults to *excluding* disabled
    items because the rules engine will be the main caller and shouldn't
    emit hidden SKUs."""
    rows = _load().by_trigger.get(trigger, [])
    if include_disabled:
        return list(rows)
    return [it for it in rows if not it.disabled]


def source() -> str:
    """For diagnostics — 'firestore' | 'json_fallback' | similar."""
    return _load().source


# ---------------------------------------------------------------------------
# Write API — Firestore-backed CRUD
# ---------------------------------------------------------------------------

def _require_db():
    db = _get_db()
    if db is None:
        raise CatalogError(
            "Firestore unavailable — catalog is read-only in this environment",
            status_code=503,
        )
    return db


def create_item(payload: dict, *, actor_email: Optional[str] = None) -> dict:
    """Insert a new SKU. Raises CatalogError(409) if it already exists."""
    clean = validate_item(payload, require_sku=True)
    db = _require_db()

    doc_ref = db.collection(COLLECTION).document(clean["sku"])
    if doc_ref.get().exists:
        raise CatalogError(f"SKU {clean['sku']!r} already exists", status_code=409)

    now = _utc_now()
    record = {
        **clean,
        "created_at": now,
        "updated_at": now,
        "created_by": actor_email,
        "updated_by": actor_email,
    }
    doc_ref.set(record)
    logger.info("[SKUCatalog] Created %s by %s", clean["sku"], actor_email or "anon")
    reload()
    return clean


def update_item(sku: str, patch: dict, *, actor_email: Optional[str] = None) -> dict:
    """Partial update. Forbids changing the doc id (sku field).
    Raises CatalogError(404) if SKU doesn't exist."""
    db = _require_db()
    doc_ref = db.collection(COLLECTION).document(sku)
    snap = doc_ref.get()
    if not snap.exists:
        raise CatalogError(f"SKU {sku!r} not found", status_code=404)

    existing = snap.to_dict() or {}
    merged = {**existing, **patch, "sku": sku}  # sku stays pinned
    clean = validate_item(merged, require_sku=True)

    record = {
        **clean,
        "created_at": existing.get("created_at"),
        "updated_at": _utc_now(),
        "created_by": existing.get("created_by"),
        "updated_by": actor_email,
    }
    doc_ref.set(record)
    logger.info("[SKUCatalog] Updated %s by %s", sku, actor_email or "anon")
    reload()
    return clean


def delete_item(sku: str, *, actor_email: Optional[str] = None) -> None:
    """Hard delete. Raises CatalogError(404) if missing."""
    db = _require_db()
    doc_ref = db.collection(COLLECTION).document(sku)
    if not doc_ref.get().exists:
        raise CatalogError(f"SKU {sku!r} not found", status_code=404)
    doc_ref.delete()
    logger.info("[SKUCatalog] Deleted %s by %s", sku, actor_email or "anon")
    reload()


def bulk_upsert(
    payloads: list[dict],
    *,
    actor_email: Optional[str] = None,
) -> dict:
    """Idempotent bulk upsert.

    Walks ``payloads`` in order. Each payload is validated and either
    created (if no doc with that sku exists) or fully replaced (if it
    does). Per-row failures are isolated — a bad row contributes an
    entry to ``errors`` and the rest of the batch continues.

    Returns a summary dict::

        {
            "created":  N,   # new docs written
            "updated":  M,   # existing docs replaced
            "skipped":  K,   # rows that failed validation
            "errors":   [{"index": i, "sku": "...", "error": "..."}],
        }

    Designed to be called by /api/v1/sku-catalog/bulk-import. Single
    cache reload at the end (not per-row) so importing 100 SKUs is
    one Firestore-stream invalidation, not 100.
    """
    db = _require_db()
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors":  [],
    }
    if not isinstance(payloads, list):
        raise CatalogError("bulk import expects a list of SKU dicts", status_code=400)

    now = _utc_now()
    for index, payload in enumerate(payloads):
        if not isinstance(payload, dict):
            summary["skipped"] += 1
            summary["errors"].append({
                "index": index,
                "sku":   None,
                "error": f"row {index} is not an object (got {type(payload).__name__})",
            })
            continue

        try:
            clean = validate_item(payload, require_sku=True)
        except CatalogError as exc:
            summary["skipped"] += 1
            summary["errors"].append({
                "index": index,
                "sku":   payload.get("sku"),
                "error": str(exc),
            })
            continue

        doc_ref = db.collection(COLLECTION).document(clean["sku"])
        snap = doc_ref.get()
        if snap.exists:
            existing = snap.to_dict() or {}
            record = {
                **clean,
                "created_at": existing.get("created_at"),
                "updated_at": now,
                "created_by": existing.get("created_by"),
                "updated_by": actor_email,
            }
            summary["updated"] += 1
        else:
            record = {
                **clean,
                "created_at": now,
                "updated_at": now,
                "created_by": actor_email,
                "updated_by": actor_email,
            }
            summary["created"] += 1

        doc_ref.set(record)

    if summary["created"] or summary["updated"]:
        reload()  # single cache invalidation for the whole batch

    logger.info(
        "[SKUCatalog] bulk-upsert by %s: created=%d updated=%d skipped=%d",
        actor_email or "anon",
        summary["created"], summary["updated"], summary["skipped"],
    )
    return summary


def set_disabled(sku: str, disabled: bool, *, actor_email: Optional[str] = None) -> dict:
    """Toggle the soft-hide flag without touching anything else."""
    db = _require_db()
    doc_ref = db.collection(COLLECTION).document(sku)
    snap = doc_ref.get()
    if not snap.exists:
        raise CatalogError(f"SKU {sku!r} not found", status_code=404)

    doc_ref.update({
        "disabled": bool(disabled),
        "updated_at": _utc_now(),
        "updated_by": actor_email,
    })
    logger.info(
        "[SKUCatalog] %s %s by %s",
        "Disabled" if disabled else "Enabled", sku, actor_email or "anon",
    )
    reload()
    fresh = doc_ref.get().to_dict() or {}
    return {**fresh, "sku": sku}
