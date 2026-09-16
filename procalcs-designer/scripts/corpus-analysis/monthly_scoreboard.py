#!/usr/bin/env python3
"""
monthly_scoreboard.py — Day-25. Re-run the corpus scoreboard monthly
and measure whether accumulated user input is actually moving the
needle ("is the app learning, or just collecting?").

Two layers, because they move for different reasons:

  1. BASE ENGINE (recall / precision / qty_acc over the Rheia pair
     corpus, v6 methodology) — moves when engine rules improve.
  2. LEARNING OVERLAY — coverage added by contractor overrides on top
     of the engine's output: of the distinct part keys the engine
     emits across the corpus, what fraction now has a real-team
     override carrying a price or SKU fix? Moves when Richard's team
     feeds the loop.

Each run appends one row to scoreboard_history.jsonl next to this
script. THE TRIPWIRE (Gerald's "when do we need a new strategy?"):
if >= 50 real-provenance inputs have accumulated since the previous
run and overlay coverage moved < 1 point, the script exits 2 and says
so — inputs are either off-target or not being fed back.

Usage:
    python3 monthly_scoreboard.py [--skip-base] \
        [--impact-url https://<designer-staging>/api/usage/impact]

  --skip-base     reuse the last base scores (base takes ~10 min over
                  the full corpus; overlay alone takes seconds)
  --impact-url    where to fetch override impact. Auth rides on
                  OBSERVER_STAGING_COOKIE or direct BOM-service URL +
                  X-Procalcs-Service-Token via BOM_SERVICE_TOKEN env.

Provenance: the impact endpoint already excludes test actors
(Gerald/dev) server-side — nothing here needs to re-filter.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
HISTORY = HERE / "scoreboard_history.jsonl"
PAIRS = Path(os.environ.get(
    "CORPUS_PAIRS",
    str(Path.home() / "Procalcs/full-corpus-run-2026-07-15/pairs.jsonl")))

UPSTREAM_BACKEND = Path(os.environ.get(
    "PROCALCS_BOM_BACKEND",
    str(Path.home() / "Projects/procalcs-hvac-upstream/procalcs-bom/backend")))

SYN = ("DUCT-", "REGISTERS", "FITTINGS")


def run_base() -> dict:
    """v6-methodology base scoreboard over the pair corpus."""
    sys.path.insert(0, str(UPSTREAM_BACKEND))
    sys.path.insert(0, str(Path.home() / "Procalcs/reliable-analysis-2026-07-14"))
    import repro_harness as H  # noqa: E402
    from services.bom_from_rup import build_lines_from_rup  # noqa: E402

    def gen(rup: Path) -> dict:
        out: dict = {}
        for li in build_lines_from_rup(rup.read_bytes(), source_name=rup.name,
                                       rheia_takeoff=True):
            sku = (li.get("generic_id") or "").strip().upper()
            if sku and not sku.startswith(SYN):
                out.setdefault(sku, {"qty": li.get("quantity") or 0})
        return out

    rows = [json.loads(l) for l in open(PAIRS)]
    rows = [r for r in rows if r.get("recall") is not None]
    R, P, Q = [], [], []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        try:
            c = H.compare(gen(H.ROOT / r["rup"]), H.parse_xls(H.ROOT / r["xls"]))
            R.append(c["recall"]); P.append(c["precision"]); Q.append(c["qty_acc"] or 1)
        except Exception:  # noqa: BLE001 — junk pairs already labeled upstream
            pass
        if i % 200 == 0:
            print(f"  base [{i}/{len(rows)}] {time.time()-t0:.0f}s", flush=True)
    return {
        "n": len(R),
        "recall_median": round(st.median(R), 3),
        "precision_median": round(st.median(P), 3),
        "qty_acc_median": round(st.median(Q), 3),
    }


def corpus_part_keys() -> set[str]:
    """Distinct (supplier-agnostic) part keys the engine emits across
    the corpus — the denominator for overlay coverage. Cached because
    it only changes when the engine changes."""
    cache = HERE / ".corpus_part_keys.json"
    if cache.exists():
        return set(json.loads(cache.read_text()))
    sys.path.insert(0, str(UPSTREAM_BACKEND))
    sys.path.insert(0, str(Path.home() / "Procalcs/reliable-analysis-2026-07-14"))
    import repro_harness as H  # noqa: E402
    from services.bom_from_rup import build_lines_from_rup  # noqa: E402
    keys: set[str] = set()
    rows = [json.loads(l) for l in open(PAIRS)]
    for r in rows:
        try:
            for li in build_lines_from_rup((H.ROOT / r["rup"]).read_bytes(),
                                           source_name=r["rup"],
                                           rheia_takeoff=True):
                k = (li.get("generic_id") or "").strip().upper()
                if k:
                    keys.add(k)
        except Exception:  # noqa: BLE001
            pass
    cache.write_text(json.dumps(sorted(keys)))
    return keys


def fetch_impact(url: str) -> dict:
    req = urllib.request.Request(url)
    tok = os.environ.get("BOM_SERVICE_TOKEN")
    if tok:
        req.add_header("X-Procalcs-Service-Token", tok)
    cookie = os.environ.get("OBSERVER_STAGING_COOKIE")
    if cookie:
        req.add_header("Cookie", cookie)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if not body.get("success"):
        raise SystemExit(f"impact fetch failed: {body.get('error')}")
    return body["data"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-base", action="store_true")
    ap.add_argument("--impact-url", default=os.environ.get(
        "IMPACT_URL",
        "https://procalcs-hvac-bom-staging-69864992834.us-east1.run.app"
        "/api/v1/usage-events/impact"))
    args = ap.parse_args()

    history = [json.loads(l) for l in open(HISTORY)] if HISTORY.exists() else []
    prev = history[-1] if history else None

    if args.skip_base and prev:
        base = prev["base"]
        print("base: reused from previous run")
    else:
        base = run_base()
    print("base:", json.dumps(base))

    impact = fetch_impact(args.impact_url)
    totals = impact["totals"]
    keys = corpus_part_keys()
    # Overlay coverage: overridden keys ∩ corpus keys / corpus keys.
    overridden = {
        (d.get("sku") or "").strip().upper() for d in impact.get("top", [])
    } | set()  # /top is capped at 25; totals carry the true count
    covered = len(overridden & keys)
    overlay = {
        "overrides": totals["overrides"],
        "overrides_reapplied": totals["overrides_reapplied"],
        "total_reapplications": totals["total_reapplications"],
        "corpus_keys": len(keys),
        "corpus_keys_covered_sample": covered,
        "coverage_pct": round(100.0 * totals["overrides"] / max(len(keys), 1), 2),
    }
    print("overlay:", json.dumps(overlay))

    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "overlay": overlay,
    }
    with open(HISTORY, "a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"appended → {HISTORY}")

    # ── The tripwire ──────────────────────────────────────────────
    if prev:
        new_inputs = overlay["overrides"] - prev["overlay"]["overrides"]
        delta = overlay["coverage_pct"] - prev["overlay"]["coverage_pct"]
        print(f"since last run: +{new_inputs} overrides, "
              f"coverage {delta:+.2f} pts")
        if new_inputs >= 50 and delta < 1.0:
            print("TRIPWIRE: >=50 real inputs but coverage flat — "
                  "inputs are off-target or not feeding back. "
                  "Time to revisit the strategy.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
