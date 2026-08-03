"""full_corpus_pass.py — overnight full-corpus learning run.

Phase A  every canonical Finals .rup (non-RE): structural features
         (registers, home-run count+ft, duct segments, equipment,
         priced lines) + paired/unpaired classification.
Phase B  every unambiguous pair: engine-v3 generation vs Richard's
         xls — recall/precision/qty + footage ratio (skew detector)
         + per-SKU miss/extra tallies + xls quantities for rule
         regression (ferrules, takeoffs, hangers).
Phase C  aggregates: corpus-wide scoreboard, skew list, standard-
         project profile by community, rule-regression tables.

Outputs in this directory:
  features.jsonl      one row per rup (checkpointed, resumable)
  pairs.jsonl         one row per scored pair
  summary.json / summary.md
"""
from __future__ import annotations

import json
import math
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
sys.path.insert(0, "/Users/geraldvillaran/Procalcs/reliable-analysis-2026-07-14")

import repro_harness as H  # find/pair/compare/parse_xls helpers
from utils.rup_reader import RupReader
from utils.rup_rpitem_parser import has_priced_bom, parse_priced_lines
from utils.rup_equip_parser import parse_equipment
from utils.rup_duct_parser import parse_baldict
from utils.rup_duct_drawing_parser import parse_duct_segments
from utils.rup_home_run_parser import parse_home_run_lengths
from services.bom_from_rup import build_lines_from_rup

ROOT = H.ROOT
OUT = Path(__file__).parent
FEATURES = OUT / "features.jsonl"
PAIRS = OUT / "pairs.jsonl"

SYNTHETIC = ("DUCT-", "REGISTERS", "FITTINGS")
RULE_SKUS = ["10-00-190", "10-01-010", "20-01-010", "10-01-030", "10-01-020",
             "10-01-041", "10-01-051", "10-01-040", "10-01-050", "00-00-240",
             "10-01-220", "10-01-200", "10-01-210", "10-04-230", "10-04-091"]


def rup_features(rup: Path) -> dict:
    raw = rup.read_bytes()
    rd = RupReader(raw)
    runs = []
    try:
        runs = parse_home_run_lengths(rd)
    except Exception:
        pass
    equip = parse_equipment(rd)
    models = sorted({(e.get("condenser_model") or "").strip()
                     for e in equip if e.get("condenser_model")} |
                    {(e.get("coil_model") or "").strip()
                     for e in equip if e.get("coil_model")})
    mfrs = sorted({(e.get("manufacturer") or "").strip()
                   for e in equip if e.get("manufacturer")})
    segs = parse_duct_segments(rd)
    return {
        "built": has_priced_bom(rd),
        "priced_lines": len({L["part_no"] for L in parse_priced_lines(rd)}) if has_priced_bom(rd) else 0,
        "registers": len(parse_baldict(rd)),
        "home_runs": len(runs),
        "home_run_ft": round(sum(r["length_ft"] for r in runs), 1) if runs else 0,
        "trunk_segments": len(segs),
        "trunk_ft": round(sum(s["cut_length_ft"] for s in segs), 1),
        "equip_models": models[:12],
        "equip_mfrs": mfrs,
        "size_mb": round(len(raw) / 1e6, 2),
    }


def gen_v3(rup: Path) -> dict:
    out = {}
    for li in build_lines_from_rup(rup.read_bytes(), source_name=rup.name,
                                   rheia_takeoff=True):
        sku = (li.get("generic_id") or "").strip().upper()
        if not sku or sku.startswith(SYNTHETIC):
            continue
        out.setdefault(sku, {"qty": li.get("quantity") or 0})
    return out


