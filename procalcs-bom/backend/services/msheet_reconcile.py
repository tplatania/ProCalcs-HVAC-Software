"""msheet_reconcile.py — reconcile an M-sheet against a .rup BOM.

Takes the structured output of `msheet_extract.extract_msheet()` plus a
generated BOM and returns a list of REVIEW FLAGS: things the mechanical
schedule specifies that the BOM is missing (Richard's #5 list), and the
true grille sizes that can replace the .rup's 12x12 auto-lump (#1).

HARD GUARDRAIL: this only PRODUCES flags. It never mutates the BOM, adds
lines, or overrides anything. Each flag carries an optional `proposed`
payload for the existing reviewer Apply flow (confidence-review / chat),
so nothing reaches the pilot's BOM without Richard/Dana accepting it.
Filter size, damper basis, and strap rates are still open (see
docs/standard-accessories-draft.md), so those flags stay advisory until
the quantities are confirmed.

Defaults-safe: no M-sheet (or a scanned one with no text layer) → [].
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


def _bom_equipment_ids(bom: Dict[str, Any]) -> List[str]:
    return [str(li.get("generic_id") or li.get("sku") or "")
            for li in (bom.get("line_items") or [])
            if (li.get("section") or "") == "Equipment"]


def _model_in_bom(model: str, bom_ids: List[str]) -> bool:
    """Match tolerant of the BOM's trailing wildcard (SUZ-AA12NL*** vs
    the schedule's SUZ-AA12NL)."""
    core = model.split("*")[0]
    return any(core and (core in b or b.split("*")[0] == core) for b in bom_ids)


def _bom_has_keyword(bom: Dict[str, Any], *keywords: str) -> bool:
    pat = re.compile("|".join(keywords), re.I)
    for li in (bom.get("line_items") or []):
        blob = f"{li.get('generic_id','')} {li.get('sku','')} {li.get('description','')}"
        if pat.search(blob):
            return True
    return False


def _flag(code, confidence, title, detail, proposed=None):
    return {"code": code, "confidence": confidence, "source": "m-sheet",
            "title": title, "detail": detail, "proposed": proposed}


def reconcile(msheet: Dict[str, Any], bom: Dict[str, Any]) -> List[Dict[str, Any]]:
    flags: List[Dict[str, Any]] = []
    if not msheet or not msheet.get("has_text_layer"):
        return flags

    systems = msheet.get("equipment") or []
    bom_ids = _bom_equipment_ids(bom)

    # 1. Equipment cross-check — every scheduled unit should be in the BOM.
    for s in systems:
        for role, model in (("condenser", s.get("condenser_model")),
                            ("air handler", s.get("ahu_model"))):
            if model and not _model_in_bom(model, bom_ids):
                flags.append(_flag(
                    "equipment_mismatch", "high",
                    f"M-sheet {s.get('system_tag')} lists a {role} "
                    f"({model}) that isn't in the BOM",
                    "The mechanical schedule and the BOM disagree on "
                    "equipment — verify the design file matches the schedule."))

    condensers = [s for s in systems if s.get("condenser_model")]
    ahus = [s for s in systems if s.get("ahu_model")]

    # 2. Refrigerant line sets — one per condenser, using the schedule's dims.
    if condensers and not _bom_has_keyword(bom, "refriger", "line set", "lineset"):
        for s in condensers:
            dims = s.get("refrig_pipe_dim_in")
            rtype = s.get("refrigerant_type")
            flags.append(_flag(
                "missing_refrigerant", "high",
                f"Refrigerant line set for {s.get('system_tag')} — not in the BOM",
                f"M-sheet specifies pipe dims {dims or '(see schedule)'}"
                f"{' , ' + rtype if rtype else ''}. Length = air-handler ↔ "
                "condenser distance (from the M-sheet).",
                proposed={"add": "refrigerant_line_set",
                          "system": s.get("system_tag"),
                          "pipe_dim_in": dims, "refrigerant_type": rtype}))

    # 3. Condensate drain — one per air handler (schedule shows the detail).
    if ahus and (msheet.get("detail_accessories") or {}).get("condensate_trap") \
            and not _bom_has_keyword(bom, "condensate", "drain", "pvc drain"):
        flags.append(_flag(
            "missing_condensate", "medium",
            f"Condensate drain — not in the BOM ({len(ahus)} air handler(s))",
            "M-sheet carries the condensate drain/trap detail. Standard: one "
            "PVC drain run per air handler.",
            proposed={"add": "condensate_drain", "per": "air_handler",
                      "count": len(ahus)}))

    # 4. Support straps / clamps — schedule shows the mounting details.
    acc = msheet.get("detail_accessories") or {}
    if (acc.get("hurricane_strap") or acc.get("isomode_pad")) \
            and not _bom_has_keyword(bom, "strap", "clamp", "isomode", "hanger"):
        flags.append(_flag(
            "missing_straps", "low",
            "Support straps / clamps — not in the BOM",
            "M-sheet shows mounting details (hurricane strap / isomode pad). "
            "Rate per run + trunk footage is still to be confirmed with Richard.",
            proposed={"add": "support_straps"}))

    # 5. Grille sizes — replace the 12x12 auto-lump with the schedule's real
    #    neck sizes (Richard #1, fixed at the source).
    pf = bom.get("register_preflight") or {}
    devices = msheet.get("air_devices") or []
    if pf.get("auto_count") and devices:
        from collections import Counter
        by = dict(sorted(Counter(d.get("neck_in") for d in devices
                                 if d.get("neck_in")).items()))
        flags.append(_flag(
            "grille_true_sizes", "medium",
            "M-sheet has real grille/diffuser sizes — the .rup used the 12x12 default",
            f"{pf.get('auto_count')} of {pf.get('total')} register records are "
            f"auto-sized (12x12 default). M-sheet air devices by neck size: {by} "
            "(best-effort read). Use these to replace the lumped grille line.",
            proposed={"replace": "auto_sized_grilles", "neck_size_counts": by}))

    return flags
