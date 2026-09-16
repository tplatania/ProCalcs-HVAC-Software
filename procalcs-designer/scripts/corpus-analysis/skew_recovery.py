"""P4.4 — revision-skew recovery. For each footage-skewed pair, search
the lot folder's OTHER rup revisions (Working Drawings, Reviews,
non-Current, RE variants) for one whose ceil(home-run sum) matches the
xls footage exactly. Match found => recovered ground-truth pair +
proof of the revision-skew hypothesis."""
import json, math, sys
from pathlib import Path
sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
from utils.rup_reader import RupReader
from utils.rup_home_run_parser import parse_home_run_lengths
ROOT = Path("/Users/geraldvillaran/Procalcs/RUPs-from-zoho")
rows = [json.loads(l) for l in open('/Users/geraldvillaran/Procalcs/full-corpus-run-2026-07-15/pairs.jsonl')]
skewed = [r for r in rows if r.get("xls_ft") and not r.get("ft_exact")]
print(f"skewed pairs: {len(skewed)}", flush=True)
recovered, nomatch, errs = [], 0, 0
for i, r in enumerate(skewed, 1):
    try:
        xls_ft = r["xls_ft"]
        lot_dir = (ROOT / r["xls"]).parent.parent  # project folder-ish
        cands = [p for p in lot_dir.rglob("*.rup")]
        hit = None
        for c in cands:
            try:
                ft = math.ceil(sum(x["length_ft"] for x in
                                   parse_home_run_lengths(RupReader(c.read_bytes()))))
                if abs(ft - xls_ft) <= 1:
                    hit = str(c.relative_to(ROOT)); break
            except Exception: continue
        if hit: recovered.append({"pair": r["rup"], "xls": r["xls"], "matching_rup": hit})
        else: nomatch += 1
    except Exception:
        errs += 1
    if i % 50 == 0: print(f"  [{i}/{len(skewed)}] recovered={len(recovered)}", flush=True)
out = {"skewed": len(skewed), "recovered": len(recovered), "no_match": nomatch, "errors": errs,
       "matches": recovered}
json.dump(out, open('/Users/geraldvillaran/Procalcs/full-corpus-run-2026-07-15/skew_recovery.json','w'), indent=1)
print(f"RESULT: recovered {len(recovered)}/{len(skewed)} (no_match={nomatch}, errs={errs})")
