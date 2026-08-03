import sys, json, statistics as st, time
sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
sys.path.insert(0, "/Users/geraldvillaran/Procalcs/reliable-analysis-2026-07-14")
import repro_harness as H
from services.bom_from_rup import build_lines_from_rup
SYN = ("DUCT-", "REGISTERS", "FITTINGS")
def gen(rup):
    out = {}
    for li in build_lines_from_rup(rup.read_bytes(), source_name=rup.name, rheia_takeoff=True):
        sku = (li.get("generic_id") or "").strip().upper()
        if sku and not sku.startswith(SYN): out.setdefault(sku, {"qty": li.get("quantity") or 0})
    return out
rows = [json.loads(l) for l in open('/Users/geraldvillaran/Procalcs/full-corpus-run-2026-07-15/pairs.jsonl')]
rows = [r for r in rows if r.get("recall") is not None]
R,P,Q = [],[],[]
t0=time.time()
for i,r in enumerate(rows,1):
    try:
        c = H.compare(gen(H.ROOT/r["rup"]), H.parse_xls(H.ROOT/r["xls"]))
        R.append(c["recall"]); P.append(c["precision"]); Q.append(c["qty_acc"] or 1)
    except Exception: pass
    if i%200==0: print(f"  [{i}/{len(rows)}] {time.time()-t0:.0f}s", flush=True)
res = {"n": len(R),
       "recall": {"median": round(st.median(R),3), "mean": round(st.mean(R),3)},
       "precision": {"median": round(st.median(P),3), "mean": round(st.mean(P),3)},
       "qty_acc": {"median": round(st.median(Q),3), "mean": round(st.mean(Q),3)}}
json.dump(res, open('/Users/geraldvillaran/Procalcs/full-corpus-run-2026-07-15/v6_final_scoreboard.json','w'), indent=2)
print(json.dumps(res, indent=2))
