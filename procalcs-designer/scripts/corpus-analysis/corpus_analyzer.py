"""corpus_analyzer.py — parse every .rup in Richard's Zoho archive.

Reads ~/Procalcs/RUPs-from-zoho/, runs our structural parsers against
each .rup, aggregates equipment placements + priced-line summaries +
duct-geometry stats + BALDUCT CFMs.

Output: three JSON files in scratchpad/:
    corpus_summary.json      — per-file stats
    corpus_aggregates.json   — cross-file rollups (brand distribution,
                                catalog gap map, fitting frequencies)
    corpus_errors.json       — files that failed to parse

Runs incrementally — safe to re-run as new files land from the sync.
Skips already-analyzed files unless --force is passed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
from utils.rup_reader import RupReader
from utils.rup_rpitem_parser import has_priced_bom, parse_priced_lines
from utils.rup_equip_parser import parse_equipment
from utils.rup_duct_parser import parse_baldict
from utils.rup_duct_drawing_parser import parse_duct_segments

CORPUS_ROOT = Path("/Users/geraldvillaran/Procalcs/RUPs-from-zoho")
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-geraldvillaran-Projects-designer-desktop"
    "/b3565f6f-f7f2-4a38-afa8-d431cb93c7b4/scratchpad"
)
SUMMARY_PATH   = SCRATCH / "corpus_summary.json"
AGGS_PATH      = SCRATCH / "corpus_aggregates.json"
ERRORS_PATH    = SCRATCH / "corpus_errors.json"


def _analyze_one(path: Path) -> Dict[str, Any]:
    """Parse one .rup, return a stats dict."""
    with open(path, "rb") as f:
        reader = RupReader(f.read())

    is_built = has_priced_bom(reader)
    priced = parse_priced_lines(reader) if is_built else []
    equipment = parse_equipment(reader)
    balduct = parse_baldict(reader)
    segments = parse_duct_segments(reader)

    # Priced total (dedup by first occurrence of each part_no, mirroring
    # the QA pilot's convention — multi-investment copies bloat totals)
    first_by_pn: Dict[str, Dict[str, Any]] = {}
    for L in priced:
        first_by_pn.setdefault(L["part_no"], L)
    priced_total = sum(L["extended"] for L in first_by_pn.values())

    # Zero-priced parts — catalog-gap candidates
    zero_priced = [
        {"part_no": L["part_no"],
         "part_source": L["part_source"],
         "category_code": L["category_code"] or None,
         "description": L["description"],
         "quantity": L["quantity"]}
        for L in first_by_pn.values() if L["unit_price"] == 0.0
    ]

    # Equipment placement summary (dedup identical placements)
    equip_summary = []
    seen_equip = set()
    for e in equipment:
        key = (e.get("equipment_type"), e.get("condenser_model"),
               e.get("coil_model"))
        if key in seen_equip:
            continue
        seen_equip.add(key)
        equip_summary.append({
            "type": e.get("equipment_type"),
            "mfr": e.get("manufacturer"),
            "mfr_code": e.get("mfr_catalog_key"),
            "part_source": e.get("part_source"),
            "condenser": e.get("condenser_model"),
            "coil": e.get("coil_model"),
            "drawing_tag": e.get("drawing_tag"),
        })

    # Register CFM aggregate
    total_design_cfm = sum(r["cfm"] for r in balduct)
    register_count = len(balduct)

    # Duct segment aggregate
    total_duct_ft = sum(s["cut_length_ft"] for s in segments)
    duct_type_counts = Counter(s["shape"] for s in segments)

    return {
        "path": str(path.relative_to(CORPUS_ROOT)),
        "size_bytes": path.stat().st_size,
        "is_built": is_built,
        # Priced totals
        "priced_line_count_dedup": len(first_by_pn),
        "priced_line_count_raw": len(priced),
        "priced_total": round(priced_total, 2),
        "zero_priced_count": len(zero_priced),
        "zero_priced_items": zero_priced,
        # Equipment
        "equipment_count": len(equip_summary),
        "equipment": equip_summary,
        # Duct/registers
        "register_count": register_count,
        "total_design_cfm": round(total_design_cfm, 1),
        "duct_segment_count": len(segments),
        "total_duct_ft": round(total_duct_ft, 1),
        "duct_shape_counts": dict(duct_type_counts),
    }


def _load_prior(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"files": {}}
    return json.loads(path.read_text())


def _save(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


def _build_aggregates(files_by_path: Dict[str, Any]) -> Dict[str, Any]:
    """Cross-file rollups. Numbers Gerald can validate."""
    files = list(files_by_path.values())
    built = [f for f in files if f["is_built"]]

    # ── Corpus stats ────────────────────────────────────────────────
    stats = {
        "total_files":       len(files),
        "built_files":       len(built),
        "unbuilt_files":     len(files) - len(built),
        "total_size_bytes":  sum(f["size_bytes"] for f in files),
        "built_priced_total_median": None,
        "built_priced_total_p90":    None,
    }
    if built:
        totals = sorted(f["priced_total"] for f in built)
        stats["built_priced_total_median"] = round(totals[len(totals) // 2], 2)
        stats["built_priced_total_p90"] = round(
            totals[int(len(totals) * 0.9)], 2
        )
        stats["built_priced_total_sum"] = round(sum(totals), 2)

    # ── Client roots (top-level folder = developer/community) ───────
    client_counts = Counter(
        f["path"].split("/")[0] for f in files
    )

    # ── Equipment brand distribution across all builds ──────────────
    brand_counts: Counter = Counter()
    equipment_type_counts: Counter = Counter()
    condenser_model_counts: Counter = Counter()
    part_source_counts: Counter = Counter()

    for f in built:
        for e in f["equipment"]:
            if e.get("mfr"):
                brand_counts[e["mfr"]] += 1
            if e.get("type"):
                equipment_type_counts[e["type"]] += 1
            if e.get("condenser"):
                condenser_model_counts[e["condenser"]] += 1
            if e.get("part_source"):
                part_source_counts[e["part_source"]] += 1

    # ── Catalog gap map — every zero-priced SKU ranked by frequency ─
    zero_priced_freq: Counter = Counter()
    zero_priced_desc: Dict[str, str] = {}
    for f in built:
        for z in f["zero_priced_items"]:
            zero_priced_freq[z["part_no"]] += 1
            if z["part_no"] not in zero_priced_desc:
                zero_priced_desc[z["part_no"]] = z["description"]

    # ── Priced-part frequency — SKUs that appear on almost every file ──
    priced_part_appearances: Counter = Counter()
    for f in built:
        for z in f["zero_priced_items"]:
            pass  # zero-priced tracked separately
    # For priced parts, we need to re-derive — the per-file summary
    # doesn't list every priced SKU. Use file paths and re-parse later
    # for the "fitting kit" analysis; for now just skip.

    return {
        "stats": stats,
        "client_distribution": dict(client_counts.most_common()),
        "brand_distribution": dict(brand_counts.most_common()),
        "equipment_type_distribution": dict(equipment_type_counts.most_common()),
        "condenser_model_frequency_top20":
            dict(condenser_model_counts.most_common(20)),
        "part_source_distribution": dict(part_source_counts.most_common()),
        "catalog_gap_map_top50": [
            {"part_no": pn, "occurrences": count,
             "description": zero_priced_desc.get(pn, "")}
            for pn, count in zero_priced_freq.most_common(50)
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-analyze files even if already in summary")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N new analyses (for iterative runs)")
    args = parser.parse_args()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    summary = _load_prior(SUMMARY_PATH)
    errors = _load_prior(ERRORS_PATH)
    already_done = set(summary["files"].keys())

    rup_files = sorted(CORPUS_ROOT.rglob("*.rup"))
    print(f"Scanning {len(rup_files)} .rup files in {CORPUS_ROOT}")
    print(f"Previously analyzed: {len(already_done)}")

    new_analyses = 0
    t0 = time.time()
    for path in rup_files:
        rel = str(path.relative_to(CORPUS_ROOT))
        if rel in already_done and not args.force:
            continue
        try:
            summary["files"][rel] = _analyze_one(path)
            new_analyses += 1
            if new_analyses % 25 == 0:
                elapsed = time.time() - t0
                rate = new_analyses / elapsed
                print(f"  [{new_analyses}] {rel[-60:]}  ({rate:.1f} files/s)")
                _save(SUMMARY_PATH, summary)  # checkpoint
        except Exception as exc:  # noqa: BLE001
            errors["files"][rel] = {
                "error": str(exc),
                "traceback": traceback.format_exc()[-1000:],
            }
            print(f"  ERROR on {rel}: {exc}")
        if args.limit and new_analyses >= args.limit:
            break

    # Final save
    _save(SUMMARY_PATH, summary)
    _save(ERRORS_PATH, errors)
    # Build aggregates
    aggs = _build_aggregates(summary["files"])
    _save(AGGS_PATH, aggs)

    elapsed = time.time() - t0
    print()
    print(f"Done in {elapsed:.1f}s  (new: {new_analyses}, "
          f"errors: {len(errors['files'])})")
    print(f"  summary:    {SUMMARY_PATH}  ({len(summary['files'])} files)")
    print(f"  aggregates: {AGGS_PATH}")
    print(f"  errors:     {ERRORS_PATH}  ({len(errors['files'])})")
    print()
    st = aggs["stats"]
    print(f"Corpus size:   {st['total_files']} files, {st['built_files']} built")
    if st.get("built_priced_total_sum"):
        print(f"Priced totals: sum ${st['built_priced_total_sum']:,.2f}  "
              f"median ${st['built_priced_total_median']:,.2f}  "
              f"p90 ${st['built_priced_total_p90']:,.2f}")
    print("Client distribution (top 5):")
    for k, v in list(aggs["client_distribution"].items())[:5]:
        print(f"  {k:<40} {v}")
    print("Brand distribution:")
    for k, v in aggs["brand_distribution"].items():
        print(f"  {k:<20} {v}")


if __name__ == "__main__":
    main()
