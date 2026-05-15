"""
catalog_match.py — Look up SKU Catalog entries by equipment type +
capacity tolerance band.

Bridges parsed RUP equipment ({type, cfm, tonnage, model}) to specific
SKU Catalog entries with matching `capacity_btu` in the tolerance
band declared on each catalog row. Sits between the deterministic
rules engine (which fires SKUs by trigger flags but doesn't pick by
capacity) and the AI fallback (which estimates everything else).

Design intent (Phase 3.7, May 2026 — see _repo-docs/SAAS_BILLING_DESIGN
sibling notes for the broader context):
  - The rules engine already emits ONE SKU per trigger. If you have
    5 air handlers at 24 kBTU and 3 at 36 kBTU, the rules engine
    emits 8x the same AHU SKU because its triggers are coarse
    (ahu_present, ahu_count).
  - This module emits PER-INSTANCE catalog matches so different-
    capacity equipment items get the right SKU. The 5x24 kBTU AHUs
    get one Goodman SKU; the 3x36 kBTU AHUs get a different one.
  - Falls back gracefully: contractor-scoped SKUs win first, then
    globally-scoped SKUs, then nothing (and the rules engine /
    AI take it from there).

Confidence-flag semantics on emitted lines:
  - "catalog_exact"   : SKU.capacity_btu matched the parsed capacity
  - "catalog_band"    : parsed capacity inside [capacity_min, capacity_max] band
  - "catalog_default" : SKU has no capacity declared but matched type+contractor
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from services import sku_catalog

logger = logging.getLogger("procalcs_bom.catalog_match")


# ---------------------------------------------------------------------
# Equipment-type → trigger key (mirrors materials_rules.evaluate_trigger
# vocabulary so the two layers speak the same scope language).
# ---------------------------------------------------------------------

_TYPE_TO_TRIGGER: dict[str, str] = {
    "air_handler":  "ahu_present",
    "ahu":          "ahu_present",
    "condenser":    "condenser_present",
    "heat_pump":    "condenser_present",   # heat pumps use the condenser trigger
    "furnace":      "ahu_present",         # furnaces ride on AHU rules
    "heat_kit":     "heat_kit_present",
    "erv":          "erv_present",
    "hrv":          "erv_present",
}


def _trigger_for_equipment(eq_type: Optional[str]) -> Optional[str]:
    """Map a canonical equipment type to its rules-engine trigger key.
    Returns None for unknown types — caller should skip those (parser's
    'other' bucket isn't actionable for catalog matching)."""
    if not eq_type:
        return None
    key = eq_type.lower().strip().replace(" ", "_")
    return _TYPE_TO_TRIGGER.get(key)


# ---------------------------------------------------------------------
# Capacity derivation. Equipment from the RUP parser carries one or
# more of {cfm, tonnage, model}. Convert to BTU for catalog matching.
# ---------------------------------------------------------------------

# Rough conversions used industry-wide for residential air-handling:
#   1 ton of cooling = 12,000 BTU/hr ≈ 400 CFM
# Both are approximations but consistent with how Wrightsoft and the
# AHRI catalogs encode equipment capacity.
_BTU_PER_TON = 12_000
_CFM_TO_BTU_FACTOR = 30  # 1 CFM ≈ 30 BTU/hr (12000 / 400)


def _equipment_capacity_btu(eq: dict) -> Optional[int]:
    """Best-effort BTU/hr for one parsed equipment record. Returns
    None when no usable signal exists — caller should treat that as
    'capacity unknown, match without band constraint'."""
    if not isinstance(eq, dict):
        return None

    # Prefer explicit tonnage when the parser surfaced it (most precise).
    tonnage = eq.get("tonnage")
    if tonnage is not None:
        try:
            return int(round(float(tonnage) * _BTU_PER_TON))
        except (TypeError, ValueError):
            pass

    # Fall back to CFM (residential rule of thumb).
    cfm = eq.get("cfm")
    if cfm is not None:
        try:
            return int(round(float(cfm) * _CFM_TO_BTU_FACTOR))
        except (TypeError, ValueError):
            pass

    # Some parsers stash an explicit capacity_btu — honor it.
    btu = eq.get("capacity_btu") or eq.get("btu")
    if btu is not None:
        try:
            return int(round(float(btu)))
        except (TypeError, ValueError):
            pass

    return None


# ---------------------------------------------------------------------
# SKU candidate filter
# ---------------------------------------------------------------------

def _candidate_skus_for_trigger(
    trigger_key: str,
    contractor_id: Optional[str],
    catalog: list[sku_catalog.SKUItem],
) -> list[sku_catalog.SKUItem]:
    """Filter the catalog to SKUs that:
      1. Have the matching trigger
      2. Are scoped to this contractor OR are global (contractor_id None)
      3. Aren't disabled

    Order: contractor-scoped first (so they win the picker if
    capacity matches equally), then globals.
    """
    matches = [
        s for s in catalog
        if not s.disabled and s.trigger == trigger_key
        and (s.contractor_id is None or s.contractor_id == contractor_id)
    ]
    matches.sort(key=lambda s: (s.contractor_id is None, s.sku))  # contractor-scoped first
    return matches


def _pick_sku_by_capacity(
    candidates: list[sku_catalog.SKUItem],
    target_btu: Optional[int],
) -> tuple[Optional[sku_catalog.SKUItem], str]:
    """Choose the best SKU from candidates given a target capacity.

    Returns (sku, confidence) where confidence is:
      "catalog_exact"   : sku.capacity_btu == target_btu
      "catalog_band"    : target_btu is in [min, max] band
      "catalog_default" : no capacity info on either side OR no better match found
      "no_match"        : candidates is empty
    """
    if not candidates:
        return None, "no_match"

    if target_btu is not None:
        # Exact match wins.
        for s in candidates:
            if s.capacity_btu == target_btu:
                return s, "catalog_exact"
        # Band match next.
        for s in candidates:
            lo, hi = s.capacity_min_btu, s.capacity_max_btu
            if lo is not None and hi is not None and lo <= target_btu <= hi:
                return s, "catalog_band"

    # No capacity info or no banded candidate — first contractor-scoped
    # (or first global) wins. Better than nothing; better than asking AI.
    return candidates[0], "catalog_default"


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def match_equipment_to_catalog(
    equipment: list[dict],
    contractor_id: Optional[str],
    *,
    catalog: Optional[list[sku_catalog.SKUItem]] = None,
) -> list[dict]:
    """Emit one matched-SKU line per parsed equipment item.

    Args:
        equipment: parsed equipment array (RUP design_data.equipment).
            Each dict has at minimum {name, type}; ideally cfm/tonnage too.
        contractor_id: client_id of the BOM's profile. Contractor-scoped
            SKUs win over globals; pass None to consider only globals.
        catalog: override SKU list (used in tests). Defaults to the live
            catalog with disabled items excluded.

    Returns a list of line-item dicts in the same shape rules_priced
    uses, with two extra fields for provenance:
      - source: "catalog_match"
      - confidence: catalog_exact | catalog_band | catalog_default

    Equipment items with no matchable trigger or no candidates are
    skipped — the caller's AI / rules-engine pipeline picks them up.
    """
    if not isinstance(equipment, list) or not equipment:
        return []

    items = catalog if catalog is not None else sku_catalog.all_items(include_disabled=False)
    out: list[dict] = []

    for eq in equipment:
        trigger = _trigger_for_equipment(eq.get("type"))
        if not trigger:
            continue
        candidates = _candidate_skus_for_trigger(trigger, contractor_id, items)
        if not candidates:
            continue
        target_btu = _equipment_capacity_btu(eq)
        sku, confidence = _pick_sku_by_capacity(candidates, target_btu)
        if sku is None:
            continue

        # Emit one line per matched equipment item. Quantity is 1 (the
        # rules engine handles per-equipment quantity via its
        # quantity_resolver; this layer is per-instance).
        out.append({
            "category":    sku.section.lower().split()[0] if sku.section else "equipment",
            "description": sku.description,
            "quantity":    1.0,
            "unit":        "EA",
            "unit_cost":   sku.default_unit_price,
            "sku":         sku.sku,
            "supplier":    sku.supplier,
            "section":     sku.section,
            "phase":       sku.phase,
            "manufacturer": sku.manufacturer,
            "source":      "catalog_match",
            "confidence":  confidence,
            # Hint for the deduper downstream — equipment items that
            # share an SKU should fold to a single multi-quantity line.
            "_match_key":  (sku.sku, eq.get("name") or ""),
            # Carry the parsed equipment capacity so a designer can see
            # what we matched against (useful when confidence=band).
            "_target_btu": target_btu,
        })

    logger.info(
        "catalog_match: %d equipment items in, %d matched lines out (contractor=%s)",
        len(equipment), len(out), contractor_id or "global",
    )
    return out


def coalesce_matched_lines(matched: list[dict]) -> list[dict]:
    """Fold per-equipment lines that share an SKU into one line with
    quantity = N. Most BOMs prefer '5x AHU SKU XYZ' over five separate
    rows. Strips the internal _match_key / _target_btu hints."""
    if not matched:
        return []

    grouped: dict[str, dict] = {}
    for line in matched:
        sku = line["sku"]
        if sku not in grouped:
            # Copy and strip internals on first occurrence.
            head = {k: v for k, v in line.items() if not k.startswith("_")}
            grouped[sku] = head
        else:
            grouped[sku]["quantity"] += line["quantity"]

    return list(grouped.values())
