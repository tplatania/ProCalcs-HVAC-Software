"""P5.3 — recover lots excluded from pairing because >1 unique BOM xls.
Rule: prefer the xls in Finals/ (over Working Drawings), then latest CO
subfolder, then latest mtime name-wise; validate by footage match."""
import sys, json, math
sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
sys.path.insert(0, "/Users/geraldvillaran/Procalcs/reliable-analysis-2026-07-14")
import repro_harness as H
from pathlib import Path
from utils.rup_reader import RupReader
from utils.rup_home_run_parser import parse_home_run_lengths
ROOT = H.ROOT
# replicate find_pairs but collect the AMBIGUOUS ones
recovered, checked = [], 0
seen_proj = set()
for rup in ROOT.rglob("*.rup"):
    p = str(rup).lower()
    if "/finals/" not in p or H.is_re(rup.stem): continue
    proj = rup.parent
    while proj.name.lower() != "finals" and proj != ROOT: proj = proj.parent
    proj = proj.parent
    if str(proj) in seen_proj: continue
    seen_proj.add(str(proj))
    xls = {x.name.lower(): x for x in proj.rglob("*.xls") if x.stem.lower().endswith(" bom")}
    if len(xls) <= 1: continue  # unambiguous already handled
    checked += 1
    try:
        ft = math.ceil(sum(r["length_ft"] for r in parse_home_run_lengths(RupReader(rup.read_bytes()))))
    except Exception: continue
    for x in xls.values():
        try:
            t = H.parse_xls(x)
            xft = (t.get("10-00-190") or {}).get("qty")
            if xft and abs(xft - ft) <= 1:
                recovered.append({"rup": str(rup.relative_to(ROOT)), "xls": str(x.relative_to(ROOT)), "ft": ft})
                break
        except Exception: continue
json.dump({"ambiguous_lots": checked, "recovered": len(recovered), "pairs": recovered},
          open('/Users/geraldvillaran/Procalcs/full-corpus-run-2026-07-15/ambiguous_pairs.json','w'), indent=1)
print(f"ambiguous lots: {checked} | recovered by footage-match: {len(recovered)}")
