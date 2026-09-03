"""
bom_patches.py — server-side replay of run-scoped patch ops.

Day-30 (Tim, Test 2): patch carry-forward kept corrected quantities in
the LINE ITEMS after regeneration, but the Quick Order Summary (and
Duct Cuts summary) are computed once from the RAW build and were never
rebuilt — Tim's FBTI-4 10→2 correction showed 2 in the lines and 10 in
the summary. These helpers replay the ops (mirroring the SPA's
client-side applyPatchOps semantics exactly) and rebuild the derived
summaries so every surface agrees.

Consumables rows in the quick order depend on the contractor profile's
rules, which patches never touch — they are preserved verbatim from
the original summary instead of being rebuilt (avoids a Firestore
profile fetch on every read).
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("procalcs_bom")

_CONSUMABLES_CATEGORY = "Install consumables"


def apply_patch_ops(line_items: List[Dict[str, Any]],
                    ops: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Return a patched COPY of line_items. Semantics mirror the SPA's
    applyPatchOps: update by sku (qty recomputes total_price), remove
    by sku, add appends a manual line. Unknown skus no-op."""
    items = [dict(li) for li in (line_items or [])]
    for op in ops or []:
        kind = op.get("op")
        sku = op.get("sku")
        idx = next((i for i, li in enumerate(items)
                    if (li.get("sku") or li.get("generic_id")) == sku), -1)
        fields = op.get("fields") or {}
        if kind == "remove_line":
            if idx >= 0:
                items.pop(idx)
        elif kind == "add_line":
            qty = float(fields.get("quantity") or 1)
            price = float(fields.get("unit_price") or 0)
            # Dana #9a (2026-09-02): an added ERV landed in "Other"
            # because the section defaulted there. Honor an explicit
            # section, else infer Equipment from the description for
            # HVAC equipment keywords (safety net for older add ops or
            # a client that didn't pass section).
            section = fields.get("section")
            if not section:
                _d = str(fields.get("description") or sku).lower()
                _equip_kw = ("erv", "hrv", "air handler", "condenser",
                             "furnace", "coil", "heat strip", "elec strip",
                             "electric strip", "dehumidif", "ventilator",
                             "heat pump", "split ac", "ac unit")
                section = "Equipment" if any(k in _d for k in _equip_kw) else "Other"
            items.append({
                "generic_id": sku, "sku": sku,
                "description": fields.get("description") or sku,
                "quantity": qty, "unit": "ea",
                "unit_cost": price, "unit_price": price,
                "total_price": round(price * qty, 2),
                "source": fields.get("source") or "wrightsoft_manual",
                "section": section,
                "patched": True,
            })
        elif kind == "update_line" and idx >= 0:
            li = dict(items[idx])
            li["patched"] = True
            if fields.get("quantity") is not None:
                li["quantity"] = float(fields["quantity"])
                unit = li.get("unit_price") or li.get("unit_cost") or 0
                li["total_price"] = round(float(unit) * li["quantity"], 2)
            if fields.get("description") is not None:
                li["description"] = fields["description"]
            items[idx] = li
    return items


def rebuild_summaries(bom: Dict[str, Any],
                      ops: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Recompute quick_order_summary + duct_cuts_summary from the
    PATCHED line items, in place on `bom`. No-op when there are no ops.
    Consumables rows carry over from the original summary verbatim."""
    if not ops:
        return bom
    try:
        from services.bom_quick_order import (
            build_quick_order, build_duct_cuts_summary,
        )
        patched = apply_patch_ops(bom.get("line_items") or [], ops)
        consumables = [r for r in (bom.get("quick_order_summary") or [])
                       if r.get("category") == _CONSUMABLES_CATEGORY]
        bom["quick_order_summary"] = build_quick_order(patched) + consumables
        bom["duct_cuts_summary"] = build_duct_cuts_summary(patched)
    except Exception:  # noqa: BLE001 — summaries must never break a read
        logger.warning("patched-summary rebuild failed (serving raw)",
                       exc_info=True)
    return bom


def bom_with_patched_summaries(run) -> Dict[str, Any]:
    """Deep-copied generated_bom with summaries rebuilt from the run's
    patch ops — for run-detail reads. Stored data stays raw/canonical."""
    bom = copy.deepcopy(run.generated_bom or {})
    return rebuild_summaries(bom, run.patch_ops)


# Day-31 — structural extras extracted from the .rup bytes at upload
# time (duct tables, canvas annotations, register pre-flight). The
# wrightsoft line builder strips unknown keys, so any rebuild from
# stored wrightsoft_lines loses them unless explicitly carried from
# the parent run's stored BOM. Single source of truth for the key set
# (route-level snapshot in bom_routes.py uses the same list).
STRUCTURAL_EXTRA_KEYS = (
    "rup_balduct", "rup_unbuilt_hint", "rup_duct_geometry",
    "rup_file_type_hint", "duct_runout_pieces", "drawing_annotations",
    "register_preflight",
)


def carry_structural_extras(child_bom: Dict[str, Any],
                            parent_bom: Any) -> Dict[str, Any]:
    """Copy structural extras from a parent run's stored BOM onto a
    freshly rebuilt child BOM (setdefault — never overwrites keys the
    rebuild produced itself). Tolerates a None/non-dict parent."""
    if isinstance(parent_bom, dict):
        for key in STRUCTURAL_EXTRA_KEYS:
            if key in parent_bom:
                child_bom.setdefault(key, parent_bom[key])
    return child_bom
