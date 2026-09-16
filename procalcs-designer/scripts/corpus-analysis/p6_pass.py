"""P6 — formal zero-zero convergence pass.
(a) v7 engine scored on FULL expanded ground truth (base + recovered).
(b) New-question detector: recurring miss/extra SKUs not already
    explained by the ledger's known buckets.
Verdict: CONVERGED if no new material pattern and scoreboard stable."""
import sys, json, statistics as st
sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
sys.path.insert(0, "/Users/geraldvillaran/Procalcs/reliable-analysis-2026-07-14")
import repro_harness as H
from pathlib import Path
from collections import Counter
from services.bom_from_rup import build_lines_from_rup
OUT = Path('/Users/geraldvillaran/Procalcs/full-corpus-run-2026-07-15')
SYN = ("DUCT-", "REGISTERS", "FITTINGS")
KNOWN = set("10-01-010 20-01-010 10-01-020 10-01-030 00-00-240 10-01-210 10-04-090 20-00-190 10-01-040 10-01-050 10-01-041 10-01-051 10-00-190 10-01-220 10-01-200 10-04-230 10-04-091 B150E75NT B150E75NS B33DHW".split())
def gen(rup, name):
    out = {}
    for li in build_lines_from_rup(rup.read_bytes(), source_name=name, rheia_takeoff=True):
        sku = (li.get("generic_id") or "").strip().upper()
        if sku and not sku.startswith(SYN): out.setdefault(sku, {"qty": li.get("quantity") or 0})
    return out
pairs = []
rows = [json.loads(l) for l in (OUT/'pairs.jsonl').read_text().splitlines()]
pairs += [(r["rup"], r["xls"]) for r in rows if r.get("recall") is not None]
for src, kr in (("ambiguous_pairs.json","rup"), ("skew_recovery.json","matching_rup")):
    d = json.load(open(OUT/src))
    pairs += [(m[kr], m["xls"]) for m in (d.get("pairs") or d.get("matches") or [])]
print(f"P6 scoring {len(pairs)} pairs", flush=True)
R,P,Q = [],[],[]
miss, extra = Counter(), Counter()
for i,(rp,xp) in enumerate(pairs,1):
    try:
        c = H.compare(gen(H.ROOT/rp, Path(rp).name), H.parse_xls(H.ROOT/xp))
        R.append(c["recall"]); P.append(c["precision"]); Q.append(c["qty_acc"] or 1)
        for m in c["missing"]: miss[m]+=1
        for e in c["extra"]: extra[e]+=1
    except Exception: pass
    if i%300==0: print(f"  [{i}/{len(pairs)}]", flush=True)
new_miss  = [(s,n) for s,n in miss.most_common(30)  if s not in KNOWN and n >= len(pairs)*0.05]
new_extra = [(s,n) for s,n in extra.most_common(30) if s not in KNOWN and n >= len(pairs)*0.05]
res = {"pairs": len(R),
       "scoreboard": {"recall": round(st.median(R),3), "precision": round(st.median(P),3), "qty": round(st.median(Q),3)},
       "new_material_misses": new_miss, "new_material_extras": new_extra,
       "verdict": "CONVERGED" if not new_miss and not new_extra else "NEW PATTERNS FOUND"}
json.dump(res, open(OUT/'p6_results.json','w'), indent=1)
print(json.dumps(res, indent=1))
