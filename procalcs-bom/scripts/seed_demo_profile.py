"""
seed_demo_profile.py — one-shot Firestore seeder for demo client profiles.

Creates "ProCalcs Direct" (and optionally a secondary profile) so the
Designer Desktop dashboard has something to pick against during the
Richard/Tom user test walkthrough. Uses the live procalcs-hvac-bom
Cloud Run service — no direct Firestore SDK, no service account setup.

The "ProCalcs Direct" profile is seeded with Tom Platania's contact info
from the Enos Residence .rup JOBINFO block (tom@procalcs.net, license
CAC1815254) as flavor, plus realistic HVAC contractor defaults:
  - Supplier: Ferguson
  - Markups:  15% equipment, 20% materials, 30% consumables, 0% labor
  - Brands:   Carrier AC / Goodman furnace / Rectorseal mastic / Nashua tape

Usage:
    python scripts/seed_demo_profile.py
    python scripts/seed_demo_profile.py --base-url http://localhost:8080
    python scripts/seed_demo_profile.py --also-beazer   # seed a second profile

Exit code 0 on success, non-zero if any profile failed to create.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error


DEFAULT_BASE_URL = "https://procalcs-hvac-bom-w7vvclyqya-ue.a.run.app"


PROCALCS_DIRECT = {
    "client_id":   "procalcs-direct",
    "client_name": "ProCalcs Direct",
    "is_active":   True,
    "supplier": {
        "supplier_name":           "Ferguson",
        "account_number":          "",
        "mastic_cost_per_gallon":  38.50,
        "tape_cost_per_roll":      12.75,
        "strapping_cost_per_roll": 24.00,
        "screws_cost_per_box":     18.50,
        "brush_cost_each":         4.25,
        "flex_duct_cost_per_foot": 2.85,
        "rect_duct_cost_per_sqft": 6.40,
    },
    "markup": {
        "equipment_pct":    15.0,
        "materials_pct":    20.0,
        "consumables_pct":  30.0,
        "labor_pct":        0.0,
    },
    "brands": {
        "ac_brand":          "Carrier",
        "furnace_brand":     "Goodman",
        "air_handler_brand": "Carrier",
        "mastic_brand":      "Rectorseal",
        "tape_brand":        "Nashua",
        "flex_duct_brand":   "Atco",
    },
    "part_name_overrides": [
        {"standard_name": "4-inch collar",
         "client_name":   "4\" snap collar",
         "client_sku":    "FRG-COL-4IN"},
        {"standard_name": "6-inch collar",
         "client_name":   "6\" snap collar",
         "client_sku":    "FRG-COL-6IN"},
    ],
    "default_output_mode": "full",
    "include_labor":       False,
    "created_by":          "tom@procalcs.net",
    "notes": (
        "Tom Platania / ProCalcs, LLC — license CAC1815254. "
        "Default profile for direct ProCalcs installs; used as a demo "
        "baseline for the Designer Desktop Enos Residence walkthrough."
    ),
}


BEAZER_ARIZONA = {
    "client_id":   "beazer-homes-az",
    "client_name": "Beazer Homes - Arizona",
    "is_active":   True,
    "supplier": {
        "supplier_name":           "Winsupply",
        "account_number":          "BEAZ-AZ-4471",
        "mastic_cost_per_gallon":  36.00,
        "tape_cost_per_roll":      11.50,
        "strapping_cost_per_roll": 22.00,
        "screws_cost_per_box":     17.25,
        "brush_cost_each":         3.95,
        "flex_duct_cost_per_foot": 2.60,
        "rect_duct_cost_per_sqft": 6.10,
    },
    "markup": {
        "equipment_pct":    10.0,
        "materials_pct":    15.0,
        "consumables_pct":  25.0,
        "labor_pct":        0.0,
    },
    "brands": {
        "ac_brand":          "Trane",
        "furnace_brand":     "Trane",
        "air_handler_brand": "Trane",
        "mastic_brand":      "Rectorseal",
        "tape_brand":        "3M",
        "flex_duct_brand":   "Thermaflex",
    },
    "part_name_overrides": [],
    "default_output_mode": "client_proposal",
    "include_labor":       False,
    "created_by":          "tom@procalcs.net",
    "notes": (
        "Beazer Homes Arizona production contract. Uses Trane equipment "
        "across the board; tighter markups reflect volume pricing."
    ),
}


def post_profile(base_url: str, profile: dict) -> tuple[bool, str]:
    """POST one profile to /api/v1/profiles/. Returns (ok, message)."""
    url = f"{base_url.rstrip('/')}/api/v1/profiles/"
    body = json.dumps(profile).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            envelope = json.loads(res.read().decode("utf-8"))
            if envelope.get("success"):
                return True, f"created {profile['client_id']}"
            return False, f"flask rejected: {envelope.get('error')}"
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            env = json.loads(raw)
            err = env.get("error", raw)
        except Exception:
            err = raw
        return False, f"HTTP {e.code}: {err}"
    except Exception as e:  # noqa: BLE001
        return False, f"request failed: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo client profiles")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="procalcs-hvac-bom base URL (default: live Cloud Run)",
    )
    parser.add_argument(
        "--also-beazer",
        action="store_true",
        help="Also seed 'Beazer Homes - Arizona' (second demo profile)",
    )
    args = parser.parse_args()

    profiles = [PROCALCS_DIRECT]
    if args.also_beazer:
        profiles.append(BEAZER_ARIZONA)

    print(f"Seeding {len(profiles)} profile(s) against {args.base_url} ...")
    failures = 0
    for p in profiles:
        ok, msg = post_profile(args.base_url, p)
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] {p['client_id']:25s} {msg}")
        if not ok:
            failures += 1

    print()
    if failures:
        print(f"{failures} profile(s) failed.")
        return 1
    print("All profiles seeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
