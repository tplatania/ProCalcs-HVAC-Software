#!/usr/bin/env python3
"""
Seed the Firestore ``sku_catalog`` collection from the checked-in JSON.

Usage:
    # From procalcs-bom/ root, with FIRESTORE_PROJECT_ID and
    # GOOGLE_APPLICATION_CREDENTIALS set in env (or a service-account.json
    # at the repo root that python-dotenv picks up):
    python scripts/seed_sku_catalog.py            # add missing SKUs only
    python scripts/seed_sku_catalog.py --force    # overwrite existing
    python scripts/seed_sku_catalog.py --dry-run  # show what would happen

Idempotent by default — running twice without --force is safe.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the backend package importable when running from the repo root.
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "backend"
sys.path.insert(0, str(BACKEND))

from google.cloud import firestore  # noqa: E402

JSON_PATH = BACKEND / "data" / "sku_catalog.json"
COLLECTION = "sku_catalog"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="Overwrite items that already exist")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen without writing")
    args = parser.parse_args()

    raw = json.loads(JSON_PATH.read_text())
    seed_items = raw.get("items", [])
    print(f"Loaded {len(seed_items)} items from {JSON_PATH}")

    if args.dry_run:
        print("DRY RUN — no Firestore writes")
    db = firestore.Client() if not args.dry_run else None

    now = datetime.now(timezone.utc)
    created, updated, skipped = 0, 0, 0

    for item in seed_items:
        sku = item.get("sku")
        if not sku:
            print(f"  skip: missing sku → {item}")
            skipped += 1
            continue

        if args.dry_run:
            print(f"  would seed {sku} ({item.get('section')})")
            continue

        doc_ref = db.collection(COLLECTION).document(sku)
        existing = doc_ref.get()

        record = {
            **item,
            "disabled": item.get("disabled", False),
            "updated_at": now,
            "created_at": now if not existing.exists else
                          (existing.to_dict() or {}).get("created_at", now),
            "created_by": "seed_script" if not existing.exists else
                          (existing.to_dict() or {}).get("created_by", "seed_script"),
            "updated_by": "seed_script",
        }

        if existing.exists and not args.force:
            print(f"  skip {sku}: already exists (use --force to overwrite)")
            skipped += 1
        elif existing.exists:
            doc_ref.set(record)
            print(f"  update {sku}")
            updated += 1
        else:
            doc_ref.set(record)
            print(f"  create {sku}")
            created += 1

    print(f"\nDone — created={created} updated={updated} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
