"""
Tests for the Day-14 Phase-1 equipment-model extraction +
bom_service._expand_equipment_models pass.

Locks in the behavior Richard's Comparison Summary 4.0 surfaced:
  - Per-instance equipment with real manufacturer + model gets pulled
    out of the EQUIP section, not just AHU names.
  - The rules engine no longer falls back to Goodman defaults when
    the RUP actually contains Trane (or other) model numbers.
  - One line per distinct model, count from EQUIP occurrence frequency.

Uses Richard's real 79th Ct Residence RUP as the regression fixture
so the test silently catches any future parser regression on that
file.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        _w = MagicMock(); _w.HTML = MagicMock(); _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w


RUP_FIXTURE = Path("/Users/geraldvillaran/Procalcs/RUPs/79th Ct Residence Load Calcs.rup")


def _design_data():
    """Parse the 79th Ct RUP once per test request. Returns the full
    design_data envelope or pytest.skip when the fixture isn't on the
    box (CI / fresh clone)."""
    if not RUP_FIXTURE.exists():
        pytest.skip(f"RUP fixture missing: {RUP_FIXTURE}")
    from utils.rup_parser import parse_rup_bytes
    return parse_rup_bytes(RUP_FIXTURE.read_bytes())


# ─── Parser-side checks ────────────────────────────────────────────

def test_parser_surfaces_trane_air_handler_model():
    d = _design_data()
    ahs = [e for e in d["equipment"]
           if e.get("type") == "air_handler" and e.get("model")]
    assert ahs, "expected at least one air_handler with a model"
    assert ahs[0]["manufacturer"] == "TRANE"
    assert ahs[0]["model"] == "5TAMXD06AV41"


def test_parser_surfaces_trane_condenser_with_count():
    d = _design_data()
    cs = [e for e in d["equipment"] if e.get("type") == "condenser"]
    assert cs, "expected at least one condenser entry"
    cond = next(e for e in cs if e.get("model") == "5TTV0X48A1")
    assert cond["manufacturer"] == "TRANE"
    assert cond["count"] >= 2  # appears twice in EQUIP


def test_parser_surfaces_trane_heat_kit_with_count():
    d = _design_data()
    hk = next(e for e in d["equipment"]
              if e.get("type") == "heat_kit" and e.get("model") == "BAYEAAC08BK1")
    assert hk["manufacturer"] == "TRANE"
    assert hk["count"] >= 3


def test_parser_preserves_ahu_naming_pattern():
    """AHU-1..AHU-5 must still appear so compute_scope sees ahu_count=5
    even though only the first carries the model."""
    d = _design_data()
    ah_names = sorted(e.get("name", "") for e in d["equipment"]
                      if e.get("type") == "air_handler")
    assert ah_names == ["AHU - 1", "AHU - 2", "AHU - 3", "AHU - 4", "AHU - 5"]


# ─── Bom-service model-expansion pass ──────────────────────────────

def _profile():
    from models.client_profile import (
        ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences,
    )
    return ClientProfile(
        client_id="trane-test",
        client_name="Trane Test",
        supplier=SupplierInfo(supplier_name="TRANE"),
        markup=MarkupTiers(equipment_pct=15.0),
        brands=BrandPreferences(ac_brand="Trane"),
        part_name_overrides=[],
    )


def _make_rule_line(*, sku, trigger, qty, description, unit_cost=2500.0):
    """Mimic a single _format_rule_lines_for_bom output row."""
    return {
        "sku":          sku,
        "supplier":     "GOODMAN",
        "section":      "Equipment",
        "category":     "equipment",
        "description":  description,
        "quantity":     qty,
        "unit":         "EA",
        "unit_cost":    unit_cost,
        "unit_price":   unit_cost * 1.15,
        "total_cost":   qty * unit_cost,
        "total_price":  qty * unit_cost * 1.15,
        "trigger":      trigger,
        "source":       "rules_engine",
    }


def test_expand_replaces_default_with_per_model_lines():
    from services.bom_service import _expand_equipment_models
    rule_lines = [
        _make_rule_line(sku="AHVE24BP1300A", trigger="ahu_present",
                        qty=5, description="AHU"),
    ]
    design = {
        "equipment": [
            {"type": "air_handler", "manufacturer": "TRANE",
             "model": "5TAMXD06AV41", "count": 2},
            {"type": "air_handler", "manufacturer": "TRANE",
             "model": "OTHER-MODEL-XYZ", "count": 3},
        ],
    }
    out = _expand_equipment_models(rule_lines, design, _profile())
    # Single default replaced with two per-model lines
    assert len(out) == 2
    skus = {l["sku"] for l in out}
    assert skus == {"5TAMXD06AV41", "OTHER-MODEL-XYZ"}
    # Qty matches the count from design_data
    for l in out:
        if l["sku"] == "5TAMXD06AV41":
            assert l["quantity"] == 2
        else:
            assert l["quantity"] == 3
    # Source tagged so cross-pollination + run-history know what hit
    assert all(l["source"] == "rup_equipment_model" for l in out)
    assert all(l["manufacturer"] == "TRANE" for l in out)


def test_expand_passes_non_equipment_lines_through():
    from services.bom_service import _expand_equipment_models
    rule_lines = [
        _make_rule_line(sku="MASTIC-RECT-GAL", trigger="always",
                        qty=7, description="Duct mastic"),
    ]
    design = {
        "equipment": [{"type": "air_handler", "manufacturer": "TRANE",
                       "model": "X", "count": 1}],
    }
    out = _expand_equipment_models(rule_lines, design, _profile())
    assert out == rule_lines


def test_expand_passes_through_when_design_has_no_models():
    """Without model info we MUST keep the catalog-default rule line —
    otherwise we silently drop equipment from the BOM."""
    from services.bom_service import _expand_equipment_models
    rule_lines = [_make_rule_line(sku="AHVE24BP1300A",
                                  trigger="ahu_present", qty=5,
                                  description="AHU")]
    design = {"equipment": [
        {"type": "air_handler", "name": "AHU - 1", "model": None},
    ]}
    out = _expand_equipment_models(rule_lines, design, _profile())
    assert out == rule_lines


def test_expand_handles_all_three_equipment_triggers():
    """Real 79th Ct shape: AHU + condenser + heat-kit triggers all
    fire, all get model expansion."""
    from services.bom_service import _expand_equipment_models
    rule_lines = [
        _make_rule_line(sku="A", trigger="ahu_present",      qty=5, description="AHU"),
        _make_rule_line(sku="B", trigger="condenser_present", qty=5, description="Condenser"),
        _make_rule_line(sku="C", trigger="heat_kit_present", qty=5, description="Heat Kit"),
    ]
    design = {"equipment": [
        {"type": "air_handler", "manufacturer": "TRANE", "model": "M1", "count": 1},
        {"type": "condenser",   "manufacturer": "TRANE", "model": "M2", "count": 2},
        {"type": "heat_kit",    "manufacturer": "TRANE", "model": "M3", "count": 3},
    ]}
    out = _expand_equipment_models(rule_lines, design, _profile())
    by_sku = {l["sku"]: l for l in out}
    assert by_sku["M1"]["quantity"] == 1
    assert by_sku["M2"]["quantity"] == 2
    assert by_sku["M3"]["quantity"] == 3


def test_expand_against_real_79th_ct_rup():
    """End-to-end against Richard's actual file: after expansion the
    AHU/condenser/heat-kit lines carry real Trane models, not Goodman
    defaults."""
    from services.bom_service import _expand_equipment_models
    design = _design_data()
    rule_lines = [
        _make_rule_line(sku="AHVE24BP1300A-DEFAULT", trigger="ahu_present",
                        qty=5, description="AHU", unit_cost=2875.0),
        _make_rule_line(sku="GZV6SA1810A-DEFAULT", trigger="condenser_present",
                        qty=5, description="Condenser", unit_cost=3450.0),
        _make_rule_line(sku="HKTSD05X1-DEFAULT", trigger="heat_kit_present",
                        qty=5, description="Electric Heat Kit", unit_cost=287.50),
    ]
    out = _expand_equipment_models(rule_lines, design, _profile())
    skus = {l["sku"] for l in out}
    # Trane models must appear; Goodman defaults must not
    assert "5TAMXD06AV41" in skus     # AHU
    assert "5TTV0X48A1" in skus       # condenser
    assert "BAYEAAC08BK1" in skus     # heat kit
    assert "AHVE24BP1300A-DEFAULT" not in skus
    assert "GZV6SA1810A-DEFAULT" not in skus
    assert "HKTSD05X1-DEFAULT" not in skus
    # All Trane-branded
    assert all(l["manufacturer"] == "TRANE" for l in out)
