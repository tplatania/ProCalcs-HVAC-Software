"""plan_memo_harvest.py — learn per-plan fitting quantities from all
existing BOMs (learning stream #1).

Theory (full-corpus finding): ferrule/elbow/coupler/hanger/boot-split
quantities are constant per plan code (same plan = same routing =
same joints). So: group the 1,076 scored pairs by (community, plan),
verify constancy, and emit a plan-memo lookup table the engine can
use to fill fitting hardware exactly for any known plan.

Outputs: plan_memo.json + plan_memo_report.md (constancy stats,
coverage: what fraction of corpus lots a memo covers).
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/Users/geraldvillaran/Procalcs/reliable-analysis-2026-07-14")
import repro_harness as H

OUT = Path(__file__).parent
PAIRS = OUT / "pairs.jsonl"

MEMO_SKUS = ["10-01-010", "20-01-010", "10-01-020", "10-01-030",
             "00-00-240", "10-01-220", "10-01-200", "10-01-210",
             "10-04-230", "10-04-091", "10-04-090",
             "10-01-041", "10-01-051", "10-01-040", "10-01-050",
             "10-00-190", "20-00-190"]

PLAN_RE = re.compile(r"\b([TVE]\d{3}R?)(?:\s*v?[\d.]+)?\b", re.I)


def plan_of(path: str) -> str | None:
    m = PLAN_RE.search(Path(path).stem)
    return m.group(1).upper() if m else None


def main():
    rows = [json.loads(l) for l in PAIRS.read_text().splitlines()]
    ok = [r for r in rows if r.get("xls_qty")]
    groups: dict[tuple, list] = defaultdict(list)
    unplanned = 0
    for r in ok:
        plan = plan_of(r["rup"]) or plan_of(r["xls"])
        if not plan:
            unplanned += 1
            continue
        groups[(r["community"], plan)].append(r)

    memo, report_rows = {}, []
    for (comm, plan), rs in sorted(groups.items()):
        entry, consts, varies = {}, 0, 0
        for sku in MEMO_SKUS:
            vals = [q for r in rs
                    if (q := (r["xls_qty"] or {}).get(sku)) is not None]
            if not vals:
                continue
            mode = Counter(vals).most_common(1)[0]
            share = mode[1] / len(vals)
            entry[sku] = {"qty": mode[0], "n": len(vals),
                          "agreement": round(share, 3)}
            if share >= 0.9:
                consts += 1
            else:
                varies += 1
        if entry:
            memo[f"{comm}::{plan}"] = entry
            report_rows.append((comm, plan, len(rs), consts, varies))

    (OUT / "plan_memo.json").write_text(json.dumps(memo, indent=1))

    # Coverage: of all canonical Finals rups (features.jsonl), how many
    # have a plan memo available?
    feats = [json.loads(l) for l in (OUT / "features.jsonl").read_text().splitlines()]
    covered = unc = 0
    for f in feats:
        plan = plan_of(f["rup"])
        if plan and f"{f['community']}::{plan}" in memo:
            covered += 1
        else:
            unc += 1

    agree_vals = [e["agreement"] for pe in memo.values() for e in pe.values()]
    md = [
        "# Per-plan fitting memo — harvest report",
        f"- pairs used: {len(ok)} (unparseable plan code: {unplanned})",
        f"- plan memos learned: {len(memo)} (community::plan groups)",
        f"- constancy: median per-SKU agreement = {st.median(agree_vals):.3f}; "
        f"{sum(1 for a in agree_vals if a >= 0.9)}/{len(agree_vals)} SKU-entries ≥90% agreement",
        f"- corpus coverage: {covered}/{covered+unc} canonical rups "
        f"({covered/(covered+unc)*100:.0f}%) have a memo for their plan",
        "",
        "| community | plan | lots | const SKUs | varying SKUs |",
        "|---|---|---|---|---|",
    ]
    for comm, plan, n, c, v in report_rows:
        md.append(f"| {comm} | {plan} | {n} | {c} | {v} |")
    (OUT / "plan_memo_report.md").write_text("\n".join(md))
    print("\n".join(md[:8]))
    print(f"\n→ plan_memo.json ({len(memo)} plans), plan_memo_report.md")


if __name__ == "__main__":
    main()
