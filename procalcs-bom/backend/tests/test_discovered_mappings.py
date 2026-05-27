"""
Tests for the Day-12 discovered_mappings auto-learn flow.

Locks in:
  - upsert_many inserts new rows + increments existing ones
  - lookup() round-trips correctly
  - bom_from_wrightsoft writes to the table on a passthrough line
  - second BOM with the same (supplier, sku) flips that line's source
    from 'wrightsoft_passthrough' to 'wrightsoft_discovered' and bumps
    times_seen on the row

This is the proof that the auto-learn loop actually closes — first
upload teaches the catalog, second upload uses it.
"""

import io
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        _w = MagicMock(); _w.HTML = MagicMock(); _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w

for _k, _v in (
    ('DATABASE_URL',         'sqlite:///:memory:'),
    ('ANTHROPIC_API_KEY',    'dev-test'),
    ('FIRESTORE_PROJECT_ID', 'dev-test'),
):
    if not os.environ.get(_k):
        os.environ[_k] = _v
os.environ['SERVICE_SHARED_SECRET'] = ''


@pytest.fixture
def app():
    from app import create_app
    from extensions import db
    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


# ─── Model layer ───────────────────────────────────────────────────

def test_upsert_inserts_new_row(app):
    from extensions import db
    from models.discovered_mapping import DiscoveredMapping
    touched = DiscoveredMapping.upsert_many([
        {"supplier": "GOOD", "sku": "AHVE24BP1300A",
         "description": "Air Handling Unit", "section_hint": "Equipment",
         "quantity": 1.0},
    ], run_id=42)
    db.session.commit()
    assert touched == 1
    row = DiscoveredMapping.lookup(supplier="GOOD", sku="AHVE24BP1300A")
    assert row is not None
    assert row.times_seen == 1
    assert row.total_quantity == 1.0
    assert row.first_seen_run_id == 42


def test_upsert_increments_existing_row(app):
    from extensions import db
    from models.discovered_mapping import DiscoveredMapping
    DiscoveredMapping.upsert_many([
        {"supplier": "BROAN", "sku": "B150E75NT", "description": "ERV",
         "section_hint": "Equipment", "quantity": 1.0},
    ], run_id=1)
    db.session.commit()
    DiscoveredMapping.upsert_many([
        {"supplier": "BROAN", "sku": "B150E75NT", "description": "ERV",
         "section_hint": "Equipment", "quantity": 2.0},
    ], run_id=2)
    db.session.commit()
    row = DiscoveredMapping.lookup(supplier="BROAN", sku="B150E75NT")
    assert row.times_seen == 2
    assert row.total_quantity == 3.0
    assert row.first_seen_run_id == 1
    assert row.last_seen_run_id == 2


def test_upsert_skips_rows_missing_supplier_or_sku(app):
    from extensions import db
    from models.discovered_mapping import DiscoveredMapping
    touched = DiscoveredMapping.upsert_many([
        {"supplier": "GOOD", "sku": "", "quantity": 1.0},
        {"supplier": "",    "sku": "FOO", "quantity": 1.0},
        {"supplier": "GOOD", "sku": "REAL-SKU", "quantity": 1.0},
    ])
    db.session.commit()
    assert touched == 1
    assert DiscoveredMapping.lookup(supplier="GOOD", sku="REAL-SKU") is not None


def test_upsert_supplier_normalized_to_uppercase(app):
    from extensions import db
    from models.discovered_mapping import DiscoveredMapping
    DiscoveredMapping.upsert_many([
        {"supplier": "rhea", "sku": "10-00-190", "quantity": 1.0},
    ])
    db.session.commit()
    assert DiscoveredMapping.lookup(supplier="RHEA", sku="10-00-190") is not None
    assert DiscoveredMapping.lookup(supplier="rhea", sku="10-00-190") is not None


# ─── Integration with bom_from_wrightsoft ──────────────────────────

def _build_richmond_bom(profile):
    """Pipe a small chunk of the Richmond fixture through the builder."""
    from services.bom_from_wrightsoft import (
        parse_wrightsoft_bom_rows, build_bom_from_wrightsoft_lines,
    )
    csv = (
        "Src,Name,Description,Phase,Qty,Un,Tax,Price,Ext price\n"
        ",,Equipment,,,,,,\n"
        "GOOD,AHVE24BP1300A,Air Handling Unit,None,1,0,,0,0\n"
        "BROAN,B150E75NT,ERV,None,1,0,,0,0\n"
    )
    lines = parse_wrightsoft_bom_rows(csv.encode("utf-8"), filename="rich.csv")
    return build_bom_from_wrightsoft_lines(
        lines=lines, profile=profile, job_id="auto-learn-test",
    )


def _profile():
    from models.client_profile import (
        ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences,
    )
    return ClientProfile(
        client_id="auto-learn",
        client_name="Auto-Learn Test",
        supplier=SupplierInfo(supplier_name="WSF"),
        markup=MarkupTiers(),
        brands=BrandPreferences(),
        part_name_overrides=[],
    )


def test_first_run_writes_passthrough_and_seeds_table(app):
    from extensions import db
    from models.discovered_mapping import DiscoveredMapping
    bom = _build_richmond_bom(_profile())
    db.session.commit()

    # First time we've seen these SKUs — both passthrough, zero discovered.
    assert bom["wrightsoft_passthrough_item_count"] == 2
    assert bom["wrightsoft_discovered_item_count"] == 0

    # Table now has both rows.
    good = DiscoveredMapping.lookup(supplier="GOOD", sku="AHVE24BP1300A")
    broan = DiscoveredMapping.lookup(supplier="BROAN", sku="B150E75NT")
    assert good is not None and good.times_seen == 1
    assert broan is not None and broan.times_seen == 1


def test_second_run_promotes_to_discovered(app):
    from extensions import db
    from models.discovered_mapping import DiscoveredMapping
    # First run — seeds table.
    _build_richmond_bom(_profile())
    db.session.commit()
    # Second run — should now hit the discovered path.
    bom = _build_richmond_bom(_profile())
    db.session.commit()

    assert bom["wrightsoft_discovered_item_count"] == 2
    assert bom["wrightsoft_passthrough_item_count"] == 0

    # Per-line check too
    sources = [li["source"] for li in bom["line_items"]]
    assert sources.count("wrightsoft_discovered") == 2
    assert sources.count("wrightsoft_passthrough") == 0

    # Table rows now have times_seen=2
    good = DiscoveredMapping.lookup(supplier="GOOD", sku="AHVE24BP1300A")
    assert good.times_seen == 2
    assert good.total_quantity == 2.0   # 1 + 1 across the two runs


def test_db_unavailable_falls_back_to_passthrough(app, monkeypatch):
    """If the lookup throws (e.g. DB hiccup), the builder must still
    return a valid BOM — the line falls through to passthrough rather
    than 500ing. Best-effort auto-learn must never poison the
    response."""
    import models.discovered_mapping as dm

    def boom(*_a, **_kw):
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(dm.DiscoveredMapping, "lookup", classmethod(boom))
    monkeypatch.setattr(dm.DiscoveredMapping, "upsert_many", classmethod(boom))

    bom = _build_richmond_bom(_profile())
    # Both lines still emitted, just as passthrough.
    assert bom["item_count"] == 2
    assert bom["wrightsoft_passthrough_item_count"] == 2
    assert bom["wrightsoft_discovered_item_count"] == 0
