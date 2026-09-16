"""qa_aggregator.py — cross-corpus QA candidate aggregation.

Consumes corpus_summary.json + pair_analysis.json + reliable_profile_draft.json.
Emits a ranked list of the actual questions we'd send Richard.

Design principle from the pilot on 79th Ct+BOM:
    * Per-file QA generation produces ~13 questions. Across 221
      matched projects that would be ~2,800 questions. Nobody
      answers 2,800 questions.
    * Aggregate at profile level: instead of asking "why Trane on
      zone A" and "why Trane on zone B", ask ONCE "Trane is your
      Split AC default — confirm?"
    * Only ask per-project when a project deviates from the profile
      pattern.

Question categories, in priority order:
    1. Catalog-supplement pricing (highest signal, easiest to answer):
       "SKU X appears on 175 of your projects with no Wrightsoft
        price. What's your per-unit price?"
    2. Supplier confirmation:
       "12 SKUs on 100% of your projects come from source RHEA.
        Confirm RHEA (Rheia) is Reliable's primary supplier?"
    3. Equipment brand confirmation:
       "94% of your projects use a Broan B150E75NT ERV. Standard,
        or project-dependent?"
    4. Heat strip pairing rule:
       "You add HKTSD05X1 to 79% of projects. This is the 5kW
        Goodman heat strip. What backup-heat load range does that
        cover?"
    5. Alt-equipment triggers:
       "72% of the time you use Goodman AHVE24BP1300A; 11% of the
        time you switch to Daikin DFVE24BP1400A. What triggers the
        Daikin choice?"

Output: scratchpad/qa_aggregate.json + scratchpad/qa_aggregate.md
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-geraldvillaran-Projects-designer-desktop"
    "/b3565f6f-f7f2-4a38-afa8-d431cb93c7b4/scratchpad"
)


def main():
    profile = json.loads((SCRATCH / "reliable_profile_draft.json").read_text())
    pair_analysis = json.loads((SCRATCH / "pair_analysis.json").read_text())

    qas = []

    # ── Category 1: Catalog-supplement pricing ─────────────────────
    for gap in profile["catalog_gap_needs_pricing"][:30]:
        qas.append({
            "priority": 1,
            "category": "catalog_pricing",
            "sku": gap["sku"],
            "context": {
                "occurrences": gap["occurrences"],
                "appearance_pct": gap["appearance_pct"],
                "source": gap["source"],
                "description": gap["description"],
            },
            "question": (
                f"**{gap['sku']}** ({gap['description']}) appears on "
                f"**{gap['occurrences']} of your projects "
                f"({gap['appearance_pct']}%)** but Wrightsoft's default "
                f"catalog has no price for it. What does Reliable pay "
                f"per unit?"
            ),
            "answer_shape": "Dollar amount (freeform)",
            "impact": (
                f"Adds one row to Reliable's catalog supplement — "
                f"future BOMs will price this SKU correctly on "
                f"{gap['occurrences']} project variants."
            ),
        })

    # ── Category 2: Supplier confirmation ──────────────────────────
    sup_dist = profile["supplier_distribution_by_appearances"]
    if sup_dist:
        primary_sup = list(sup_dist.keys())[0]
        primary_data = sup_dist[primary_sup]
        qas.append({
            "priority": 2,
            "category": "supplier_confirmation",
            "sku": None,
            "context": {
                "primary_source": primary_sup,
                "share_pct": primary_data["share_pct"],
                "appearances": primary_data["appearances"],
            },
            "question": (
                f"Fitting-kit source **{primary_sup}** appears on "
                f"**{primary_data['share_pct']}%** of the appearances "
                f"in your archive ({primary_data['appearances']} total). "
                f"Is that Rheia (as it looks) or something else? And is "
                f"this Reliable's default supplier for ductwork fittings?"
            ),
            "answer_shape": "(a) Confirm Rheia default, "
                             "(b) It's a different supplier: __ (freeform), "
                             "(c) Depends on project — please explain the "
                             "rule (freeform).",
            "impact": (
                "Populates the primary supplier field on Reliable's "
                "contractor profile. Downstream: our BOM engine can "
                "flag when a project would need a different supplier."
            ),
        })

    # ── Category 3: Equipment brand confirmation ───────────────────
    for ub in profile["ubiquitous_equipment_90pct"]:
        qas.append({
            "priority": 3,
            "category": "ubiquitous_equipment_confirmation",
            "sku": ub["sku"],
            "context": {
                "description": ub["description"],
                "source": ub["source"],
                "appearance_pct": ub["appearance_pct"],
            },
            "question": (
                f"**{ub['sku']}** ({ub['description']}, {ub['source']}) "
                f"appears on **{ub['appearance_pct']}% of your projects**. "
                f"Is this the Reliable default for this component, or "
                f"does the client / house shape drive it?"
            ),
            "answer_shape": (
                "(a) Reliable default — always use unless client specifies "
                "otherwise, (b) Project-dependent, driven by __ (freeform), "
                "(c) Legacy — we've moved to __ recently (freeform)."
            ),
            "impact": (
                "Sets the default equipment SKU for this component on "
                "Reliable's profile. Un-built .rup files without an "
                "explicit selection get this as the presumed choice."
            ),
        })

    # ── Category 4: Heat strip pairing rule ────────────────────────
    heat_strip_skus = [e for e in profile["standard_equipment_60_90pct"]
                        if "hkt" in e["sku"].lower() or "hkst" in e["sku"].lower()]
    if heat_strip_skus:
        primary_hs = heat_strip_skus[0]
        alt_hs = heat_strip_skus[1] if len(heat_strip_skus) > 1 else None
        alt_note = (f" You also use **{alt_hs['sku']}** on "
                    f"{alt_hs['appearance_pct']}% of projects."
                    if alt_hs else "")
        qas.append({
            "priority": 4,
            "category": "heat_strip_pairing_rule",
            "sku": primary_hs["sku"],
            "context": {
                "primary_strip": primary_hs["sku"],
                "primary_appearance_pct": primary_hs["appearance_pct"],
                "alt_strip": alt_hs["sku"] if alt_hs else None,
                "alt_appearance_pct": alt_hs["appearance_pct"] if alt_hs else None,
            },
            "question": (
                f"Heat strip **{primary_hs['sku']}** ({primary_hs['description']}) "
                f"appears on **{primary_hs['appearance_pct']}%** of your "
                f"projects." + alt_note + " Per your earlier walkthrough, "
                f"heat strips aren't populated automatically in Wrightsoft "
                f"— you insert them manually per project. What rule "
                f"determines the strip size?"
            ),
            "answer_shape": (
                "(a) Fixed size for all projects: __, "
                "(b) Sized by Manual-J backup heat load — please give the "
                "BTU range per strip size (5kW = X-Y BTU, 8kW = Y-Z BTU), "
                "(c) Sized by primary heating capacity ratio, "
                "(d) Other (freeform)."
            ),
            "impact": (
                "The single most valuable rule to capture. Once this is "
                "in the profile, un-built .rup files can auto-populate "
                "the heat strip choice, closing the biggest gap "
                "identified in your walkthrough."
            ),
        })

    # ── Category 5: Alt-equipment triggers (Goodman↔Daikin) ────────
    equip_inv = pair_analysis["equipment_inventory"]
    # Look for pairs of similar equipment across brands
    for e in profile["ubiquitous_equipment_90pct"] + profile["standard_equipment_60_90pct"]:
        if e["source"] == "GOOD":
            # Search for a Daikin equivalent (similar description)
            daik_alt = next(
                (a for a in equip_inv
                 if a["typical_source"] == "DAIK"
                 and _similar_desc(a["description"], e["description"])),
                None,
            )
            if daik_alt and daik_alt["appearance_pct"] >= 5:
                qas.append({
                    "priority": 5,
                    "category": "alt_equipment_trigger",
                    "sku": e["sku"],
                    "context": {
                        "primary_sku": e["sku"],
                        "primary_pct": e["appearance_pct"],
                        "alt_sku": daik_alt["sku"],
                        "alt_pct": daik_alt["appearance_pct"],
                        "description": e["description"],
                    },
                    "question": (
                        f"You use **Goodman {e['sku']}** on "
                        f"{e['appearance_pct']}% of projects and "
                        f"**Daikin {daik_alt['sku']}** on "
                        f"{daik_alt['appearance_pct']}% "
                        f"for what looks like the same role "
                        f"({e['description']}). What triggers Daikin over Goodman?"
                    ),
                    "answer_shape": (
                        "(a) Client-specified brand, "
                        "(b) Model availability at design time, "
                        "(c) Home style / size (specify the trigger), "
                        "(d) Other (freeform)."
                    ),
                    "impact": (
                        "Adds a brand-selection rule to Reliable's profile. "
                        "Future BOMs can auto-select the correct alternate "
                        "when the trigger condition applies."
                    ),
                })

    # Deduplicate by (category, sku)
    seen = set()
    deduped = []
    for q in qas:
        key = (q["category"], q.get("sku"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)

    # Sort by priority, then by impact size
    deduped.sort(key=lambda q: (q["priority"], -(q["context"].get("occurrences") or 0)))

    (SCRATCH / "qa_aggregate.json").write_text(
        json.dumps({"total": len(deduped), "questions": deduped},
                    indent=2, default=str)
    )

    # ── Markdown summary ──────────────────────────────────────────
    md = []
    md.append("# Aggregated QA candidate list for Richard")
    md.append(f"### {len(deduped)} questions total, ranked by priority")
    md.append("")
    md.append(f"Derived from **{len(pair_analysis.get('sku_price_aggregates_top50', {}))} priced SKUs** "
              f"across **{pair_analysis['match_stats']['matched']} matched project pairs**. "
              "Each question is designed to be answered ONCE and unlock a rule "
              "that applies across all future projects with the same shape.")
    md.append("")

    by_cat = defaultdict(list)
    for q in deduped:
        by_cat[q["category"]].append(q)

    cat_order = [
        ("catalog_pricing", "1️⃣ Catalog pricing — highest signal per unit of Richard's time"),
        ("supplier_confirmation", "2️⃣ Supplier confirmation"),
        ("ubiquitous_equipment_confirmation", "3️⃣ Ubiquitous equipment defaults"),
        ("heat_strip_pairing_rule", "4️⃣ Heat strip pairing rule (highest-value single question)"),
        ("alt_equipment_trigger", "5️⃣ Alt-equipment brand triggers"),
    ]

    for cat, heading in cat_order:
        items = by_cat.get(cat, [])
        if not items:
            continue
        md.append(f"## {heading}")
        md.append(f"({len(items)} questions)")
        md.append("")
        for i, q in enumerate(items, 1):
            md.append(f"### {cat[:3].upper()}-{i}")
            md.append("")
            md.append(f"**Question**: {q['question']}")
            md.append("")
            md.append(f"**Expected answer shape**: {q['answer_shape']}")
            md.append("")
            md.append(f"*Impact if answered*: {q['impact']}")
            md.append("")
            md.append("---")
            md.append("")

    (SCRATCH / "qa_aggregate.md").write_text("\n".join(md))

    # ── Console summary ─────────────────────────────────────────
    print(f"QA questions total: {len(deduped)}")
    for cat, heading in cat_order:
        n = len(by_cat.get(cat, []))
        print(f"  {cat:<40} {n}")
    print()
    print("Top 5 by priority:")
    for q in deduped[:5]:
        print(f"  [P{q['priority']}] [{q['category']}]  {q['question'][:100]}")


def _similar_desc(a: str, b: str) -> bool:
    """Loose similarity for matching brand equivalents."""
    if not a or not b:
        return False
    a_low = a.lower()
    b_low = b.lower()
    keys = ["air handler", "condenser", "heat kit", "heat strip",
            "erv", "hrv", "furnace", "coil"]
    return any(k in a_low and k in b_low for k in keys)


if __name__ == "__main__":
    main()
