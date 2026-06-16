"""
bom_from_rup.py — Day-16: best-effort .rup binary → BOM line items.

Tom's repeated ask in the Day-14 meeting: drop the .rup straight onto the
page and get a BOM. The deterministic builder (bom_from_wrightsoft.py)
takes the Wrightsoft generic-parts EXPORT (a CSV/XLS that contractors
produce by clicking File → Bill of Materials → Save As in Wrightsoft).
Tom doesn't routinely run that export step — he just saves the .rup.

This module bridges the gap: parse the .rup binary (using the existing
utils.rup_parser surface that powers /diagnostics/rup-inspect) and shape
the data into the same {generic_id, quantity, description, section_hint}
contract that build_bom_from_wrightsoft_lines expects, so the rest of
the pipeline (catalog lookup, DFUnit enrichment, AHRI enrichment,
non-standard fitting flag, contractor overrides, branding, PDF/XLS
export) is reused unchanged.

What we CAN extract from the .rup deterministically:
  - Equipment instances (EQUIP blocks) — manufacturer + model number;
    drives both the catalog mapping and AHRI enrichment
  - Duct-system type mix (DTYPREF) — ShtMetl / VinlFlx / RectFbg counts
  - Register count + total CFM (DREGINFO) — proxy for register-line qty
  - Fitting INSTANCE count (FITNG block count) — emitted as a placeholder
    so reviewers see something to verify against the .xls export

What we CANNOT extract reliably (must surface to caller):
  - Per-fitting CODE (8E, 11H, etc. from Tom's standard template) — those
    live in the .xls export's tabular rollup, not in the .rup directly
  - Per-fitting QUANTITY — the .xls has these as aggregated counts;
    .rup has FITNG instances but no per-code grouping
  - Per-duct LF totals — needs binary decode of per-run segments;
    deferred from Day-14 (see _extract_duct_summary docstring)

Contract: build_lines_from_rup(file_bytes, source_name="") → list[dict]
returning [{generic_id, quantity, description, src?, section_hint?,
unit?}, ...] suitable to feed straight into
build_bom_from_wrightsoft_lines.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from utils.rup_parser import parse_rup_bytes

logger = logging.getLogger("procalcs_bom")


# Wrightsoft 4-char manufacturer codes for the common HVAC majors. These
# are what land in `Src` on the .xls export when Wrightsoft itself
# generates the BOM; we mirror them here so the catalog mapping path
# (lookup_skus_for_generic + the contractor-override lookup keyed by
# (supplier, sku)) lights up exactly the same as the .xls flow.
_MFR_NAME_TO_SRC: Dict[str, str] = {
    "Carrier":              "CARR",
    "Bryant":               "BRYA",
    "Trane":                "TRAN",
    "Lennox":               "LENX",
    "Goodman":              "GOOD",
    "Mitsubishi":           "MITS",
    "Mitsubishi Electric":  "MITS",
    "Fujitsu":              "FUJI",
    "Daikin":               "DAIK",
    "Rheem":                "RHEE",
    "Ruud":                 "RUUD",
    "LG":                   "LGEL",
    "LG Electronics":       "LGEL",
    "MRCOOL":               "MRCO",
}


def build_lines_from_rup(file_bytes: bytes,
                         source_name: str = "") -> List[Dict[str, Any]]:
    """Parse a .rup binary and project it into BOM line-item shape.

    Returns a list of dicts shaped for build_bom_from_wrightsoft_lines.
    Empty list when the .rup yields no usable equipment/duct info (very
    rare — even a sparse Manual D RUP has at least DTYPREF / FITNG /
    DREGINFO counts).
    """
    design = parse_rup_bytes(file_bytes, source_name=source_name)

    lines: List[Dict[str, Any]] = []

    # ── Equipment lines ────────────────────────────────────────────
    # Each EQUIP record contributes one BOM line. We use the model
    # number AS the generic_id so the existing AHRI + DFUnit lookups
    # (which key on model) fire transparently. The Wrightsoft 4-char
    # Src code goes into "src" so contractor overrides keyed by
    # (supplier, sku) resolve the same way they do on the .xls flow.
    for unit in design.get("equipment", []) or []:
        model = (unit.get("model") or "").strip()
        if not model:
            continue
        mfr_name = unit.get("manufacturer") or ""
        src = _MFR_NAME_TO_SRC.get(mfr_name) or _MFR_NAME_TO_SRC.get(
            mfr_name.title()) or "WSF"
        qty = float(unit.get("count") or 1)
        type_label = (unit.get("type") or "equipment").replace("_", " ").title()
        lines.append({
            "generic_id":   model,
            "quantity":     qty,
            "description":  f"{type_label} — {mfr_name} {model}".strip(" —"),
            "src":          src,
            "section_hint": "Equipment",
            "unit":         "EA",
        })

    # ── Duct-system summary lines ──────────────────────────────────
    # DTYPREF type_counts is a per-run breakdown (one count per duct
    # run). We emit one line per type as a placeholder so reviewers
    # see the system composition; quantity = run count (not LF).
    duct = design.get("duct_summary") or {}
    type_counts = duct.get("type_counts") or {}
    _DUCT_TYPE_LABEL = {
        "ShtMetl": "Sheet metal duct run",
        "VinlFlx": "Vinyl flex duct run",
        "RectFbg": "Rectangular fiberglass duct run",
        "RectMet": "Rectangular sheet metal duct run",
    }
    for code, count in type_counts.items():
        label = _DUCT_TYPE_LABEL.get(code, f"Duct run ({code})")
        lines.append({
            "generic_id":   f"DUCT-{code}",
            "quantity":     float(count),
            "description":  f"{label} — quantity from .rup DTYPREF",
            "src":          "WSF",
            "section_hint": "Duct System Equipment",
            "unit":         "RUN",
        })

    # ── Register count placeholder ─────────────────────────────────
    # DREGINFO instance count is a clean signal — one record per
    # register location in the design. Caller can apply contractor
    # overrides to refine the SKU/price; default surfaces as a single
    # generic line so reviewers see register count at a glance.
    registers = design.get("rooms") or []
    # The rooms collection from raw_rup_context is a richer source for
    # this; fall back to None when absent.
    raw = design.get("raw_rup_context") or ""
    reg_count = _count_registers_from_context(raw)
    if reg_count:
        lines.append({
            "generic_id":   "REGISTERS",
            "quantity":     float(reg_count),
            "description":  "Registers (count from .rup DREGINFO)",
            "src":          "WSF",
            "section_hint": "Duct System Equipment",
            "unit":         "EA",
        })

    # ── Fitting-instance placeholder ───────────────────────────────
    # FITNG count from the raw_rup_context. The .rup doesn't carry
    # per-code rollups (Tom's 8E/11H/etc. come from the .xls export's
    # tabular fitting section), so this is a single aggregate line
    # the reviewer uses to sanity-check the .xls export later.
    fit_count = _count_fittings_from_context(raw)
    if fit_count:
        lines.append({
            "generic_id":   "FITTINGS",
            "quantity":     float(fit_count),
            "description":  "Fittings (instance count from .rup FITNG; "
                            "see Wrightsoft BOM export for per-code rollup)",
            "src":          "WSF",
            "section_hint": "Duct System Equipment",
            "unit":         "EA",
        })

    logger.info(
        "Built %d BOM lines from .rup (%d equip, %d duct types, "
        "registers=%s, fittings=%s)",
        len(lines), len(design.get("equipment") or []),
        len(type_counts), reg_count or 0, fit_count or 0,
    )
    return lines


def _count_registers_from_context(raw: str) -> int:
    """Pull the DREGINFO count out of raw_rup_context. We use the
    narrative text rather than reparsing because the parser already
    counts and surfaces it; this avoids re-running _block_bodies on
    20 MB of file bytes."""
    if not raw:
        return 0
    for line in raw.splitlines():
        # Format: "  Register count (DREGINFO): 42"
        if "DREGINFO" in line:
            tail = line.rsplit(":", 1)[-1].strip()
            try:
                return int(tail)
            except ValueError:
                continue
    return 0


def _count_fittings_from_context(raw: str) -> int:
    """Same trick for FITNG instance count."""
    if not raw:
        return 0
    for line in raw.splitlines():
        if "FITNG" in line and "Fitting instances" in line:
            tail = line.rsplit(":", 1)[-1].strip()
            try:
                return int(tail)
            except ValueError:
                continue
    return 0
