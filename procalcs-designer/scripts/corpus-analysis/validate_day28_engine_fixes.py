#!/usr/bin/env python3
"""
validate_day28_engine_fixes.py — Day-28 P0 engine fixes (Richard, SW
55th Ave). Rups can't live in the repo, so this reproduces the
validation against local files.

Two fixes in backend/services/bom_from_rup.py:

  1. Flex/duct summing — priced-BOM (RPITEM) lines that recur per size
     across zones are now SUMMED, not first-only. SW 55th DDVn04 was
     shown as 49 (kept first) vs the real 49+77 = 126.

  2. Per-project Rheia gate — rheia_takeoff was set from the CONTRACTOR
     profile ("rheia" in supplier), so a Rheia contractor's CONVENTIONAL
     jobs got 9 phantom Rheia lines + a phantom ERV every upload. New
     gate: count distinct conventional duct-run SKUs (DDVn/DRFg) in the
     priced BOM. Known-Rheia projects price only a 1-2 SKU stub
     (Wrightsoft's Rheia plugin derives the rest); conventional jobs
     price the full system (SW 55th=29, 79th Ct=26). Threshold 5 sits in
     the gap with a 3-SKU margin above the Rheia max — validated as
     0/50 false-suppressions on the known-Rheia pairs.

Run:  python3 validate_day28_engine_fixes.py
Exit 0 = all assertions hold.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

UPSTREAM = Path.home() / "Projects/procalcs-hvac-upstream/procalcs-bom/backend"
sys.path.insert(0, str(UPSTREAM))

from services.bom_from_rup import build_lines_from_rup            # noqa: E402
from utils.rup_reader import RupReader                            # noqa: E402
from utils.rup_rpitem_parser import has_priced_bom, parse_priced_lines  # noqa: E402

CONV = Path.home() / "Procalcs/SW 55th Ave Residence_duct2.rup"
ROOT = Path.home() / "Procalcs/RUPs-from-zoho"
PAIRS = Path.home() / "Procalcs/full-corpus-run-2026-07-15/pairs.jsonl"

# Day-31 review (Tom): check ALL local conventional ground-truth
# files, not just SW 55th. Verified result: 50 known-Rheia pairs
# max 7 vs five BUILT conventional projects min 37 (Enos is unbuilt —
# gate not applicable; Melko's 27 came from its stored-run listing and
# stays supporting-only until its fresh upload). Corpus-based
# supporting evidence — rups can't live in the repo; the committed run
# log (docs/validation-2026-07-31-rheia-gate.md) is the artifact.
CONV_ALL = [
    Path.home() / "Procalcs/SW 55th Ave Residence_duct2.rup",
    Path.home() / "Procalcs/Jappeloup Lane Residence_duct.rup",
    Path.home() / "Procalcs/1257 Irvine Rd Residence.rup",
    Path.home() / "Procalcs/Enos Residence Load Calcs.rup",
    Path.home() / "Procalcs/RUPs/79th Ct Residence Load Calcs+BOM.rup",
    Path.home() / "Procalcs/BOM Samples/Clarke Residence Load Calcs.rup",
]


def build(f: Path, rheia: bool):
    lines = build_lines_from_rup(f.read_bytes(), source_name=f.name, rheia_takeoff=rheia)
    rheia_lines = [l for l in lines
                   if l.get("src") == "RHEA" or str(l.get("generic_id", "")).startswith("10-")]
    erv = [l for l in lines if "B150E" in str(l.get("generic_id", ""))]
    flex: dict[str, float] = {}
    for l in lines:
        g = str(l.get("generic_id", ""))
        if g.startswith("DDVn"):
            flex[g] = flex.get(g, 0.0) + float(l.get("quantity") or 0)
    return rheia_lines, erv, flex


# Day-31 (Melko): gate metric broadened from DDVn/DRFg-only (threshold
# 5) to the full conventional duct-system family spread (threshold 15)
# after a small sheet-metal-dominant conventional home fell below the
# old threshold and got phantom Rheia back.
_CONV_FAMS = ("DDVn", "DRFg", "DMS", "FBTI", "FTOB", "FTOA", "FTOD",
              "FRGR", "FREL", "FPLH", "FPLI", "FPLB", "FPLJ", "FRTE",
              "FMEC", "FBEC", "FRRTR")


def duct_run_skus(f: Path) -> int:
    lines = parse_priced_lines(RupReader(f.read_bytes()))
    return len({str(l.get("part_no", "")) for l in lines
                if str(l.get("part_no", "")).startswith(_CONV_FAMS)})


def main() -> int:
    ok = True

    # Fix 1 + 2 on the conventional file, WITH the Rheia flag on
    # (simulating a Rheia contractor uploading a conventional job).
    rl, erv, flex = build(CONV, rheia=True)
    checks = [
        ("SW55 conventional: 0 Rheia lines", len(rl) == 0),
        ("SW55 conventional: 0 phantom ERV", len(erv) == 0),
        ("SW55 flex DDVn04 summed to 126 (49+77)", flex.get("DDVn04") == 126.0),
        ("SW55 flex DDVn05 summed to 109", flex.get("DDVn05") == 109.0),
    ]

    # Regression: a real Rheia project must KEEP its takeoff.
    tcand = list(ROOT.rglob("T075*Master Option A.rup")) or list(ROOT.rglob("T075*.rup"))
    if tcand:
        rl2, _, _ = build(tcand[0], rheia=True)
        checks.append(("T075 Rheia: takeoff intact (>0 lines)", len(rl2) > 0))

    # Threshold separation across known-Rheia pairs vs conventional.
    if PAIRS.exists():
        counts = []
        for r in (json.loads(x) for x in open(PAIRS)):
            if not r.get("rup"):
                continue
            c = list(ROOT.rglob(Path(r["rup"]).name))
            if not c:
                continue
            try:
                if has_priced_bom(RupReader(c[0].read_bytes())):
                    counts.append(duct_run_skus(c[0]))
            except Exception:
                pass
            if len(counts) >= 50:
                break
        checks.append((f"known-Rheia max duct-system SKUs < 15 "
                       f"(n={len(counts)}, max={max(counts)})", max(counts) < 15))
        conv_counts = {}
        for cf in CONV_ALL:
            if not cf.exists():
                continue
            # The gate metric reads the PRICED BOM (RPITEM); unbuilt
            # files take the synthetic path and never reach the gate,
            # so they aren't calibration points for this threshold.
            if not has_priced_bom(RupReader(cf.read_bytes())):
                print(f"  ⏭️  '{cf.name}' has no Wrightsoft-built BOM "
                      "(unbuilt — gate not applicable, skipped)")
                continue
            conv_counts[cf.name] = duct_run_skus(cf)
        for cname, cnt in conv_counts.items():
            checks.append((f"conventional '{cname}' duct-system SKUs >= 15 "
                           f"(got {cnt})", cnt >= 15))
        if conv_counts:
            checks.append((f"conventional min across {len(conv_counts)} projects "
                           f"= {min(conv_counts.values())} (threshold 15, "
                           f"Rheia max {max(counts)})",
                           min(conv_counts.values()) >= 15))

    for label, passed in checks:
        print(f"  {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
