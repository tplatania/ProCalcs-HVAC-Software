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
from utils.rup_reader import RupReader
from utils.rup_rpitem_parser import has_priced_bom, parse_priced_lines
from utils.rup_equip_parser import parse_equipment
from utils.rup_duct_parser import parse_baldict
from utils.rup_duct_geometry import (
    is_geometry_join_available, join_duct_geometry,
)

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


import json as _json
import os as _os
import re as _re

_PLAN_RE = _re.compile(r"\b([TVE]\d{3}R?)(?:\s*v?[\d.]+)?\b", _re.I)
_MEMO_SKU_DESC = {
    "10-01-010": "3-in ferrule", "20-01-010": '4" Ferrule',
    "10-01-020": "Elbow Extension", "10-01-030": "Coupler",
    "00-00-240": "Hanger Bar Assembly",
    "10-01-210": "Pass Through Boot Assembly",
    "10-04-090": "Slotted Diffuser", "20-00-190": "4-in Duct Uninsulated",
    "10-01-040": "Duct board Take Off Inside",
    "10-01-050": "Duct board Take Off Outside",
}
_memo_cache: Dict[str, Any] = {}


def _plan_memo_lookup(source_name: str):
    """Yield (sku, qty, agreement) from the per-plan memo for the plan
    code found in the filename. Community disambiguation: when the
    same plan code exists in several communities, require a community
    token from the memo key to appear in the filename; a unique plan
    code matches directly. Missing memo file → no-op."""
    global _memo_cache
    if not _memo_cache:
        path = _os.environ.get("PLAN_MEMO_PATH", "")
        try:
            _memo_cache = _json.loads(open(path).read()) if path else {"__missing__": 1}
        except Exception:  # noqa: BLE001
            _memo_cache = {"__missing__": 1}
    if "__missing__" in _memo_cache:
        return
    m = _PLAN_RE.search(source_name or "")
    if not m:
        return
    plan = m.group(1).upper()
    hits = [k for k in _memo_cache if k.endswith(f"::{plan}")]
    if len(hits) > 1:
        low = (source_name or "").lower()
        narrowed = [k for k in hits
                    if any(tok in low for tok in k.split("::")[0].lower().split()[:2])]
        if narrowed:
            hits = narrowed
    if not hits:
        return
    if len(hits) == 1:
        for sku, e in _memo_cache[hits[0]].items():
            if e.get("agreement", 0) >= 0.9 and e.get("n", 0) >= 2:
                yield sku, e["qty"], e["agreement"]
        return
    # Ambiguous community (lot filenames often omit it) — merge across
    # communities and emit only SKUs whose quantity AGREES everywhere
    # (builders reuse the same plan across communities; e.g. T076 is
    # identical in Glades and Riverwalk). Disagreement → skip the SKU.
    all_skus = set().union(*(_memo_cache[k].keys() for k in hits))
    for sku in sorted(all_skus):
        entries = [_memo_cache[k][sku] for k in hits if sku in _memo_cache[k]]
        if not entries or any(e.get("agreement", 0) < 0.9 or e.get("n", 0) < 2
                              for e in entries):
            continue
        qtys = {e["qty"] for e in entries}
        if len(qtys) == 1:
            yield sku, entries[0]["qty"], min(e["agreement"] for e in entries)


