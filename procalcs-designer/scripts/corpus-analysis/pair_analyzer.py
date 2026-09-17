"""pair_analyzer.py — cross-reference .rup + .xls pairs across the corpus.

Reads the corpus_summary.json produced by corpus_analyzer.py, then
walks the archive again matching each .rup to its likely .xls pair
(same folder, same stem — the pairing rule in the sync script).

For each matched pair, parses the .xls to extract the actual line
items Reliable emits, then joins to the .rup's RPITEM data to find:

  1. Equipment SKUs Reliable uses (with quantities per project)
  2. Fitting/duct SKUs Reliable uses (with unit prices from Wrightsoft
     when present, quantities always)
  3. Catalog-gap items: SKUs the .xls carries with no wrightsoft_price
     — those are Reliable's own catalog entries (Goodman equipment,
     custom items) that we need Richard's pricing for.
  4. Priced items: SKUs where Reliable's Wrightsoft install had a
     price. Aggregate across projects to get canonical pricing.

Output: scratchpad/pair_analysis.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
from services.bom_from_wrightsoft import parse_wrightsoft_bom_rows

CORPUS_ROOT = Path("/Users/geraldvillaran/Procalcs/RUPs-from-zoho")
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-geraldvillaran-Projects-designer-desktop"
    "/b3565f6f-f7f2-4a38-afa8-d431cb93c7b4/scratchpad"
)


def _find_xls_for_rup(rup_path: Path) -> Optional[Path]:
    """Best-effort .xls pair. Rule: same folder or sibling Finals/
    folder, name shares a stem prefix. Prefer files named '... BOM.xls'."""
    rup_stem = rup_path.stem  # without .rup
    stem_lc = rup_stem.lower()

    # Search current folder first, then parent (Finals ↔ Working
    # Drawings sibling structure is common in Richard's archive)
    candidates: List[Path] = []
    for folder in (rup_path.parent, rup_path.parent.parent, rup_path.parent.parent.parent):
        if not folder.exists():
            continue
        for xls in folder.glob("*.xls"):
            candidates.append(xls)
        for xls in folder.glob("*.xlsx"):
            candidates.append(xls)

    # Score each: prefer stem-match + " BOM" in filename
    def score(x: Path) -> int:
        s = x.stem.lower()
        pts = 0
        # Full stem match minus " bom" suffix
        s_clean = s.replace(" bom", "").strip()
        stem_clean = stem_lc.replace(" load calcs", "").strip()
        if s_clean == stem_clean:
            pts += 100
        elif s_clean in stem_clean or stem_clean in s_clean:
            pts += 50
        if "bom" in s:
            pts += 20
        # Depth penalty — prefer same folder over parent's
        rel_up = 0
        try:
            rel_up = len(rup_path.relative_to(x.parent).parts) - 1
        except ValueError:
            rel_up = 5
        pts -= rel_up * 5
        return pts

    if not candidates:
        return None
    best = max(candidates, key=score)
    if score(best) < 20:  # too weak — no confident match
        return None
    return best


def _analyze_pair(rup_relpath: str, rup_summary: Dict[str, Any]) -> Dict[str, Any]:
    """Load the paired .xls, parse it, join to rup_summary data.
    Returns a per-pair analysis dict."""
    rup_path = CORPUS_ROOT / rup_relpath
    xls_path = _find_xls_for_rup(rup_path)

    result: Dict[str, Any] = {
        "rup_path": rup_relpath,
        "xls_path": None,
        "xls_rows": 0,
        "xls_equipment": [],
        "xls_priced_lines": [],
        "xls_unpriced_lines": [],
        "sku_prices_from_xls": {},  # sku → unit_price (Reliable's)
        "sku_sources_from_xls": {},  # sku → src (GOOD/DAIK/WSF/PGM)
    }
    if xls_path is None:
        return result

    result["xls_path"] = str(xls_path.relative_to(CORPUS_ROOT))
    try:
        rows = parse_wrightsoft_bom_rows(xls_path.read_bytes(),
                                          filename=xls_path.name)
    except Exception:  # noqa: BLE001
        result["xls_error"] = traceback.format_exc()[-500:]
        return result

    result["xls_rows"] = len(rows)
    for r in rows:
        sku = (r.get("generic_id") or "").strip()
        if not sku:
            continue
        price = r.get("wrightsoft_price")
        qty = r.get("quantity") or 0
        src = r.get("src") or ""
        section = r.get("section_hint") or ""
        desc = r.get("description") or ""

        if price is not None and price > 0:
            result["xls_priced_lines"].append(
                {"sku": sku, "qty": qty, "unit_price": price,
                 "src": src, "section": section, "description": desc}
            )
            result["sku_prices_from_xls"][sku] = price
        else:
            result["xls_unpriced_lines"].append(
                {"sku": sku, "qty": qty, "src": src,
                 "section": section, "description": desc}
            )

        result["sku_sources_from_xls"][sku] = src
        if section == "Equipment":
            result["xls_equipment"].append(
                {"sku": sku, "qty": qty, "src": src, "description": desc,
                 "unit_price": price}
            )
    return result


def main():
    summary_path = SCRATCH / "corpus_summary.json"
    if not summary_path.exists():
        print("corpus_summary.json not found — run corpus_analyzer.py first")
        sys.exit(1)

    corpus = json.loads(summary_path.read_text())
    files = corpus["files"]

    print(f"Analyzing pairs for {len(files)} .rup files...")

    pairs: Dict[str, Any] = {}
    matched = 0
    unmatched = 0

    # Aggregates we'll compute across all matched pairs
    sku_price_samples: Dict[str, List[float]] = defaultdict(list)
    sku_source_counter: Dict[str, Counter] = defaultdict(Counter)
    sku_appearance_count: Counter = Counter()
    sku_desc: Dict[str, str] = {}
    equipment_sku_freq: Counter = Counter()

    for rup_relpath in files:
        pa = _analyze_pair(rup_relpath, files[rup_relpath])
        pairs[rup_relpath] = pa
        if pa["xls_path"]:
            matched += 1
        else:
            unmatched += 1
            continue

        for sku, price in pa["sku_prices_from_xls"].items():
            sku_price_samples[sku].append(price)
        for sku, src in pa["sku_sources_from_xls"].items():
            sku_source_counter[sku][src] += 1
        for row in pa["xls_priced_lines"] + pa["xls_unpriced_lines"]:
            sku_appearance_count[row["sku"]] += 1
            if row["sku"] not in sku_desc and row.get("description"):
                sku_desc[row["sku"]] = row["description"]
        for e in pa["xls_equipment"]:
            equipment_sku_freq[e["sku"]] += 1

    print(f"Matched: {matched}  Unmatched: {unmatched}")

    # ── SKU pricing aggregates ─────────────────────────────────────
    price_agg = {}
    for sku, samples in sku_price_samples.items():
        samples.sort()
        price_agg[sku] = {
            "sample_count": len(samples),
            "median_price": samples[len(samples) // 2],
            "min_price": samples[0],
            "max_price": samples[-1],
            "source_distribution":
                dict(sku_source_counter[sku].most_common()),
            "description": sku_desc.get(sku, ""),
        }

    # ── Fitting kit — SKUs on ≥50% of files ─────────────────────────
    threshold_50 = matched * 0.5
    threshold_80 = matched * 0.8
    fitting_kit_50 = []
    fitting_kit_80 = []
    for sku, count in sku_appearance_count.most_common():
        entry = {
            "sku": sku,
            "appearances": count,
            "appearance_pct": round(count / matched * 100, 1) if matched else 0,
            "description": sku_desc.get(sku, ""),
            "typical_source":
                sku_source_counter[sku].most_common(1)[0][0]
                if sku_source_counter[sku] else "",
            "has_wrightsoft_price": sku in price_agg,
            "typical_price": price_agg[sku]["median_price"] if sku in price_agg else None,
        }
        if count >= threshold_80:
            fitting_kit_80.append(entry)
        if count >= threshold_50:
            fitting_kit_50.append(entry)

    # ── Equipment inventory (from xls Equipment section) ────────────
    equipment_inventory = [
        {"sku": sku, "appearances": count,
         "appearance_pct": round(count / matched * 100, 1) if matched else 0,
         "description": sku_desc.get(sku, ""),
         "typical_source":
             sku_source_counter[sku].most_common(1)[0][0]
             if sku_source_counter[sku] else "",
         "has_wrightsoft_price": sku in price_agg,
         "typical_price": price_agg[sku]["median_price"] if sku in price_agg else None,
        }
        for sku, count in equipment_sku_freq.most_common()
    ]

    output = {
        "match_stats": {"matched": matched, "unmatched": unmatched,
                          "total": len(files)},
        "sku_price_aggregates_top50": {
            sku: agg for sku, agg in sorted(
                price_agg.items(), key=lambda kv: -sku_appearance_count[kv[0]]
            )[:50]
        },
        "fitting_kit_80pct": fitting_kit_80,
        "fitting_kit_50pct": fitting_kit_50,
        "equipment_inventory": equipment_inventory,
        "unmatched_examples": [
            p for p, v in list(pairs.items())[:10] if not v["xls_path"]
        ],
    }

    out_path = SCRATCH / "pair_analysis.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))

    print()
    print(f"pair_analysis.json → {out_path}")
    print(f"  fitting kit (80% appearance): {len(fitting_kit_80)} SKUs")
    print(f"  fitting kit (50% appearance): {len(fitting_kit_50)} SKUs")
    print(f"  equipment inventory:          {len(equipment_inventory)} SKUs")
    print()
    print("Top 10 fitting kit SKUs (≥80% appearance):")
    for e in fitting_kit_80[:10]:
        price_note = (f" @${e['typical_price']:.2f}"
                       if e["typical_price"] else " (no WS price)")
        print(f"  {e['sku']:<20} {e['appearances']:>4}× ({e['appearance_pct']:>5}%)"
              f" src={e['typical_source']:<5}{price_note}")
    print()
    print("Top 10 equipment SKUs:")
    for e in equipment_inventory[:10]:
        price_note = (f" @${e['typical_price']:.2f}"
                       if e["typical_price"] else " (no WS price — Reliable's catalog needed)")
        print(f"  {e['sku']:<25} {e['appearances']:>4}× ({e['appearance_pct']:>5}%)"
              f" src={e['typical_source']:<5}{price_note}")


if __name__ == "__main__":
    main()