def main():
    t0 = time.time()
    # ── enumerate canonical rups + pairing ─────────────────────────
    pairs = H.find_pairs()
    paired_rups = {str(p["rup"]): p for p in pairs}
    all_rups = [p for p in ROOT.rglob("*.rup")
                if "/finals/" in str(p).lower()
                and not H.is_re(p.stem)]
    print(f"canonical Finals rups: {len(all_rups)} | unambiguous pairs: {len(pairs)}",
          flush=True)

    done = set()
    if FEATURES.exists():
        for ln in FEATURES.read_text().splitlines():
            try:
                done.add(json.loads(ln)["rup"])
            except Exception:
                pass

    # ── Phase A: features for every rup ───────────────────────────
    ferr = open(FEATURES, "a")
    errs = 0
    for i, rup in enumerate(all_rups, 1):
        rel = str(rup.relative_to(ROOT))
        if rel in done:
            continue
        row = {"rup": rel,
               "community": rel.split("/")[0],
               "paired": str(rup) in paired_rups}
        try:
            row.update(rup_features(rup))
        except Exception as exc:
            row["error"] = str(exc)[:150]
            errs += 1
        ferr.write(json.dumps(row) + "\n")
        if i % 100 == 0:
            ferr.flush()
            print(f"  [A {i}/{len(all_rups)}] errs={errs} "
                  f"({(time.time()-t0):.0f}s)", flush=True)
    ferr.close()
    print(f"Phase A done: {len(all_rups)} rups, {errs} errors "
          f"({time.time()-t0:.0f}s)", flush=True)

    # ── Phase B: score every pair ──────────────────────────────────
    done_pairs = set()
    if PAIRS.exists():
        for ln in PAIRS.read_text().splitlines():
            try:
                done_pairs.add(json.loads(ln)["rup"])
            except Exception:
                pass
    pf = open(PAIRS, "a")
    for i, p in enumerate(pairs, 1):
        rel = str(p["rup"].relative_to(ROOT))
        if rel in done_pairs:
            continue
        row = {"rup": rel, "xls": str(p["xls"].relative_to(ROOT)),
               "community": p["community"], "kind": p["kind"]}
        try:
            gen = gen_v3(p["rup"])
            truth = H.parse_xls(p["xls"])
            c = H.compare(gen, truth)
            row.update({k: c[k] for k in
                        ("recall", "precision", "qty_acc", "matched",
                         "truth_lines", "gen_lines")})
            row["missing"] = c["missing"][:20]
            row["extra"] = c["extra"][:20]
            # footage skew detector
            gen_ft = gen.get("10-00-190", {}).get("qty")
            xls_ft = truth.get("10-00-190", {}).get("qty")
            row["gen_ft"], row["xls_ft"] = gen_ft, xls_ft
            row["ft_exact"] = (gen_ft is not None and xls_ft
                               and abs(gen_ft - xls_ft) <= 1)
            # rule-regression payload: xls qty for candidate SKUs + rup drivers
            rd = RupReader(p["rup"].read_bytes())
            runs = parse_home_run_lengths(rd)
            row["home_runs"] = len(runs)
            row["home_run_ft"] = round(sum(r["length_ft"] for r in runs), 1)
            row["xls_qty"] = {s: truth.get(s, {}).get("qty") for s in RULE_SKUS
                              if s in truth}
        except Exception as exc:
            row["error"] = str(exc)[:200]
        pf.write(json.dumps(row) + "\n")
        if i % 50 == 0:
            pf.flush()
            print(f"  [B {i}/{len(pairs)}] ({(time.time()-t0):.0f}s)", flush=True)
    pf.close()
    print(f"Phase B done ({time.time()-t0:.0f}s)", flush=True)

    # ── Phase C: aggregates ────────────────────────────────────────
    import statistics as st
    feats = [json.loads(l) for l in FEATURES.read_text().splitlines()]
    prs = [json.loads(l) for l in PAIRS.read_text().splitlines()]
    ok = [r for r in prs if r.get("recall") is not None]
    exact = [r for r in ok if r.get("ft_exact")]
    skewed = [r for r in ok if r.get("xls_ft") and not r.get("ft_exact")]

    def med(k, rows):
        v = [r[k] for r in rows if r.get(k) is not None]
        return round(st.median(v), 3) if v else None

    # standard-project profile
    std = [f for f in feats if not f.get("paired") and not f.get("error")]
    std_by_comm = defaultdict(lambda: {"n": 0, "built": 0, "rheia_runs": 0,
                                       "mfrs": Counter()})
    for f in std:
        b = std_by_comm[f["community"]]
        b["n"] += 1
        b["built"] += 1 if f.get("built") else 0
        b["rheia_runs"] += 1 if f.get("home_runs") else 0
        for m in f.get("equip_mfrs") or []:
            b["mfrs"][m] += 1

    miss_all, extra_all = Counter(), Counter()
    for r in ok:
        for m in r.get("missing") or []:
            miss_all[m] += 1
        for e in r.get("extra") or []:
            extra_all[e] += 1

    summary = {
        "generated_at": "2026-07-15 overnight",
        "rups_analyzed": len(feats),
        "pairs_scored": len(ok),
        "pair_errors": len(prs) - len(ok),
        "scoreboard": {
            "recall_median": med("recall", ok),
            "precision_median": med("precision", ok),
            "qty_acc_median": med("qty_acc", ok),
            "recall_on_ft_exact_pairs": med("recall", exact),
        },
        "footage": {
            "pairs_with_xls_ft": sum(1 for r in ok if r.get("xls_ft")),
            "ft_exact": len(exact),
            "ft_skewed": len(skewed),
        },
        "top_misses": dict(miss_all.most_common(25)),
        "top_extras": dict(extra_all.most_common(15)),
        "standard_projects": {
            c: {"n": b["n"], "built": b["built"], "with_home_runs": b["rheia_runs"],
                "top_mfrs": dict(b["mfrs"].most_common(5))}
            for c, b in sorted(std_by_comm.items())
        },
        "skewed_pairs": [r["rup"] for r in skewed][:100],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary["scoreboard"], indent=2))
    print(f"\nALL DONE in {time.time()-t0:.0f}s → {OUT/'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