def build_lines_from_rup(file_bytes: bytes,
                         source_name: str = "",
                         rheia_takeoff: bool = False) -> List[Dict[str, Any]]:
    """Parse a .rup binary and project it into BOM line-item shape.

    Returns a list of dicts shaped for build_bom_from_wrightsoft_lines.
    Empty list when the .rup yields no usable equipment/duct info (very
    rare — even a sparse Manual D RUP has at least DTYPREF / FITNG /
    DREGINFO counts).

    Day-21 — three new structural extraction paths from the sister
    session's RUP_BINARY_FORMAT.md Increments 1-3:

    * **RPITEM/RPRPART** (§1) — when the .rup was built + saved inside
      Wrightsoft, it carries the FULL priced BOM as paired records
      with real per-code quantities and unit prices. When present we
      short-circuit the empirical duct/fitting placeholders and emit
      those authoritative lines directly.
    * **EQUIP** (§3) — placed equipment instances (Trane condenser +
      coil pair, BAYEA heat kits). Augments the empirical equipment
      extraction — fixes the Ally "0 equipment" bug the aligned
      reader had for weeks.
    * **BALDUCT** (§2) — per-register design CFM. Surfaced via the
      _rup_baldict attribute on the first line for the Duct Cuts card
      downstream consumer.
    """
    design = parse_rup_bytes(file_bytes, source_name=source_name)
    reader = RupReader(file_bytes)

    lines: List[Dict[str, Any]] = []

    # ── Equipment lines (structural EQUIP + empirical fallback) ──
    # Structural walk finds placed instances with matched condenser +
    # coil pairs across every manufacturer Wrightsoft names, no code
    # changes when a contractor uses Lennox or Bosch. Fixes Ally's
    # "0 equipment" bug and retires the day-18 mfr-double-marker
    # filter + the day-17 free-standing model regex scan.
    #
    # When structural returns non-empty we PREFER it over the
    # empirical result. When empty (older files, edge shapes), fall
    # back to the empirical equipment extraction so nothing regresses.
    structural_equipment = parse_equipment(reader)
    seen_models = set()
    if structural_equipment:
        for row in structural_equipment:
            cond = row["condenser_model"]
            coil = row.get("coil_model")
            mfr_name = row.get("manufacturer") or ""
            src = row.get("part_source") or _MFR_NAME_TO_SRC.get(mfr_name) \
                  or _MFR_NAME_TO_SRC.get(mfr_name.title()) or "WSF"
            type_label = row.get("equipment_type") or "Equipment"
            # Day-27 — quantity from the placed-instance count (2 identical
            # systems → qty 2). Defaults to 1 for older parser output.
            qty = float(row.get("quantity") or 1.0)
            primary = {
                "generic_id":   cond,
                "quantity":     qty,
                "description":  f"{type_label} — {mfr_name} {cond}".strip(" —"),
                "src":          src,
                "section_hint": "Equipment",
                "unit":         "EA",
            }
            # Day-29 — expert-ratified heat-strip policy (Richard,
            # q.heat_strip_rule): no standing rule exists; "1 per split
            # is general but not set in stone". A multi-count strip may
            # be real or Wrightsoft investment duplication (79th Ct: we
            # count 4, Richard says 3) — flag for review, never guess.
            # Condensers/AHUs are NOT flagged (multi-count confirmed
            # correct by Richard).
            if qty > 1 and "strip" in (type_label or "").lower():
                primary["verify_reason"] = (
                    f"{int(qty)} identical heat strips counted in the design "
                    "file — no standing per-strip rule (expert-confirmed); "
                    "verify the count for this project.")
            # Emit the primary (condenser) line
            lines.append(primary)
            seen_models.add(cond)
            # Emit the paired coil/AH line when present — same count as
            # the system it belongs to.
            if coil and coil != cond:
                lines.append({
                    "generic_id":   coil,
                    "quantity":     qty,
                    "description":  f"Air Handler — {mfr_name} {coil}".strip(" —"),
                    "src":          src,
                    "section_hint": "Equipment",
                    "unit":         "EA",
                })
                seen_models.add(coil)
    # Empirical safety net — only add models the structural pass didn't
    # already surface. Keeps regression coverage on file variants the
    # sister session's Increment 3 hasn't accounted for.
    for unit in design.get("equipment", []) or []:
        model = (unit.get("model") or "").strip()
        if not model or model in seen_models:
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

    # Day-16 follow-up — when DTYPREF is empty (common on Manual D /
    # ADU Ducts files where Wrightsoft didn't tag duct types), fall
    # back to round_diameters_present + rect_sizes_present so we still
    # surface the actual duct sizes the designer used. Quantity stays
    # at 1 per size as a placeholder — the .rup doesn't carry LF per
    # size without a full per-run binary decode (deferred).
    if not type_counts:
        for diam in (duct.get("round_diameters_present") or []):
            lines.append({
                "generic_id":   f"DUCT-ROUND-{diam}",
                "quantity":     1.0,
                "description":  f'Round duct — {diam}" diameter (size from .rup)',
                "src":          "WSF",
                "section_hint": "Duct System Equipment",
                "unit":         "SIZE",
            })
        for size in (duct.get("rect_sizes_present") or []):
            lines.append({
                "generic_id":   f"DUCT-RECT-{size}",
                "quantity":     1.0,
                "description":  f"Rectangular duct — {size}\" (size from .rup)",
                "src":          "WSF",
                "section_hint": "Duct System Equipment",
                "unit":         "SIZE",
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

    # ── Fittings — per-code rollup or synthetic aggregate ─────────
    # Day-21 Increment 1: when the .rup was built + saved in
    # Wrightsoft, RPITEM/RPRPART records carry the exact per-code
    # BOM lines with real quantities and unit prices from Wrightsoft
    # itself. Emit those as first-class lines and skip the synthetic
    # aggregate entirely — they retire it.
    fit_count = 0  # keeps the summary log valid whichever branch runs
    if has_priced_bom(reader):
        priced = parse_priced_lines(reader)
        # Day-28 — SUM quantities per part_no (was: keep first only).
        # Richard, SW 55th Ave: Wrightsoft's priced BOM (RPITEM) is the
        # authoritative bill and splits one duct size across zones into
        # multiple lines (DDVn04 = 49 + 77). Keeping only the first
        # under-counted every multi-zone size (49 shown vs 126 real).
        # RPITEM is a FINAL bill, not design alternatives, so duplicate
        # part_no rows are genuine and must be summed. First occurrence
        # keeps the metadata (desc/price/units); quantity + extended
        # accumulate.
        first_by_pn: Dict[str, dict] = {}
        for L in priced:
            pn = L["part_no"]
            if pn not in first_by_pn:
                first_by_pn[pn] = dict(L)
            else:
                agg = first_by_pn[pn]
                agg["quantity"] = (agg.get("quantity") or 0) + (L.get("quantity") or 0)
                agg["extended"] = (agg.get("extended") or 0) + (L.get("extended") or 0)
        for L in first_by_pn.values():
            lines.append({
                "generic_id":   L["part_no"],
                "quantity":     L["quantity"],
                "description":  L["description"] or L["category_label"]
                                or L["part_no"],
                "src":          L["part_source"] or "WSF",
                "section_hint": _section_hint_from_category(
                    L.get("category_code"), L.get("category_label")),
                "unit":         L["units"] or "EA",
                # `wrightsoft_price` is consumed by the existing
                # build_bom_from_wrightsoft_lines pricing pipeline as
                # a fallback when hosted catalog + CSV both miss —
                # setting it here surfaces Wrightsoft's own RPITEM
                # unit price on those otherwise-unpriced lines.
                # Keep `wrightsoft_unit_price`/`wrightsoft_extended`
                # for auditing/debugging; a follow-up should teach
                # the pricing pipeline to prefer these over hosted
                # catalog for built .rup files (RPITEM is
                # authoritative for those).
                "wrightsoft_price":      L["unit_price"],
                "wrightsoft_unit_price": L["unit_price"],
                "wrightsoft_extended":   L["extended"],
            })
        logger.info("rup: emitted %d per-code lines from RPITEM/RPRPART "
                    "(%d rows before dedup)", len(first_by_pn), len(priced))
    else:
        # Un-built .rup — no RPITEM records. Fall back to the
        # synthetic FITTINGS aggregate + surface an actionable hint
        # so the SPA can prompt "run Bill of Materials → save → re-
        # upload" for a fully priced BOM.
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

    # Day-16 follow-up — Manual D / ADU Ducts files have no equipment
    # by design. Tag the first line so the route handler can surface a
    # banner: "this looks like a ducts-only file — for a residential
    # BOM with equipment, upload a Manual J file instead."
    is_ducts_only = (len(design.get("equipment") or []) == 0
                       and not structural_equipment)
    if is_ducts_only and lines:
        lines[0]["rup_file_type_hint"] = (
            "no equipment found — this looks like a Manual D / "
            "ducts-only file. For the full residential BOM with "
            "equipment, upload a Manual J file."
        )
    # Day-21 — un-built .rup hint. When the file has none of the
    # RPITEM priced-BOM blocks, the contractor can unlock a fully
    # priced per-code output by running Wrightsoft's Bill of
    # Materials → save step once before uploading. Surface this on
    # the first line so the SPA can prompt.
    if not has_priced_bom(reader) and lines:
        lines[0].setdefault(
            "rup_unbuilt_hint",
            "This .rup was saved without a built Bill of Materials. "
            "For a fully priced per-code BOM, open the file in "
            "Wrightsoft → Bill of Materials → save → re-upload."
        )

    # Day-21 — BALDUCT (per-register design CFM). Surfaced on the
    # first line for the Duct Cuts card consumer to render alongside
    # cut lengths without needing to re-parse the .rup.
    baldict_rows = parse_baldict(reader)
    if baldict_rows and lines:
        lines[0].setdefault("rup_balduct", [
            {"label": r["label"], "cfm": r["cfm"], "id": r["id"]}
            for r in baldict_rows
        ])

    # Day-21 — per-run diameter + cut-length join (Increment 2b).
    # Currently a no-op stub; auto-activates when the sister session's
    # CSDuctOb/CRDuctOb spec lands and `is_geometry_join_available()`
    # flips to True. When active, the returned rows feed the un-built
    # geometry-recompute path (task L) which silently supersedes the
    # "build first" UX guardrail for un-built .rup drops.
    if is_geometry_join_available():
        geometry_rows = join_duct_geometry(reader)
        if geometry_rows and lines:
            lines[0].setdefault("rup_duct_geometry", geometry_rows)

    # Day-27 — per-piece duct RUNOUTS (individual cut pieces, one per
    # room/register). Richard's finding: the .rup carries flex duct as
    # many separate pieces, but line-items + duct_cuts_summary collapse
    # them into one total-footage line per size, so the review chat
    # could only see the collapsed number. These rows expose the real
    # individual pieces (room + family + length). IMPORTANT: the .rup
    # does NOT reliably encode each piece's DIAMETER (documented decode
    # gap in rup_duct_geometry), so we deliberately do NOT invent a
    # per-size split — pieces carry family + length + room only, and
    # per-diameter footage still comes from the priced BOM. The chat
    # agent is told exactly this so it never fabricates a per-size count.
    _FAMILY = {"VinlFlx": "Flex duct", "ShtMetl": "Sheet metal",
               "RectFbg": "Rect fiberglass"}
    try:
        from utils.rup_home_run_parser import parse_home_run_lengths
        _pieces = parse_home_run_lengths(reader)
    except Exception:  # noqa: BLE001
        _pieces = []
    if _pieces and lines:
        lines[0].setdefault("duct_runout_pieces", [
            {
                "room":      p.get("label"),
                "duct_code": p.get("duct_code"),
                "family":    _FAMILY.get(p.get("duct_code"), p.get("duct_code")),
                "length_ft": round(float(p.get("length_ft") or 0), 2),
            }
            for p in _pieces[:400]
        ])

    # Day-22 — Rheia register-driven takeoff v1. The Rheia duct-system
    # section is NOT in the .rup (byte-probe proven: Wrightsoft's Rheia
    # plugin derives it from drawing geometry at export time), so for
    # Rheia-system contractors we derive it ourselves. Validated on the
    # 20-pair reproduction pilot (repro_run_2026-07-15):
    #   boots total     = registers − 1   (exact on 14/14, then 20/20)
    #   diffusers total = registers − 1   (exact; ceil-diff == ceil-boot,
    #                                      slotted == sidewall boots)
    # The ceiling/sidewall SPLIT needs the drawing-geometry decode
    # (mount type per register); until then we use the corpus-median
    # ceiling share (~0.42) and flag the lines low-confidence so the
    # review UI renders them as needs-verification, not fact.
    #
    # Day-28 — PER-PROJECT gate (Richard, SW 55th Ave). rheia_takeoff
    # came from the CONTRACTOR PROFILE ("rheia" in supplier), so a Rheia
    # contractor's CONVENTIONAL jobs got 9 phantom Rheia lines + a
    # phantom ERV on every upload. Detection by *volume* of the priced
    # duct system (validated on 50 known-Rheia pairs + 2 conventional
    # files): a Rheia .rup prices only equipment + a 1-2 SKU duct stub
    # (Wrightsoft's Rheia plugin derives the real duct separately),
    # while a conventional job prices its FULL duct system (SW 55th=29,
    # 79th Ct=26 distinct DDVn/DRFg run SKUs; every Rheia pair had ≤2).
    # Threshold 5 sits in the gap with a 3-SKU margin above the Rheia
    # max, so it never suppresses a real Rheia takeoff.
    if rheia_takeoff:
        _duct_run_skus = {
            (l.get("generic_id") or "")
            for l in lines
            if (l.get("generic_id") or "").startswith(("DDVn", "DRFg"))
        }
        if len(_duct_run_skus) >= 5:
            logger.info("rup: %d conventional duct-run SKUs in priced BOM "
                        "— conventional project, suppressing Rheia takeoff",
                        len(_duct_run_skus))
            rheia_takeoff = False
    if rheia_takeoff:
        # Day-22b — home-run decode (DUCT block, per-runout routed
        # lengths). Runout count == boot-assembly count on every
        # ground-truth pair, and xls 10-00-190 footage == ceil(Σ
        # lengths) exactly on 14/20 (the rest are rup↔xls revision
        # skew). Prefer runouts over registers−1; fall back when the
        # DUCT block is absent.
        try:
            from utils.rup_home_run_parser import parse_home_run_lengths
            _runs = parse_home_run_lengths(reader)
        except Exception:  # noqa: BLE001
            _runs = []
        if _runs:
            import math
            total_ft = math.ceil(sum(r["length_ft"] for r in _runs))
            lines.append({
                "generic_id":   "10-00-190",
                "quantity":     float(total_ft),
                "description":  "3-in Duct Uninsulated",
                "src":          "RHEA",
                "section_hint": "Rheia Duct System Equipment",
                "unit":         "FT",
                "rup_derived":  "rheia_home_run_decode",
            })
            # Day-22c — duct-board takeoffs = home-run count, EXACT on
            # all 762 non-skewed ground-truth pairs (full-corpus run
            # 2026-07-15; integer ratio 1.000 on every pair). Two SKU
            # generations exist per community era; default to the
            # newer 041/051 — the community-level override belongs in
            # the contractor profile / per-plan memo, and either
            # generation is a 1-keystroke SKU correction in review.
            for gen_id, desc in (
                ("10-01-041", "Duct board Take Off Inside"),
                ("10-01-051", "Duct board Take Off Outside"),
            ):
                lines.append({
                    "generic_id":   gen_id,
                    "quantity":     float(len(_runs)),
                    "description":  desc,
                    "src":          "RHEA",
                    "section_hint": "Rheia Duct System Equipment",
                    "unit":         "EA",
                    "rup_derived":  "rheia_takeoff_eq_runs",
                })

        # Day-23 — per-plan fitting memo. Fitting hardware (ferrules,
        # elbows, couplers, hangers, pass-through boots, 4-in duct) is
        # per-plan constant (full-corpus finding, median within-plan
        # agreement 1.000). The memo — learned from prior BOMs of the
        # same community::plan — fills what geometry can't derive yet.
        # Holdout-validated: recall 0.652→0.739, precision flat.
        # Memo file: PLAN_MEMO_PATH (GCS-mounted on Cloud Run).
        # Generation pairs: the same part across the Rheia Phase-2
        # cutover (2022-07-01). The memo carries the plan's HISTORICAL
        # generation — authoritative for that plan — so it replaces a
        # rule-emitted counterpart instead of duplicating it.
        _GEN_PAIR = {"10-01-040": "10-01-041", "10-01-041": "10-01-040",
                     "10-01-050": "10-01-051", "10-01-051": "10-01-050",
                     "10-04-090": "10-04-091", "10-04-091": "10-04-090"}
        _emitted = {(l.get("generic_id") or "").upper() for l in lines}
        for sku, qty, agreement in _plan_memo_lookup(source_name):
            if sku.upper() in _emitted:
                continue
            counterpart = _GEN_PAIR.get(sku.upper())
            if counterpart and counterpart in _emitted:
                for l in lines:
                    if (l.get("generic_id") or "").upper() == counterpart:
                        l["generic_id"] = sku
                        l["quantity"] = float(qty)
                        l["rup_derived"] = f"plan_memo (agreement {agreement:.0%})"
                        break
                _emitted.add(sku.upper())
                continue
            lines.append({
                "generic_id":   sku,
                "quantity":     float(qty),
                "description":  _MEMO_SKU_DESC.get(sku, sku),
                "src":          "RHEA",
                "section_hint": "Rheia Duct System Equipment",
                "unit":         "FT" if sku.endswith("-190") else "EA",
                "rup_derived":  f"plan_memo (agreement {agreement:.0%})",
            })

        # Day-23 — ERV profile default: B150E75NT on 94.6% of the
        # corpus, absent from the .rup (added at proposal time).
        # Emitted flagged so review renders it as a default, not fact.
        if not any("B150E" in (l.get("generic_id") or "") for l in lines):
            lines.append({
                "generic_id":   "B150E75NT",
                "quantity":     1.0,
                "description":  "Energy Recovery Ventilator (profile default)",
                "src":          "BROAN",
                "section_hint": "Equipment",
                "unit":         "EA",
                "rup_derived":  "profile_default_erv",
            })
    if rheia_takeoff and (_runs or (baldict_rows and len(baldict_rows) >= 2)):
        n = len(_runs) if _runs else len(baldict_rows) - 1
        # Day-23 — exact mount split from DREGPERF (the .rup stores the
        # literal boot SKU per register; 92.6% exact triples on 1,076
        # pairs). Prior-based 0.42 split only as last-resort fallback.
        ceil = side = passthru = 0
        try:
            from utils.rup_home_run_parser import mount_counts
            mc = mount_counts(reader)
            ceil = mc.get("ceiling", 0)
            side = mc.get("sidewall", 0)
            passthru = mc.get("pass_through", 0)
        except Exception:  # noqa: BLE001
            pass
        if not (ceil or side or passthru):
            ceil = round(0.42 * n)
            side = n - ceil
        _already = {(l.get("generic_id") or "").upper() for l in lines}
        for gen_id, qty, desc in (
            ("10-01-220", ceil, "Ceiling Boot Assembly"),
            ("10-01-200", side, "High Sidewall Boot Assembly"),
            ("10-01-210", passthru, "Pass Through Boot Assembly"),
            ("10-04-230", ceil, "Ceiling Diffuser Assembly"),
            ("10-04-091", side + passthru, "Slotted Diffuser"),
        ):
            # Plan memo (exact copies from prior BOMs of this plan)
            # outranks the prior-based ceiling/sidewall split.
            if qty <= 0 or gen_id.upper() in _already:
                continue
            lines.append({
                "generic_id":   gen_id,
                "quantity":     float(qty),
                "description":  desc,
                "src":          "RHEA",
                "section_hint": "Rheia Duct System Equipment",
                "unit":         "EA",
                # Consumed by the SPA to render a low-confidence badge;
                # totals are exact, the ceiling/sidewall split is a
                # corpus prior pending the geometry decode.
                "rup_derived":  "rheia_register_rule_v1",
            })
        logger.info("rup: emitted Rheia register-rule lines "
                    "(registers=%d → boots/diffusers=%d, ceil=%d side=%d)",
                    len(baldict_rows), n, ceil, side)

    logger.info(
        "Built %d BOM lines from .rup (%d empirical equip, %d structural equip, "
        "%d duct types, registers=%s, fittings=%s, priced_bom=%s)",
        len(lines), len(design.get("equipment") or []),
        len(structural_equipment),
        len(type_counts), reg_count or 0, fit_count or 0,
        has_priced_bom(reader),
    )
    return lines


def _section_hint_from_category(category_code: str,
                                  category_label: str) -> str:
    """Map Wrightsoft's category code/label to our BOM section hint.

    WSFDCT (ducts), WSFFTR (fittings), and their kin all land under
    'Duct System Equipment'. Equipment lines have their own explicit
    section from the EQUIP path — this function only handles the
    RPITEM-derived duct/fitting lines.
    """
    if category_code and category_code.startswith("WSF"):
        return "Duct System Equipment"
    if category_label and "Equipment" in category_label:
        return category_label
    return "Duct System Equipment"


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
