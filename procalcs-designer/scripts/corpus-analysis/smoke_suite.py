"""Richard-gate smoke suite — staging API vs XLS ground truth."""
import sys, json, random, time, requests
sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
sys.path.insert(0, "/Users/geraldvillaran/Procalcs/reliable-analysis-2026-07-14")
import repro_harness as H
from pathlib import Path
from collections import defaultdict, Counter

BASE = "https://procalcs-designer-desktop-staging-69864992834.us-east1.run.app"
OUT = Path('/Users/geraldvillaran/Procalcs/full-corpus-run-2026-07-15')
rows = [json.loads(l) for l in (OUT/'pairs.jsonl').read_text().splitlines()]
ok = [r for r in rows if r.get("recall") is not None]

# ── stratified selection ──────────────────────────────────────────
random.seed(42)
sel, seen = [], set()
bycomm = defaultdict(list)
for r in ok: bycomm[r["community"]].append(r)
for comm, rs in sorted(bycomm.items()):
    random.shuffle(rs)
    masters = [r for r in rs if r["kind"]=="master"]
    lots    = [r for r in rs if r["kind"]=="lot"]
    cos     = [r for r in rs if "co1" in r["rup"].lower() or "co2" in r["rup"].lower()]
    for bucket in (masters, lots, cos):
        for r in bucket:
            if r["rup"] not in seen and r.get("ft_exact"):
                sel.append({**r, "case": "clean"}); seen.add(r["rup"]); break
# skewed pair
skew = next(r for r in ok if r.get("xls_ft") and not r.get("ft_exact"))
sel.append({**skew, "case": "skewed"})
# sales offices
cen = json.load(open(OUT/'standard_bom_census.json'))["standard_files"]
sel.append({"rup": "Creekside/Master/T071 Master Cleanup/T071 CO Exhaust Duct Overlay/Finals/Current/T071 - Townes at Creekside Sales Office.rup",
            "xls": cen[0], "community": "Creekside", "case": "standard"})
print(f"selected: {len(sel)} uploads", flush=True)

results, fails = [], []
def upload(path, client="reliable-heating-and-cooling"):
    with open(H.ROOT/path, "rb") as f:
        t0 = time.time()
        resp = requests.post(f"{BASE}/api/bom/from-wrightsoft",
                             files={"file": (Path(path).name, f)},
                             data={"client_id": client, "job_id": "smoke-suite"},
                             timeout=180)
        return resp, time.time()-t0

for i, s in enumerate(sel, 1):
    rec = {"case": s["case"], "community": s["community"], "rup": s["rup"][-60:]}
    try:
        resp, dt = upload(s["rup"])
        rec["http"], rec["secs"] = resp.status_code, round(dt,1)
        d = resp.json()["data"]
        items = d["line_items"]
        gen = {}
        SYN = ("DUCT-", "REGISTERS", "FITTINGS")
        for li in items:
            sku = (li.get("sku") or "").strip().upper()
            if sku and not sku.startswith(SYN):
                gen.setdefault(sku, {"qty": li.get("quantity") or 0})
        truth = H.parse_xls(H.ROOT/s["xls"])
        c = H.compare(gen, truth)
        rec.update(recall=c["recall"], precision=c["precision"], qty=c["qty_acc"])
        skus = [(li.get("sku") or "") for li in items]
        dups = [k for k,v in Counter(skus).items() if v>1 and k]
        rec["dup_skus"] = dups
        rec["erv_count"] = sum(1 for k in skus if k.startswith("B150E"))
        rec["rheia_lines"] = sum(1 for k in skus if k.startswith(("10-","00-","20-")))
        gft = gen.get("10-00-190",{}).get("qty"); xft = (truth.get("10-00-190") or {}).get("qty")
        rec["ft_ok"] = (s["case"]=="skewed") or (gft is not None and xft and abs(gft-xft)<=1) or (xft is None)
        checks = [rec["http"]==200, not dups, rec["erv_count"]<=1, rec["ft_ok"]]
        if s["case"]=="clean":
            checks += [(c["recall"] or 0)>=0.70, (c["precision"] or 0)>=0.80, (c["qty_acc"] or 0)>=0.95, rec["rheia_lines"]>=8]
        if s["case"]=="standard":
            checks += [(c["recall"] or 0)>=0.95]
        rec["pass"] = all(checks)
    except Exception as e:
        rec["error"], rec["pass"] = str(e)[:120], False
    (results if rec["pass"] else fails).append(rec)
    print(f"[{i:>2}/{len(sel)}] {'PASS' if rec['pass'] else 'FAIL'} {s['case']:<9} {s['community'][:20]:<20} "
          f"r={rec.get('recall')} p={rec.get('precision')} q={rec.get('qty')} {rec.get('secs','')}s", flush=True)

# ── negative controls ─────────────────────────────────────────────
print("\nnegative controls:", flush=True)
neg = []
# 1. non-Rheia profile → no Rheia section
r0 = sel[0]
resp, _ = upload(r0["rup"], client="beazer-homes-az")
d = resp.json().get("data") or {}
rheia = sum(1 for li in (d.get("line_items") or []) if str(li.get("sku","")).startswith(("10-","00-")))
neg.append(("beazer profile suppresses Rheia section", resp.status_code==200 and rheia==0, f"rheia_lines={rheia}"))
# 2. junk file → clean 4xx
resp = requests.post(f"{BASE}/api/bom/from-wrightsoft",
                     files={"file": ("junk.rup", b"NOT A RUP FILE" * 100)},
                     data={"client_id": "reliable-heating-and-cooling", "job_id": "smoke-neg"}, timeout=60)
neg.append(("junk file rejected cleanly", 400 <= resp.status_code < 500, f"http={resp.status_code}"))
for name, okk, info in neg:
    print(f"  {'PASS' if okk else 'FAIL'}: {name} ({info})", flush=True)

# ── summary ───────────────────────────────────────────────────────
import statistics as st
clean = [r for r in results+fails if r["case"]=="clean" and r.get("recall") is not None]
summary = {
    "uploads": len(sel), "passed": len(results), "failed": len(fails),
    "negative_controls": [(n, p) for n,p,_ in neg],
    "clean_medians": {
        "recall": st.median([r["recall"] for r in clean]) if clean else None,
        "precision": st.median([r["precision"] for r in clean]) if clean else None,
        "qty": st.median([r["qty"] for r in clean]) if clean else None,
        "secs": st.median([r["secs"] for r in clean if r.get("secs")]) if clean else None,
    },
    "failures": fails,
}
json.dump(summary, open(OUT/'smoke_suite_results.json','w'), indent=1)
print("\n" + json.dumps(summary["clean_medians"], indent=1))
print(f"\nSUITE: {len(results)}/{len(sel)} passed, negatives: {[p for _,p,_ in neg]}")
