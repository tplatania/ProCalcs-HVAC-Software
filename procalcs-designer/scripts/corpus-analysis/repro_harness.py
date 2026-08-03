"""repro_harness.py — Phase-1 reproduction loop (20-pair pilot).

For each canonical (Finals .rup, BOM .xls) pair:
  1. "Generate" the BOM from the .rup alone (RPITEM priced lines +
     EQUIP equipment — the same deterministic core the staging
     pipeline uses).
  2. Parse Richard's actual .xls export.
  3. Diff: line recall / precision (SKU-level), qty accuracy on
     matched SKUs, price coverage.

Engine is FROZEN for the whole run. Checkpoints at 5/10/15/20 dump
aggregated misses for pattern extraction — no fixes applied mid-run.

Pair selection: stratified across communities; Finals-tree, non-RE
rups; the .xls must live in the same lot folder ('... BOM.xls').
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/Users/geraldvillaran/Projects/procalcs-hvac-upstream/procalcs-bom/backend")
from utils.rup_reader import RupReader
from utils.rup_rpitem_parser import has_priced_bom, parse_priced_lines
from utils.rup_equip_parser import parse_equipment
from services.bom_from_wrightsoft import parse_wrightsoft_bom_rows

ROOT = Path("/Users/geraldvillaran/Procalcs/RUPs-from-zoho")
OUT = Path(__file__).parent / "repro_run_2026-07-15"
OUT.mkdir(exist_ok=True)

QTY_TOL = 0.02  # 2% relative tolerance on quantities


def is_re(stem: str) -> bool:
    s = stem.lower().rstrip()
    return s.endswith(" re") or s.endswith("-re")


def find_pairs() -> list[dict]:
    """Unambiguous pairs: canonical Finals rup + a single '* BOM.xls'
    within the same project folder subtree."""
    pairs = []
    for rup in ROOT.rglob("*.rup"):
        p = str(rup).lower()
        if "/finals/" not in p or is_re(rup.stem):
            continue
        # project folder = the dir containing 'Finals'
        proj = rup.parent
        while proj.name.lower() not in ("finals",) and proj != ROOT:
            proj = proj.parent
        proj = proj.parent  # folder that CONTAINS Finals/
        xls = [x for x in proj.rglob("*.xls") if x.stem.lower().endswith(" bom")]
        # dedupe identical names across Finals/Working Drawings copies
        uniq = {}
        for x in xls:
            uniq.setdefault(x.name.lower(), x)
        xls = list(uniq.values())
        if len(xls) != 1:
            continue  # ambiguous or missing → skip (pairing-error guard)
        community = rup.relative_to(ROOT).parts[0]
        kind = "master" if "master" in p else "lot"
        pairs.append({"rup": rup, "xls": xls[0], "community": community, "kind": kind})
    return pairs


def stratified_sample(pairs: list[dict], n: int, seed: int = 7) -> list[dict]:
    random.seed(seed)
    by_comm = defaultdict(list)
    for p in pairs:
        by_comm[p["community"]].append(p)
    # round-robin communities, alternating master/lot when available
    picked, comms = [], sorted(by_comm)
    i = 0
    while len(picked) < n and any(by_comm.values()):
        c = comms[i % len(comms)]
        i += 1
        if not by_comm[c]:
            continue
        bucket = by_comm[c]
        random.shuffle(bucket)
        picked.append(bucket.pop())
    return picked[:n]


def generate_from_rup(rup: Path) -> dict[str, dict]:
    """Deterministic v0 engine: RPITEM lines + EQUIP models, keyed by SKU."""
    reader = RupReader(rup.read_bytes())
    out: dict[str, dict] = {}
    if has_priced_bom(reader):
        first = {}
        for L in parse_priced_lines(reader):
            first.setdefault(L["part_no"], L)
        for pn, L in first.items():
            out[pn.strip().upper()] = {
                "qty": L["quantity"], "price": L["unit_price"],
                "src": L["part_source"], "from": "rpitem",
            }
    for e in parse_equipment(reader):
        for model in (e.get("condenser_model"), e.get("coil_model")):
            if model and model.strip():
                out.setdefault(model.strip().upper(), {
                    "qty": 1, "price": 0.0,
                    "src": e.get("part_source") or "", "from": "equip",
                })
    return out


def parse_xls(xls: Path) -> dict[str, dict]:
    rows = parse_wrightsoft_bom_rows(xls.read_bytes(), filename=xls.name)
    out: dict[str, dict] = {}
    for r in rows:
        sku = (r.get("generic_id") or "").strip().upper()
        if not sku:
            continue
        if sku in out:  # first occurrence wins (mirror engine dedup)
            continue
        out[sku] = {
            "qty": r.get("quantity") or 0,
            "price": r.get("wrightsoft_price"),
            "src": r.get("src") or "", "desc": r.get("description") or "",
            "section": r.get("section_hint") or "",
        }
    return out


def compare(gen: dict, truth: dict) -> dict:
    gkeys, tkeys = set(gen), set(truth)
    matched = gkeys & tkeys
    missing = tkeys - gkeys        # in Richard's BOM, engine missed → the residual
    extra   = gkeys - tkeys        # engine emitted, Richard's BOM lacks
    qty_ok = qty_bad = 0
    qty_diffs = []
    for k in matched:
        gq, tq = float(gen[k]["qty"] or 0), float(truth[k]["qty"] or 0)
        if tq == 0 or abs(gq - tq) <= QTY_TOL * max(abs(tq), 1):
            qty_ok += 1
        else:
            qty_bad += 1
            qty_diffs.append({"sku": k, "gen_qty": gq, "xls_qty": tq})
    return {
        "recall":    round(len(matched) / len(tkeys), 3) if tkeys else None,
        "precision": round(len(matched) / len(gkeys), 3) if gkeys else None,
        "qty_acc":   round(qty_ok / len(matched), 3) if matched else None,
        "matched": len(matched), "truth_lines": len(tkeys), "gen_lines": len(gkeys),
        "missing": sorted(missing), "extra": sorted(extra), "qty_diffs": qty_diffs,
    }


def main():
    pairs = find_pairs()
    print(f"unambiguous canonical pairs available: {len(pairs)}")
    sample = stratified_sample(pairs, 20)
    print(f"sampled: {len(sample)} across "
          f"{len({p['community'] for p in sample})} communities "
          f"({sum(1 for p in sample if p['kind']=='master')} master / "
          f"{sum(1 for p in sample if p['kind']=='lot')} lot)\n")

    results = []
    miss_counter: Counter = Counter()
    miss_meta: dict[str, dict] = {}
    extra_counter: Counter = Counter()

    for i, p in enumerate(sample, 1):
        rel = str(p["rup"].relative_to(ROOT))
        try:
            gen = generate_from_rup(p["rup"])
            truth = parse_xls(p["xls"])
            cmpres = compare(gen, truth)
        except Exception as exc:  # noqa: BLE001
            results.append({"i": i, "rup": rel, "error": str(exc)[:200]})
            print(f"[{i:>2}] ERROR {rel[-60:]}: {exc}")
            continue
        rec = {"i": i, "rup": rel, "xls": str(p["xls"].relative_to(ROOT)),
               "community": p["community"], "kind": p["kind"], **cmpres}
        results.append(rec)
        for m in cmpres["missing"]:
            miss_counter[m] += 1
            if m not in miss_meta:
                miss_meta[m] = {"desc": truth[m].get("desc", ""),
                                "src": truth[m].get("src", ""),
                                "section": truth[m].get("section", "")}
        for e in cmpres["extra"]:
            extra_counter[e] += 1
        print(f"[{i:>2}] {p['community'][:22]:<22} {p['kind']:<6} "
              f"recall={cmpres['recall']} prec={cmpres['precision']} "
              f"qty={cmpres['qty_acc']} "
              f"({cmpres['matched']}/{cmpres['truth_lines']} lines)")

        if i % 5 == 0:
            print(f"\n===== CHECKPOINT after {i} =====")
            done = [r for r in results if "recall" in r and r["recall"] is not None]
            for metric in ("recall", "precision", "qty_acc"):
                vals = sorted(r[metric] for r in done if r[metric] is not None)
                if vals:
                    print(f"  {metric:<10} median={vals[len(vals)//2]:.3f} "
                          f"min={vals[0]:.3f} max={vals[-1]:.3f}")
            print("  top recurring MISSES (xls has, engine lacks):")
            for sku, n in miss_counter.most_common(8):
                m = miss_meta[sku]
                print(f"    {n:>2}× {sku:<18} [{m['src']:<5}] {m['desc'][:45]}")
            print("  top recurring EXTRAS (engine has, xls lacks):")
            for sku, n in extra_counter.most_common(5):
                print(f"    {n:>2}× {sku}")
            print()

    (OUT / "results.json").write_text(json.dumps(
        {"results": results,
         "miss_counter": dict(miss_counter.most_common()),
         "miss_meta": miss_meta,
         "extra_counter": dict(extra_counter.most_common())},
        indent=2, default=str))
    print(f"\nfull results → {OUT/'results.json'}")


if __name__ == "__main__":
    main()
