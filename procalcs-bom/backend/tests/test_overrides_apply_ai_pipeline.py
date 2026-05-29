"""
Tests that contractor_overrides apply to AI-pipeline runs too
(bom_service._apply_contractor_overrides).

Closes the loop for the BOM Output page: Richard edits a line on
either the Wrightsoft BOM page OR the BOM Output page → next time
the same SKU shows up in an AI run for the same contractor, it
picks up the correction automatically and the line is tagged
catalog_verified_manual (green badge).
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


def _seed_override(client_id, supplier, sku, **kwargs):
    from extensions import db
    from models.contractor_override import ContractorOverride
    row = ContractorOverride.upsert(
        contractor_id=client_id,
        supplier=supplier,
        sku=sku,
        corrected_sku=kwargs.get("corrected_sku"),
        corrected_supplier=kwargs.get("corrected_supplier"),
        unit_price=kwargs.get("unit_price"),
        notes=kwargs.get("notes"),
        updated_by=kwargs.get("updated_by") or "test@procalcs.net",
    )
    db.session.commit()
    return row


def _ai_lines():
    """Minimum-shape line_items list mimicking what bom_service emits
    just before _apply_contractor_overrides is called."""
    return [
        # AI line with both supplier + sku → eligible
        {
            "sku":          "AHVE24BP1300A",
            "manufacturer": "GOOD",
            "description":  "Air Handling Unit",
            "quantity":     1,
            "unit":         "EA",
            "unit_cost":    0.0,
            "unit_price":   0.0,
            "total_cost":   0.0,
            "total_price":  0.0,
            "markup_pct":   15.0,
            "source":       "ai_with_catalog_sku",
        },
        # AI line with no sku → not eligible (no key to match on)
        {
            "sku":          None,
            "manufacturer": None,
            "description":  "Hanger straps",
            "quantity":     200,
            "unit":         "EA",
            "unit_cost":    31.20,
            "unit_price":   35.88,
            "total_cost":   6240.00,
            "total_price":  7176.00,
            "markup_pct":   15.0,
            "source":       "ai_inferred",
        },
        # Rules-engine line that happens to share a sku w/ no override → unchanged
        {
            "sku":          "MASTIC-RECT-GAL",
            "manufacturer": "RECT",
            "description":  "Duct mastic, 1 gallon",
            "quantity":     7,
            "unit":         "GAL",
            "unit_cost":    50.05,
            "unit_price":   57.56,
            "total_cost":   350.35,
            "total_price":  402.92,
            "markup_pct":   15.0,
            "source":       "rules_engine",
        },
    ]


# ─── Apply pass ────────────────────────────────────────────────────

def test_no_overrides_no_changes(app):
    from services.bom_service import _apply_contractor_overrides
    lines = _ai_lines()
    snapshot = [dict(l) for l in lines]
    applied = _apply_contractor_overrides(lines, "no-such-client")
    assert applied == 0
    assert lines == snapshot


def test_override_applies_to_matching_ai_line(app):
    from services.bom_service import _apply_contractor_overrides
    _seed_override(
        "test-c", "GOOD", "AHVE24BP1300A",
        unit_price=2875.00,
        notes="contractor's actual cost from Ferguson quote",
    )
    lines = _ai_lines()
    applied = _apply_contractor_overrides(lines, "test-c")

    assert applied == 1
    ahu = lines[0]
    assert ahu["source"] == "catalog_verified_manual"
    assert ahu["unit_cost"] == 2875.00
    # markup 15% → unit_price = 2875 × 1.15 = 3306.25
    assert ahu["unit_price"] == 3306.25
    assert ahu["total_cost"] == 2875.00       # qty=1
    assert ahu["total_price"] == 3306.25
    assert ahu["override_id"] is not None
    assert ahu["override_updated_by"] == "test@procalcs.net"


def test_override_can_correct_sku_and_supplier(app):
    from services.bom_service import _apply_contractor_overrides
    _seed_override(
        "test-c", "GOOD", "AHVE24BP1300A",
        corrected_sku="AHVE24BP1300A-NEW",
        corrected_supplier="GOODMAN",
    )
    lines = _ai_lines()
    _apply_contractor_overrides(lines, "test-c")
    assert lines[0]["sku"] == "AHVE24BP1300A-NEW"
    assert lines[0]["manufacturer"] == "GOODMAN"


def test_supplier_match_is_case_insensitive(app):
    """Wrightsoft sometimes mixes case (Good vs GOOD). Override
    matching should be case-folded so a 'good' line still finds the
    'GOOD' override."""
    from services.bom_service import _apply_contractor_overrides
    _seed_override("test-c", "GOOD", "AHVE24BP1300A", unit_price=2500)
    lines = _ai_lines()
    lines[0]["manufacturer"] = "good"     # lowercase variant
    applied = _apply_contractor_overrides(lines, "test-c")
    assert applied == 1
    assert lines[0]["unit_cost"] == 2500


def test_lines_without_supplier_or_sku_are_skipped(app):
    """The Hanger straps line has no supplier+sku → no key to match.
    Must remain untouched (no phantom override applied)."""
    from services.bom_service import _apply_contractor_overrides
    # Seed an override on something — irrelevant to Hanger straps
    _seed_override("test-c", "GOOD", "AHVE24BP1300A", unit_price=2500)
    lines = _ai_lines()
    before = dict(lines[1])
    _apply_contractor_overrides(lines, "test-c")
    after = dict(lines[1])
    # Hanger straps unchanged
    assert before == after


def test_rules_engine_lines_can_also_be_overridden(app):
    """Per-contractor prices on consumables matter too. A rules-engine
    mastic line with a price override should pick it up."""
    from services.bom_service import _apply_contractor_overrides
    _seed_override("test-c", "RECT", "MASTIC-RECT-GAL", unit_price=42.00)
    lines = _ai_lines()
    _apply_contractor_overrides(lines, "test-c")
    mastic = lines[2]
    assert mastic["source"] == "catalog_verified_manual"
    assert mastic["unit_cost"] == 42.00
    # markup 15% → 48.30; qty=7 → 338.10
    assert mastic["unit_price"] == 48.30
    assert mastic["total_cost"] == round(42.00 * 7, 2)
    assert mastic["total_price"] == round(48.30 * 7, 2)


def test_returns_zero_when_client_id_empty(app):
    from services.bom_service import _apply_contractor_overrides
    _seed_override("test-c", "GOOD", "AHVE24BP1300A", unit_price=2500)
    lines = _ai_lines()
    snap = [dict(l) for l in lines]
    assert _apply_contractor_overrides(lines, "") == 0
    assert lines == snap


def test_db_unavailable_returns_zero_gracefully(app, monkeypatch):
    """If list_for_client throws, the BOM Engine must not 500.
    The pass returns 0 and lines are unchanged."""
    from services.bom_service import _apply_contractor_overrides
    import models.contractor_override as co

    def boom(_cls, _client_id):
        raise RuntimeError("simulated db outage")

    monkeypatch.setattr(co.ContractorOverride, "list_for_client",
                        classmethod(boom))
    lines = _ai_lines()
    snap = [dict(l) for l in lines]
    assert _apply_contractor_overrides(lines, "test-c") == 0
    assert lines == snap
