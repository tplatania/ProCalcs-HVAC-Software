"""
Tests for the Day-13 ContractorOverride model.

Locks in:
  - upsert inserts new rows and updates existing ones in place
  - lookup is case-insensitive on supplier
  - partial updates respect None-means-don't-touch vs ""-means-clear
  - list_for_contractor returns newest-first
"""

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


def test_upsert_inserts_new_row(app):
    from extensions import db
    from models.contractor_override import ContractorOverride
    row = ContractorOverride.upsert(
        contractor_id="procalcs-direct",
        supplier="GOOD",
        sku="AHVE24BP1300A",
        unit_price=2875.00,
        updated_by="richard@procalcs.net",
    )
    db.session.commit()
    assert row.id is not None
    assert row.unit_price == 2875.00
    assert row.updated_by == "richard@procalcs.net"


def test_upsert_updates_existing_in_place(app):
    from extensions import db
    from models.contractor_override import ContractorOverride
    ContractorOverride.upsert(
        contractor_id="c1", supplier="GOOD", sku="X1", unit_price=100.0,
    )
    db.session.commit()
    ContractorOverride.upsert(
        contractor_id="c1", supplier="GOOD", sku="X1", unit_price=150.0,
    )
    db.session.commit()
    rows = ContractorOverride.list_for_contractor("c1")
    assert len(rows) == 1
    assert rows[0].unit_price == 150.0


def test_lookup_normalizes_supplier_case(app):
    from extensions import db
    from models.contractor_override import ContractorOverride
    ContractorOverride.upsert(
        contractor_id="c1", supplier="good", sku="X1", unit_price=10.0,
    )
    db.session.commit()
    assert ContractorOverride.lookup(
        contractor_id="c1", supplier="GOOD", sku="X1") is not None
    assert ContractorOverride.lookup(
        contractor_id="c1", supplier="good", sku="X1") is not None
    assert ContractorOverride.lookup(
        contractor_id="c1", supplier="GoOd", sku="X1") is not None


def test_lookup_returns_none_for_unknown(app):
    from models.contractor_override import ContractorOverride
    assert ContractorOverride.lookup(
        contractor_id="missing", supplier="GOOD", sku="X1") is None
    assert ContractorOverride.lookup(
        contractor_id="", supplier="GOOD", sku="X1") is None


def test_partial_update_preserves_unset_fields(app):
    """Passing None for a field means 'leave alone'. Passing empty
    string means 'clear'. Critical for the SPA edit drawer where the
    user may only touch one field (e.g. price only)."""
    from extensions import db
    from models.contractor_override import ContractorOverride
    ContractorOverride.upsert(
        contractor_id="c1", supplier="GOOD", sku="X1",
        corrected_sku="ORIG-CORRECTED",
        unit_price=100.0,
        notes="initial note",
    )
    db.session.commit()
    # Update only the price.
    ContractorOverride.upsert(
        contractor_id="c1", supplier="GOOD", sku="X1",
        unit_price=200.0,
    )
    db.session.commit()
    row = ContractorOverride.lookup(contractor_id="c1", supplier="GOOD", sku="X1")
    assert row.unit_price == 200.0
    assert row.corrected_sku == "ORIG-CORRECTED"   # preserved
    assert row.notes == "initial note"             # preserved


def test_partial_update_can_clear_a_field(app):
    """Explicit empty string clears a previously-set string field."""
    from extensions import db
    from models.contractor_override import ContractorOverride
    ContractorOverride.upsert(
        contractor_id="c1", supplier="GOOD", sku="X1",
        corrected_sku="WAS-SET",
        notes="WAS-SET",
    )
    db.session.commit()
    ContractorOverride.upsert(
        contractor_id="c1", supplier="GOOD", sku="X1",
        corrected_sku="",
        notes="",
    )
    db.session.commit()
    row = ContractorOverride.lookup(contractor_id="c1", supplier="GOOD", sku="X1")
    assert row.corrected_sku is None
    assert row.notes is None


def test_unique_constraint_prevents_duplicates_per_contractor(app):
    """Same (Src, Name) for different contractors → two rows.
    Same (Src, Name) for the same contractor → upserted into one row."""
    from extensions import db
    from models.contractor_override import ContractorOverride
    ContractorOverride.upsert(
        contractor_id="c1", supplier="GOOD", sku="X1", unit_price=10.0)
    ContractorOverride.upsert(
        contractor_id="c2", supplier="GOOD", sku="X1", unit_price=20.0)
    db.session.commit()
    assert len(ContractorOverride.list_for_contractor("c1")) == 1
    assert len(ContractorOverride.list_for_contractor("c2")) == 1
    assert ContractorOverride.lookup(
        contractor_id="c1", supplier="GOOD", sku="X1").unit_price == 10.0
    assert ContractorOverride.lookup(
        contractor_id="c2", supplier="GOOD", sku="X1").unit_price == 20.0


def test_list_for_contractor_orders_newest_first(app):
    import time
    from extensions import db
    from models.contractor_override import ContractorOverride
    ContractorOverride.upsert(contractor_id="c1", supplier="GOOD", sku="OLD")
    db.session.commit()
    time.sleep(0.01)
    ContractorOverride.upsert(contractor_id="c1", supplier="GOOD", sku="NEW")
    db.session.commit()
    rows = ContractorOverride.list_for_contractor("c1")
    assert [r.sku for r in rows] == ["NEW", "OLD"]


def test_upsert_rejects_missing_keys(app):
    from models.contractor_override import ContractorOverride
    with pytest.raises(ValueError):
        ContractorOverride.upsert(contractor_id="", supplier="GOOD", sku="X")
    with pytest.raises(ValueError):
        ContractorOverride.upsert(contractor_id="c1", supplier="", sku="X")
    with pytest.raises(ValueError):
        ContractorOverride.upsert(contractor_id="c1", supplier="GOOD", sku="")
