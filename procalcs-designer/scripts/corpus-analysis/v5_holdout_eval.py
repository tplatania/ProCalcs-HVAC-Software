"""v5_holdout_eval.py — leakage-guarded evaluation of engine v5
(v4 geometric rules + per-plan fitting memo).

For each scored pair: build the plan memo from the OTHER lots of the
same (community, plan) — never from the lot being scored — then emit
v4 lines + memo SKUs (≥90% agreement among the other lots, and only
SKUs not already emitted by v4). Score against the xls.

Reports v4 vs v5 on the same pairs, split by memo coverage.
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/Users/geraldvillaran/Procalcs/reliable-analysis-2026-07-14")
sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
import repro_harness as H
from services.bom_from_rup import build_lines_from_rup

OUT = Path(__file__).parent
SYN = ("DUCT-", "REGISTERS", "FITTINGS")
MEMO_SKUS = ["10-01-010", "20-01-010", "10-01-020", "10-01-030",
             "00-00-240", "10-01-210", "10-04-090", "20-00-190",
             "10-01-040", "10-01-050"]  # SKUs v4 does NOT emit
PLAN_RE = re.compile(r"\b([TVE]\d{3}R?)(?:\s*v?[\d.]+)?\b", re.I)


def plan_of(path: str):
    m = PLAN_RE.search(Path(path).stem)
    return m.group(1).upper() if m else None


def gen_v4(rup: Path) -> dict:
    out = {}
    for li in build_lines_from_rup(rup.read_bytes(), source_name=rup.name,
                                   rheia_takeoff=True):
        sku = (li.get("generic_id") or "").strip().upper()
        if sku and not sku.startswith(SYN):
            out.setdefault(sku, {"qty": li.get("quantity") or 0})
    return out


def main():
    rows = [json.loads(l) for l in (OUT / "pairs.jsonl").read_text().splitlines()]
    ok = [r for r in rows if r.get("xls_qty") is not None and r.get("recall") is not None]
    by_plan = defaultdict(list)
    for r in ok:
        p = plan_of(r["rup"]) or plan_of(r["xls"])
        r["_plan"] = p
        if p:
            by_plan[(r["community"], p)].append(r)

    v4s, v5s, covered = [], [], 0
    for r in ok:
        key = (r["community"], r["_plan"])
        others = [o for o in by_plan.get(key, []) if o is not r]
        rup = H.ROOT / r["rup"]
        gen = gen_v4(rup)
        truth = H.parse_xls(H.ROOT / r["xls"])
        c4 = H.compare(dict(gen), truth)

        memo_added = 0
        if len(others) >= 2:
            for sku in MEMO_SKUS:
                vals = [q for o in others
                        if (q := (o["xls_qty"] or {}).get(sku)) is not None]
                if len(vals) >= 2:
                    mode, n = Counter(vals).most_common(1)[0]
                    if n / len(vals) >= 0.9 and sku not in gen:
                        gen[sku] = {"qty": mode}
                        memo_added += 1
        if memo_added:
            covered += 1
        c5 = H.compare(gen, truth)
        v4s.append(c4)
        v5s.append(c5)

    def report(label, cs):
        R = [c["recall"] for c in cs if c["recall"] is not None]
        P = [c["precision"] for c in cs if c["precision"] is not None]
        Q = [c["qty_acc"] for c in cs if c["qty_acc"] is not None]
        print(f"{label}: recall={st.median(R):.3f}  precision={st.median(P):.3f}  "
              f"qty={st.median(Q):.3f}   (means: {st.mean(R):.3f}/{st.mean(P):.3f}/{st.mean(Q):.3f})")

    print(f"pairs evaluated: {len(ok)} | memo applied on: {covered} "
          f"({covered/len(ok)*100:.0f}%)")
    report("v4          ", v4s)
    report("v5 (holdout)", v5s)
    json.dump({"pairs": len(ok), "memo_covered": covered,
               "v4": {k: st.median([c[k] for c in v4s if c[k] is not None])
                      for k in ("recall", "precision", "qty_acc")},
               "v5": {k: st.median([c[k] for c in v5s if c[k] is not None])
                      for k in ("recall", "precision", "qty_acc")}},
              open(OUT / "v5_holdout_results.json", "w"), indent=2)


if __name__ == "__main__":
    main()
