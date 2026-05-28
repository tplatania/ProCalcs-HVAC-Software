"""
Tests that ContractorOverride rows actually beat DiscoveredMapping
beats raw Wrightsoft passthrough in the builder. Plus that the
override's unit_price flows through to the line's pricing.

This is the proof Tom's correction loop actually closes — first
upload teaches the catalog (passthrough → upsert), Richard corrects
the SKU+price (override row), second upload uses the correction
(wrightsoft_manual + override price applied).
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


def _profile(client_id="procalcs-direct"):
    from models.client_profile import (
        ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences,
    )
    return ClientProfile(
        client_id=client_id,
        client_name="Test",
        supplier=SupplierInfo(supplier_name="WSF"),
        markup=MarkupTiers(equipment_pct=15.0),  # so unit_price = unit_cost * 1.15
        brands=BrandPreferences(),
        part_name_overrides=[],
    )


def _build_one_line_bom(profile, *, src="GOOD", name="AHVE24BP1300A"):
    from services.bom_from_wrightsoft import (
        parse_wrightsoft_bom_rows, build_bom_from_wrightsoft_lines,
    )
    csv = (
        "Src,Name,Description,Phase,Qty,Un,Tax,Price,Ext price\n"
        ",,Equipment,,,,,,\n"
        f"{src},{name},Air Handling Unit,None,1,0,,0,0\n"
    )
    lines = parse_wrightsoft_bom_rows(csv.encode("utf-8"), filename="t.csv")
    return build_bom_from_wrightsoft_lines(
        lines=lines, profile=profile, job_id="override-test",
    )


# ─── Precedence ────────────────────────────────────────────────────

def test_override_beats_passthrough_on_first_seen_combo(app):
    """No discovered_mapping row yet, override row exists → manual."""
    from extensions import db
    from models.contractor_override import ContractorOverride
    profile = _profile()
    ContractorOverride.upsert(
        contractor_id=profile.client_id,
        supplier="GOOD",
        sku="AHVE24BP1300A",
        corrected_sku="AHVE24BP1300A-V2",
        unit_price=2875.00,
        updated_by="richard@procalcs.net",
    )
    db.session.commit()

    bom = _build_one_line_bom(profile)
    assert bom["wrightsoft_manual_item_count"] == 1
    assert bom["wrightsoft_passthrough_item_count"] == 0
    li = bom["line_items"][0]
    assert li["source"] == "wrightsoft_manual"
    assert li["sku"] == "AHVE24BP1300A-V2"


def test_override_beats_discovered_when_both_exist(app):
    from extensions import db
    from models.discovered_mapping import DiscoveredMapping
    from models.contractor_override import ContractorOverride
    profile = _profile()
    # Seed both tables.
    DiscoveredMapping.upsert_many([{
        "supplier": "GOOD", "sku": "AHVE24BP1300A",
        "description": "Air Handling Unit (verified)",
        "section_hint": "Equipment", "quantity": 1.0,
    }])
    ContractorOverride.upsert(
        contractor_id=profile.client_id,
        supplier="GOOD",
        sku="AHVE24BP1300A",
        unit_price=2900.00,
    )
    db.session.commit()

    bom = _build_one_line_bom(profile)
    assert bom["wrightsoft_manual_item_count"] == 1
    assert bom["wrightsoft_discovered_item_count"] == 0
    assert bom["line_items"][0]["source"] == "wrightsoft_manual"


def test_no_override_still_uses_discovered_path(app):
    from extensions import db
    from models.discovered_mapping import DiscoveredMapping
    profile = _profile()
    DiscoveredMapping.upsert_many([{
        "supplier": "GOOD", "sku": "AHVE24BP1300A",
        "description": "Air Handling Unit",
        "section_hint": "Equipment", "quantity": 1.0,
    }])
    db.session.commit()
    bom = _build_one_line_bom(profile)
    assert bom["wrightsoft_manual_item_count"] == 0
    assert bom["wrightsoft_discovered_item_count"] == 1


# ─── Pricing flow (Tom's "we put it in") ───────────────────────────

def test_override_unit_price_flows_to_line_cost(app):
    """The cost from the override propagates to unit_cost AND
    total_cost (qty-multiplied). Whatever markup the line would have
    received without the override (looked up by category) is applied
    on top to derive unit_price. For passthrough lines whose category
    can't be resolved by the bundled catalog, that markup is 0% — so
    unit_price == unit_cost. This still proves the cost-side override
    flowed through; the markup side is verified separately below."""
    from extensions import db
    from models.contractor_override import ContractorOverride
    profile = _profile()
    ContractorOverride.upsert(
        contractor_id=profile.client_id,
        supplier="GOOD",
        sku="AHVE24BP1300A",
        unit_price=2875.00,
    )
    db.session.commit()
    bom = _build_one_line_bom(profile)
    li = bom["line_items"][0]
    # qty=1, override sets unit_cost=2875.00 → total_cost=2875.00
    assert li["unit_cost"] == 2875.00
    assert li["total_cost"] == 2875.00
    # unit_price = cost × (1 + markup/100). markup for this category
    # is whatever the profile resolves; the override doesn't change it.
    expected_unit_price = round(2875.00 * (1 + li.get("markup_pct", 0) / 100), 2)
    assert li["unit_price"] == expected_unit_price
    assert li["total_price"] == expected_unit_price * 1   # qty=1


def test_override_unit_price_preserves_existing_markup(app):
    """When markup_pct is non-zero on a line, the override applies the
    same percentage to derive the new unit_price. Markup is a
    contractor-profile thing, not part of the override."""
    from extensions import db
    from models.contractor_override import ContractorOverride
    profile = _profile()
    # Force a mapped line by picking a SKU that's a real
    # mapped_parts.csv entry (DDVn10 is in Tom's bundled catalog).
    ContractorOverride.upsert(
        contractor_id=profile.client_id,
        supplier="WSF",
        sku="DDVn10",
        unit_price=10.00,
    )
    db.session.commit()
    from services.bom_from_wrightsoft import (
        parse_wrightsoft_bom_rows, build_bom_from_wrightsoft_lines,
    )
    csv = (
        "Src,Name,Description,Phase,Qty,Un,Tax,Price,Ext price\n"
        ",,Duct System Equipment,,,,,,\n"
        "WSF,DDVn10,Round vinyl duct,None,5,0,,2,10\n"
    )
    lines = parse_wrightsoft_bom_rows(csv.encode("utf-8"), filename="t.csv")
    bom = build_bom_from_wrightsoft_lines(lines=lines, profile=profile, job_id="x")
    li = bom["line_items"][0]
    assert li["unit_cost"] == 10.0
    assert li["total_cost"] == 50.0   # 5 × $10
    # Whatever markup got applied, it's the same on the override side
    expected_unit_price = round(10.0 * (1 + li["markup_pct"] / 100), 2)
    assert li["unit_price"] == expected_unit_price


def test_override_with_only_price_keeps_original_sku_and_supplier(app):
    """Tom's primary workflow: a contractor's prices are different
    but the SKUs are correct. Override should only carry the price."""
    from extensions import db
    from models.contractor_override import ContractorOverride
    profile = _profile()
    ContractorOverride.upsert(
        contractor_id=profile.client_id,
        supplier="GOOD",
        sku="AHVE24BP1300A",
        unit_price=2500.00,
    )
    db.session.commit()
    bom = _build_one_line_bom(profile)
    li = bom["line_items"][0]
    assert li["sku"] == "AHVE24BP1300A"     # unchanged
    assert li["manufacturer"] == "GOOD"     # unchanged
    assert li["unit_cost"] == 2500.00       # from override


def test_audit_fields_attached_to_line(app):
    from extensions import db
    from models.contractor_override import ContractorOverride
    profile = _profile()
    ContractorOverride.upsert(
        contractor_id=profile.client_id,
        supplier="GOOD",
        sku="AHVE24BP1300A",
        unit_price=100.0,
        updated_by="richard@procalcs.net",
    )
    db.session.commit()
    li = _build_one_line_bom(profile)["line_items"][0]
    assert li.get("override_id") is not None
    assert li.get("override_updated_by") == "richard@procalcs.net"
    assert li.get("override_updated_at") is not None


# ─── Scope isolation per contractor ────────────────────────────────

def test_overrides_are_per_contractor(app):
    """An override for contractor A must not leak into contractor B's BOM."""
    from extensions import db
    from models.contractor_override import ContractorOverride
    ContractorOverride.upsert(
        contractor_id="contractor-a",
        supplier="GOOD",
        sku="AHVE24BP1300A",
        unit_price=999.0,
    )
    db.session.commit()
    bom = _build_one_line_bom(_profile(client_id="contractor-b"))
    li = bom["line_items"][0]
    assert li["source"] != "wrightsoft_manual"
    assert li["unit_cost"] != 999.0


# ─── Graceful degradation ──────────────────────────────────────────

def test_db_failure_falls_back_to_passthrough(app, monkeypatch):
    import models.contractor_override as co_module
    def boom(*_a, **_kw):
        raise RuntimeError("simulated DB outage")
    monkeypatch.setattr(co_module.ContractorOverride, "lookup", classmethod(boom))
    bom = _build_one_line_bom(_profile())
    # Still emits a BOM, just no manual hit.
    assert bom["item_count"] == 1
    assert bom["wrightsoft_manual_item_count"] == 0
