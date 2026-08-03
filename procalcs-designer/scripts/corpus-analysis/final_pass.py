"""P5 final pass — absorb recovered pairs, re-harvest memo, version check."""
import sys, json, re, statistics as st
sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
sys.path.insert(0, "/Users/geraldvillaran/Procalcs/reliable-analysis-2026-07-14")
import repro_harness as H
from pathlib import Path
from collections import Counter, defaultdict
OUT = Path('/Users/geraldvillaran/Procalcs/full-corpus-run-2026-07-15')
RULE_SKUS = ["10-01-010","20-01-010","10-01-020","10-01-030","00-00-240",
             "10-01-220","10-01-200","10-01-210","10-04-230","10-04-091","10-04-090",
             "10-01-041","10-01-051","10-01-040","10-01-050","10-00-190","20-00-190"]
PLAN_RE = re.compile(r"\b([TVE]\d{3}R?)\b", re.I)
VER_RE  = re.compile(r"\bv?(\d+\.\d+)\b", re.I)

def xls_qty(x):
    t = H.parse_xls(x)
    return {s: t[s]["qty"] for s in RULE_SKUS if s in t}

# 1. assemble expanded ground truth
rows = [json.loads(l) for l in (OUT/'pairs.jsonl').read_text().splitlines()]
base = [r for r in rows if r.get("xls_qty")]
extra = []
for src, key_r, key_x in (("ambiguous_pairs.json","rup","xls"), ("skew_recovery.json","matching_rup","xls")):
    d = json.load(open(OUT/src))
    for m in (d.get("pairs") or d.get("matches") or []):
        try:
            extra.append({"rup": m[key_r], "xls": m[key_x],
                          "community": m[key_x].split("/")[0],
                          "xls_qty": xls_qty(H.ROOT/m[key_x])})
        except Exception: pass
print(f"ground truth: base={len(base)} + recovered={len(extra)} = {len(base)+len(extra)}")

# 2. plan-version sensitivity: same plan, different version → same fitting qtys?
byplan = defaultdict(lambda: defaultdict(set))
for r in base+extra:
    m = PLAN_RE.search(Path(r["rup"]).stem); v = VER_RE.search(r["rup"])
    if not m: continue
    key = (r["community"], m.group(1).upper())
    ver = v.group(1) if v else "?"
    for sku, q in (r["xls_qty"] or {}).items():
        byplan[key][(sku, ver)].add(q)
multi_ver, changed = 0, 0
for key, entries in byplan.items():
    vers = {ver for (_, ver) in entries}
    if len(vers - {"?"}) < 2: continue
    multi_ver += 1
    for sku in {s for (s, _) in entries}:
        qs = set().union(*(entries[(sku, ver)] for ver in vers if (sku, ver) in entries))
        if len(qs) > 1: changed += 1; break
print(f"plans with multiple versions in ground truth: {multi_ver}; versions changed quantities in: {changed}")

# 3. re-harvest memo on full ground truth
groups = defaultdict(list)
for r in base+extra:
    m = PLAN_RE.search(Path(r["rup"]).stem)
    if m: groups[(r["community"], m.group(1).upper())].append(r)
memo = {}
for (comm, plan), rs in groups.items():
    entry = {}
    for sku in RULE_SKUS:
        vals = [q for r in rs if (q := (r["xls_qty"] or {}).get(sku)) is not None]
        if not vals: continue
        mode, n = Counter(vals).most_common(1)[0]
        entry[sku] = {"qty": mode, "n": len(vals), "agreement": round(n/len(vals), 3)}
    if entry: memo[f"{comm}::{plan}"] = entry
json.dump(memo, open(OUT/'plan_memo.json','w'), indent=1)
agree = [e["agreement"] for pe in memo.values() for e in pe.values()]
print(f"memo v2: {len(memo)} plans, median agreement {st.median(agree):.3f}, "
      f"{sum(1 for a in agree if a>=0.9)}/{len(agree)} entries >=90%")
