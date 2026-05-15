"""
wrightsoft_catalog.py — Loader for the BOM-relevant CSVs Tom exported
from Wrightsoft's library.

Five small reference CSVs (~600 KB total) ship in
``backend/data/wrightsoft_catalog/`` and load eagerly on first use.
The 70 manufacturer-specific AHRI equipment catalogs (~239 MB,
1.45 M rows total) are NOT part of this loader — those land in
Firestore later (Phase 4) so the Docker image stays slim.

Files consumed:
  - categories.csv   (14 rows)  Wrightsoft category code → human name
  - manufacturers.csv (29 rows) 4-char source code → mfr details
  - generic_parts.csv (3,179)   generic_id + category + description + units
  - mapped_parts.csv (4,113)    generic_id ↔ supplier + manufacturer SKU
  - DFUnit.csv (964)            Ductless / mini-split equipment library

Inventory was verified clean in Phase 1 (see _repo-docs/RUP_BINARY_LAYOUT.md
follow-up notes): every file UTF-8 with BOM, every AHRI per-equipment-type
schema is consistent across all 12 manufacturers, no parse errors, no
uneven column counts.

Public surface (Phase 2+ adds more):
  - load_categories()        → dict[code, description]
  - load_manufacturers()     → dict[source_code, dict]
  - load_generic_parts()     → dict[generic_id, dict]
  - load_mapped_parts()      → list[dict] of generic→supplier mappings
  - load_dfunit()            → list[dict]
  - all_categories()         → list of category codes
  - lookup_skus_for_generic(generic_id, supplier_pref=None)
                             → list of (supplier, manufacturer_partnum)
"""

from __future__ import annotations

import csv
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("procalcs_bom.wrightsoft_catalog")

# ---------------------------------------------------------------------
# Module-level cache. Populated lazily on first call to any loader.
# Thread-safe via a single lock — these CSVs load in <100ms so a
# coarse lock is fine.
# ---------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "wrightsoft_catalog"

_lock = threading.Lock()


@dataclass
class _Cache:
    categories: Optional[dict[str, str]] = None  # code -> description
    manufacturers: Optional[dict[str, dict[str, Any]]] = None  # source -> row
    generic_parts: Optional[dict[str, dict[str, Any]]] = None  # generic_id (item) -> row
    mapped_parts: Optional[list[dict[str, Any]]] = None  # one row per (generic, variant)
    mapped_by_generic: Optional[dict[str, list[dict[str, Any]]]] = None  # index
    dfunit: Optional[list[dict[str, Any]]] = None
    source: str = "uninitialized"


_cache = _Cache()


# ---------------------------------------------------------------------
# Loaders — each reads the corresponding CSV once and caches.
# ---------------------------------------------------------------------

