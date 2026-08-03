"""profile_extractor.py — derive Reliable's ContractorProfile draft.

Consumes corpus_summary.json + pair_analysis.json. Emits:

    reliable_profile_draft.json — machine-readable ContractorProfile
                                  seed data ready to migrate to
                                  Firestore (client_profiles collection)

    reliable_profile_summary.md — human-readable summary for review

The profile fields we derive:
  - supplier defaults (from src distribution + fitting kit sources)
  - equipment brand hierarchy (from EQUIP mfr distribution)
  - fitting kit standards (SKUs on ≥80% of projects)
  - catalog supplement candidates (SKUs Wrightsoft has no price for,
    with median price when Reliable's Wrightsoft had a price we can
    infer)
  - typical project shape (median priced total, equipment count,
    duct footage, register count)
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-geraldvillaran-Projects-designer-desktop"
    "/b3565f6f-f7f2-4a38-afa8-d431cb93c7b4/scratchpad"
)


def main():
    corpus = json.loads((SCRATCH / "corpus_summary.json").read_text())
    pairs = json.loads((SCRATCH / "pair_analysis.json").read_text())

    files = corpus["files"]
    n_files = len(files)
    matched = pairs["match_stats"]["matched"]

    # ── Typical project shape (from all .rup files) ─────────────────
    priced_totals = sorted(f["priced_total"] for f in files.values())
    equip_counts = sorted(f["equipment_count"] for f in files.values())
    register_counts = sorted(f["register_count"] for f in files.values())
    duct_fts = sorted(f["total_duct_ft"] for f in files.values())

    def _stats(vals):
        if not vals:
            return {}
        return {
            "min": vals[0],
            "median": vals[len(vals) // 2],
            "p90": vals[int(len(vals) * 0.9)],
            "max": vals[-1],
            "mean": round(statistics.mean(vals), 2),
        }

    project_shape = {
        "priced_total_dollars": _stats(priced_totals),
        "equipment_count":      _stats(equip_counts),
        "register_count":       _stats(register_counts),
        "total_duct_ft":        _stats(duct_fts),
    }

    # ── Supplier distribution across the fitting kit ────────────────
    fitting_kit_80 = pairs["fitting_kit_80pct"]
    supplier_counter: Counter = Counter()
    for e in fitting_kit_80:
        supplier_counter[e["typical_source"]] += e["appearances"]
    supplier_distribution = {
        k: {"appearances": v, "share_pct": round(v / sum(supplier_counter.values()) * 100, 1)
             if supplier_counter else 0}
        for k, v in supplier_counter.most_common()
    }

    # ── Equipment brand tiers ─────────────────────────────────────
    equip_inv = pairs["equipment_inventory"]
    brand_totals: Counter = Counter()
    for e in equip_inv:
        brand_totals[e["typical_source"]] += e["appearances"]
    total_brand_placements = sum(brand_totals.values())
    equipment_brand_tiers = {
        k: {"placements": v,
             "share_pct": round(v / total_brand_placements * 100, 1)
             if total_brand_placements else 0}
        for k, v in brand_totals.most_common()
    }

    # ── Ubiquitous equipment (≥90% appearance) ─────────────────────
    ubiquitous_equipment = [
        {"sku": e["sku"], "description": e["description"],
         "source": e["typical_source"],
         "appearance_pct": e["appearance_pct"],
         "has_wrightsoft_price": e["has_wrightsoft_price"]}
        for e in equip_inv if e["appearance_pct"] >= 90
    ]

    # ── Standard equipment options (60-90% appearance) ─────────────
    standard_equipment = [
        {"sku": e["sku"], "description": e["description"],
         "source": e["typical_source"],
         "appearance_pct": e["appearance_pct"],
         "has_wrightsoft_price": e["has_wrightsoft_price"]}
        for e in equip_inv if 60 <= e["appearance_pct"] < 90
    ]

    # ── Catalog gap map — SKUs without Wrightsoft prices ─────────
    catalog_gap = [
        {"sku": e["sku"], "description": e["description"],
         "source": e["typical_source"],
         "appearance_pct": e["appearance_pct"],
         "occurrences": e["appearances"],
         "needs_pricing": True}
        for e in fitting_kit_80 + equip_inv
        if not e["has_wrightsoft_price"]
    ]
    # Dedup by SKU
    seen = set()
    catalog_gap_dedup = []
    for c in catalog_gap:
        if c["sku"] in seen:
            continue
        seen.add(c["sku"])
        catalog_gap_dedup.append(c)
    catalog_gap_dedup.sort(key=lambda x: -x["occurrences"])

    # ── Known Wrightsoft prices we can seed ────────────────────────
    known_prices = []
    for sku, agg in pairs["sku_price_aggregates_top50"].items():
        known_prices.append({
            "sku": sku, "description": agg["description"],
            "median_price": agg["median_price"],
            "min_price": agg["min_price"],
            "max_price": agg["max_price"],
            "sample_count": agg["sample_count"],
            "source": (list(agg["source_distribution"].keys())[0]
                        if agg["source_distribution"] else ""),
        })

    profile = {
        "contractor_profile_id": "reliable-heating-and-cooling",
        "contractor_name": "Reliable Heating and Cooling",
        "corpus_source": {
            "total_files_analyzed": n_files,
            "matched_pairs": matched,
            "sync_status": "partial — sync still in progress",
            "analyzed_at": "2026-07-14 overnight run",
        },
        "typical_project_shape": project_shape,
        "supplier_distribution_by_appearances": supplier_distribution,
        "equipment_brand_tiers": equipment_brand_tiers,
        "ubiquitous_equipment_90pct": ubiquitous_equipment,
        "standard_equipment_60_90pct": standard_equipment,
        "fitting_kit_80pct": fitting_kit_80[:20],
        "catalog_gap_needs_pricing": catalog_gap_dedup[:40],
        "known_wrightsoft_prices_top30": known_prices[:30],
    }

    (SCRATCH / "reliable_profile_draft.json").write_text(
        json.dumps(profile, indent=2, default=str)
    )

    # ── Human-readable summary ─────────────────────────────────────
    md = []
    md.append("# Reliable Heating and Cooling — Contractor Profile Draft")
    md.append(f"### Derived from {n_files} `.rup` files "
               f"({matched} matched `.xls` pairs) · {n_files} priced")
    md.append("")
    md.append("**Corpus caveat**: sync was in progress when this ran. "
              "Final numbers may shift once the full ~1,500 file archive "
              "syncs. Ratios and rankings should be stable — absolute "
              "counts will grow.")
    md.append("")
    md.append("## Typical project shape")
    md.append("")
    md.append("| Metric | Min | Median | P90 | Max | Mean |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for name, stats in project_shape.items():
        md.append(f"| {name} | "
                   f"{stats['min']} | "
                   f"{stats['median']} | "
                   f"{stats['p90']} | "
                   f"{stats['max']} | "
                   f"{stats['mean']} |")
    md.append("")
    md.append("## Supplier distribution across fitting kit")
    md.append("")
    for src, data in supplier_distribution.items():
        md.append(f"- **{src}** — {data['appearances']} appearances "
                   f"({data['share_pct']}%)")
    md.append("")
    md.append("## Equipment brand tiers")
    md.append("")
    for brand, data in equipment_brand_tiers.items():
        md.append(f"- **{brand}** — {data['placements']} placements "
                   f"({data['share_pct']}%)")
    md.append("")
    md.append("## Ubiquitous equipment (≥90% of projects)")
    md.append("")
    md.append("| SKU | Description | Source | Appearance % | Has WS price? |")
    md.append("|---|---|---|---:|---|")
    for e in ubiquitous_equipment:
        md.append(f"| `{e['sku']}` | {e['description']} | {e['source']} | "
                   f"{e['appearance_pct']}% | "
                   f"{'yes' if e['has_wrightsoft_price'] else '**no — need Reliable pricing**'} |")
    md.append("")
    md.append("## Standard equipment options (60-90% of projects)")
    md.append("")
    md.append("| SKU | Description | Source | Appearance % | Has WS price? |")
    md.append("|---|---|---|---:|---|")
    for e in standard_equipment:
        md.append(f"| `{e['sku']}` | {e['description']} | {e['source']} | "
                   f"{e['appearance_pct']}% | "
                   f"{'yes' if e['has_wrightsoft_price'] else '**no — need Reliable pricing**'} |")
    md.append("")
    md.append("## Fitting kit — top 20 SKUs on ≥80% of projects")
    md.append("")
    md.append("| SKU | Description | Source | Appearance % | Median price |")
    md.append("|---|---|---|---:|---:|")
    for e in fitting_kit_80[:20]:
        p = f"${e['typical_price']:.2f}" if e["typical_price"] else "**needs pricing**"
        md.append(f"| `{e['sku']}` | {e['description'][:50]} | "
                   f"{e['typical_source']} | {e['appearance_pct']}% | {p} |")
    md.append("")
    md.append(f"## Catalog gap — top 40 SKUs needing Reliable pricing")
    md.append("")
    md.append(f"Total gap candidates: **{len(catalog_gap_dedup)}** SKUs. "
              "Each is a real part Reliable ships but Wrightsoft's default "
              "catalog doesn't price. These are the highest-leverage "
              "questions to send Richard — every answer becomes a row "
              "in Reliable's catalog supplement.")
    md.append("")
    md.append("| SKU | Description | Source | Occurrences | Appearance % |")
    md.append("|---|---|---|---:|---:|")
    for c in catalog_gap_dedup[:40]:
        md.append(f"| `{c['sku']}` | {c['description'][:50]} | "
                   f"{c['source']} | {c['occurrences']} | {c['appearance_pct']}% |")
    md.append("")

    (SCRATCH / "reliable_profile_summary.md").write_text("\n".join(md))
    print(f"Written:")
    print(f"  reliable_profile_draft.json   ({len(catalog_gap_dedup)} gap SKUs)")
    print(f"  reliable_profile_summary.md   ({len(md)} lines)")


if __name__ == "__main__":
    main()
