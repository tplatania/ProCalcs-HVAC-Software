"""mdb_to_sqlite.py — Wrightsoft RPRUWSF parts catalog → SQLite.

Extracts the tables the catalog API serves from the Wrightsoft Access
database and loads them into a single SQLite file the Express server
reads via node:sqlite.

Requires mdbtools (`brew install mdbtools`).

Usage:
    python3 scripts/catalog-etl/mdb_to_sqlite.py \
        --mdb "~/Procalcs/BOM Module/Data - Copy/RPRUWSF.mdb" \
        --out ~/Procalcs/Catalogs/catalog.sqlite

Neither the .mdb nor the .sqlite is ever committed — the repo carries
only this ETL. crm.mdb is customer PII: this script refuses it.

Tables extracted:
    ActItem     — the parts catalog (38k+ rows): part number, source,
                  category, description, list/cost/price fields.
    PartSource  — manufacturer/supplier registry (RHEA = Rheia, GOOD =
                  Goodman, ...).
    ActCateg    — category labels for ActItem.Category codes.
    GenItem     — generic (unsourced) catalog items.
"""

from __future__ import annotations

import argparse
import csv
import io
import sqlite3
import subprocess
import sys
from pathlib import Path

TABLES = ["ActItem", "PartSource", "ActCateg", "GenItem"]


def export_table(mdb: Path, table: str) -> list[dict]:
    out = subprocess.run(
        ["mdb-export", str(mdb), table],
        capture_output=True, text=True, check=True,
    ).stdout
    return list(csv.DictReader(io.StringIO(out)))


def sanitize(col: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in col)


def load(mdb: Path, out: Path) -> None:
    if "crm" in mdb.name.lower():
        sys.exit("refusing crm.mdb — customer PII is do-not-ingest")

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    con = sqlite3.connect(out)

    for table in TABLES:
        rows = export_table(mdb, table)
        if not rows:
            print(f"  {table}: empty, skipped")
            continue
        cols = [sanitize(c) for c in rows[0].keys()]
        col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
        con.execute(f'CREATE TABLE "{table}" ({col_defs})')
        placeholders = ", ".join("?" for _ in cols)
        con.executemany(
            f'INSERT INTO "{table}" VALUES ({placeholders})',
            ([r.get(orig, "") for orig in rows[0].keys()] for r in rows),
        )
        print(f"  {table}: {len(rows)} rows")

    # Indexes for the API's access patterns
    con.execute('CREATE INDEX idx_actitem_pn ON ActItem("PN")')
    con.execute('CREATE INDEX idx_actitem_psrc ON ActItem("PSrc")')
    con.execute('CREATE INDEX idx_actitem_desc ON ActItem("Description")')
    con.commit()

    # Provenance stamp
    con.execute("CREATE TABLE _meta (key TEXT, value TEXT)")
    con.execute(
        "INSERT INTO _meta VALUES ('source_mdb', ?), ('etl_script', ?)",
        (mdb.name, "scripts/catalog-etl/mdb_to_sqlite.py"),
    )
    con.commit()
    con.close()
    print(f"→ {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mdb", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    load(Path(a.mdb).expanduser(), Path(a.out).expanduser())