def _read_csv_dict(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8-with-BOM CSV into a list of dicts. utf-8-sig
    transparently strips the BOM that Wrightsoft writes on every file."""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def load_categories() -> dict[str, str]:
    """Wrightsoft category code (e.g. 'DFRBTR') → human description
    (e.g. 'Duct boots and registers')."""
    with _lock:
        if _cache.categories is None:
            rows = _read_csv_dict(_DATA_DIR / "categories.csv")
            _cache.categories = {r["Category"]: r["Description"] for r in rows}
            logger.info("Loaded %d Wrightsoft categories", len(_cache.categories))
    return _cache.categories


def load_manufacturers() -> dict[str, dict[str, Any]]:
    """4-char source code (e.g. 'GOOD', 'WSF', 'RHEA') → manufacturer
    metadata dict (Name / Address / Phone / Web / Type / etc.)."""
    with _lock:
        if _cache.manufacturers is None:
            rows = _read_csv_dict(_DATA_DIR / "manufacturers.csv")
            _cache.manufacturers = {r["Source"]: r for r in rows}
            logger.info("Loaded %d Wrightsoft manufacturers", len(_cache.manufacturers))
    return _cache.manufacturers


def load_generic_parts() -> dict[str, dict[str, Any]]:
    """generic_id (e.g. 'BPERT0750', 'HV-B15L') → row with
    Category / Description / Units. The generic_id IS the
    Wrightsoft-internal part code that DQFTG-library entries reference
    in the .rup binary."""
    with _lock:
        if _cache.generic_parts is None:
            rows = _read_csv_dict(_DATA_DIR / "generic_parts.csv")
            _cache.generic_parts = {r["Item"]: r for r in rows}
            logger.info("Loaded %d Wrightsoft generic parts", len(_cache.generic_parts))
    return _cache.generic_parts


def load_mapped_parts() -> list[dict[str, Any]]:
    """Generic-part → manufacturer-SKU mappings. One row per
    (generic_item, supplier, quantity_variant). Multiple rows per
    generic_item when the part comes in different package sizes
    (e.g. PEX0750 sold as 100 ft / 500 ft / 1000 ft rolls under QST)."""
    with _lock:
        if _cache.mapped_parts is None:
            rows = _read_csv_dict(_DATA_DIR / "mapped_parts.csv")
            _cache.mapped_parts = rows
            # Build index by generic_item for cheap lookup.
            idx: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in rows:
                idx[r["generic_item"]].append(r)
            _cache.mapped_by_generic = dict(idx)
            logger.info(
                "Loaded %d Wrightsoft mapped parts (%d distinct generics)",
                len(rows), len(_cache.mapped_by_generic),
            )
    return _cache.mapped_parts


def load_dfunit() -> list[dict[str, Any]]:
    """Ductless / mini-split equipment library. 19 columns including
    Manufacturer, Model, SysType, ClgCap (BTU), HtgCap (BTU), Series,
    Width / Depth / Height / Weight, MaxPipeLen / MaxPipeHeight."""
    with _lock:
        if _cache.dfunit is None:
            rows = _read_csv_dict(_DATA_DIR / "DFUnit.csv")
            _cache.dfunit = rows
            logger.info("Loaded %d Wrightsoft DFUnit (mini-split) entries", len(rows))
    return _cache.dfunit


# ---------------------------------------------------------------------
# Lookup helpers — built on top of the loaders above.
# Phase 2 will extend with category-section mapping; Phase 4 with AHRI.
# ---------------------------------------------------------------------

def all_categories() -> list[str]:
    """Sorted list of every category code Wrightsoft knows."""
    return sorted(load_categories().keys())


def all_manufacturer_codes() -> list[str]:
    """Sorted list of every supplier/manufacturer 4-char code."""
    return sorted(load_manufacturers().keys())


def lookup_skus_for_generic(
    generic_id: str,
    supplier_pref: Optional[str] = None,
) -> list[tuple[str, str]]:
    """Return [(supplier_code, manufacturer_partnum)] for a generic_id.

    If supplier_pref is given AND that supplier has a mapping, only the
    matching rows are returned (preserves quantity-variant ordering).
    Otherwise every supplier match is returned in file order.

    Returns [] if the generic_id has no mapping (caller decides whether
    to fall back to displaying the generic description, ask the AI, etc).
    """
    load_mapped_parts()  # populates _cache.mapped_by_generic
    rows = (_cache.mapped_by_generic or {}).get(generic_id, [])
    out = [(r["preferred_source"], r["manufacturer_partnum"]) for r in rows]
    if supplier_pref:
        filtered = [(s, p) for s, p in out if s == supplier_pref]
        if filtered:
            return filtered
    return out


def category_for_generic(generic_id: str) -> Optional[str]:
    """Return the Wrightsoft category code for a generic_id, or None
    if unknown. The category IS the bridge between an individual SKU
    and the contractor section structure — see section_for_category."""
    parts = load_generic_parts()
    row = parts.get(generic_id)
    return row.get("Category") if row else None


# ---------------------------------------------------------------------
# Phase 2 — Wrightsoft category → contractor section mapping
#
# The contractor sample BOM (`Lot 1 T075 Elm ACL`) groups items into
# four sections: Equipment / Duct System Equipment / Rheia Duct System
# Equipment / Labor. Wrightsoft has 13 raw categories. The mapping
# below routes each Wrightsoft category to the appropriate contractor
# section. Categories that don't fit cleanly (RHALL = radiant heating,
# HVACCTLS = controls, MSRP = mini-split refrigeration pipes) are
# explicitly flagged so future updates don't silently fall through.
#
# This mapping is the SOURCE OF TRUTH for grouping in PDF + JSON BOM
# output. Anything that wants to know "which section does this SKU
# belong in" goes through section_for_category.
# ---------------------------------------------------------------------

# Contractor section labels — match the sample BOM verbatim so the
# generated PDF reads the same as a designer-built spreadsheet.
SECTION_EQUIPMENT       = "Equipment"
SECTION_DUCT_SYSTEM     = "Duct System Equipment"
SECTION_RHEIA           = "Rheia Duct System Equipment"
SECTION_LABOR           = "Labor"
SECTION_OTHER           = "Other"  # fallback — investigate if it ever appears

# Wrightsoft category codes (13 total) → contractor section.
# Verified against Wrightsoft's categories.csv.
_CATEGORY_TO_SECTION: dict[str, str] = {
    # Standard duct-system fittings — the bulk of any project's BOM.
    "DFRBTR":   SECTION_DUCT_SYSTEM,    # Duct boots and registers
    "DFRELB":   SECTION_DUCT_SYSTEM,    # Duct elbows
    "DFRPLN":   SECTION_DUCT_SYSTEM,    # Duct plenum fittings
    "DFRTKO":   SECTION_DUCT_SYSTEM,    # Duct take offs
    "DFRTEE":   SECTION_DUCT_SYSTEM,    # Duct tees and wyes
    "DFRTRS":   SECTION_DUCT_SYSTEM,    # Duct transitions
    "DSRCT":    SECTION_DUCT_SYSTEM,    # Rectangular ducts
    "DSRND":    SECTION_DUCT_SYSTEM,    # Round ducts

    # Rheia / high-velocity small-diameter — universal across ProCalcs
    # projects per Tom + Richard 2026-04-29. Lives in its own section
    # so designers can see Rheia parts at a glance.
    "HVDALL":   SECTION_RHEIA,          # High velocity duct system

    # Equipment-adjacent
    "EACCESSY": SECTION_EQUIPMENT,      # Equipment accessories
    "HVACCTLS": SECTION_EQUIPMENT,      # HVAC Control System
    "MSRP":     SECTION_EQUIPMENT,      # Mini Split Refrigeration Pipes

    # Radiant heating — appears in catalog but rare in the residential
    # forced-air projects ProCalcs typically handles. Not in the sample
    # contractor BOM. Routed to Equipment as the safest bucket; revisit
    # if any radiant-heavy project surfaces.
    "RHALL":    SECTION_EQUIPMENT,      # Radiant heating
}

# Equipment items decoded from EQUIP / ZEQUIP / DFUnit blocks don't
# carry a Wrightsoft category code (they're equipment, not parts). They
# go straight to the Equipment section.
EQUIPMENT_CATEGORY_PSEUDO = "_EQUIPMENT"
_CATEGORY_TO_SECTION[EQUIPMENT_CATEGORY_PSEUDO] = SECTION_EQUIPMENT


def section_for_category(category: Optional[str]) -> str:
    """Map a Wrightsoft category code to the contractor section the
    line item should appear under. Unknown categories return
    SECTION_OTHER so they're visible in output rather than silently
    bucketed into Equipment.

    Pass EQUIPMENT_CATEGORY_PSEUDO for lines that come from the
    equipment library, not the generic-parts catalog.
    """
    if not category:
        return SECTION_OTHER
    return _CATEGORY_TO_SECTION.get(category, SECTION_OTHER)


def section_for_generic(generic_id: str) -> str:
    """Convenience: lookup category, then route to section. Returns
    SECTION_OTHER if the generic_id isn't in the catalog at all."""
    cat = category_for_generic(generic_id)
    return section_for_category(cat)


def all_sections() -> list[str]:
    """The four canonical sections, in display order. Used by the PDF
    template + bom_service formatter to emit consistent ordering."""
    return [
        SECTION_EQUIPMENT,
        SECTION_DUCT_SYSTEM,
        SECTION_RHEIA,
        SECTION_LABOR,
    ]


def categories_in_section(section: str) -> list[str]:
    """Reverse lookup — every REAL Wrightsoft category routed to a
    given section. Pseudo-categories (those prefixed with '_', used
    internally for items that don't carry a Wrightsoft category like
    raw equipment) are excluded so callers don't try to look them up
    in load_categories() and get a KeyError."""
    return sorted(
        c for c, s in _CATEGORY_TO_SECTION.items()
        if s == section and not c.startswith("_")
    )


# ---------------------------------------------------------------------
# Diagnostic / health
# ---------------------------------------------------------------------

def cache_summary() -> dict[str, Any]:
    """Diagnostic view of what's loaded — used by /api/v1/health and
    by tests that want to confirm the catalog is reachable without
    calling lookup helpers."""
    return {
        "data_dir": str(_DATA_DIR),
        "categories":     len(_cache.categories) if _cache.categories else 0,
        "manufacturers":  len(_cache.manufacturers) if _cache.manufacturers else 0,
        "generic_parts":  len(_cache.generic_parts) if _cache.generic_parts else 0,
        "mapped_parts":   len(_cache.mapped_parts) if _cache.mapped_parts else 0,
        "mapped_unique_generics": (
            len(_cache.mapped_by_generic) if _cache.mapped_by_generic else 0
        ),
        "dfunit":         len(_cache.dfunit) if _cache.dfunit else 0,
    }
