"""
Tests for the Day-12 deterministic Labor lines (services.materials_rules.
generate_labor_lines + ClientProfile.labor).

Locks in:
  - LaborRates.is_configured gates emission (no phantom lines when
    contractor hasn't filled rates).
  - One line per configured task, suppressed when scope count is 0.
  - Quantity = count × hours_each, cost = quantity × hourly_rate.
  - Line shape matches what _format_rule_lines_for_bom emits (so the
    rest of the BOM pipeline doesn't need to special-case labor).
  - ClientProfile serialization round-trips the labor block.
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

from models.client_profile import (
    ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences, LaborRates,
)
from services.materials_rules import generate_labor_lines


def _profile(**labor_kw):
    """Build a minimal profile with labor rates overridden."""
    return ClientProfile(
        client_id="lab-test",
        client_name="Labor Test",
        supplier=SupplierInfo(supplier_name="WSF"),
        markup=MarkupTiers(),
        brands=BrandPreferences(),
        part_name_overrides=[],
        labor=LaborRates(**labor_kw),
    )


def _design(ahu=1, condenser=1, erv=0, rect_lf=0.0):
    runs = []
    if rect_lf > 0:
        runs.append({"shape": "rectangular", "length_ft": rect_lf, "diameter": 12})
    equipment = []
    equipment += [{"type": "AHU"}] * ahu
    equipment += [{"type": "Condenser"}] * condenser
    equipment += [{"type": "ERV"}] * erv
    return {"equipment": equipment, "duct_runs": runs, "fittings": [],
            "raw_rup_context": ""}


# ─── is_configured gate ────────────────────────────────────────────

def test_no_labor_lines_when_rates_unconfigured():
    profile = _profile()  # all zeros
    assert generate_labor_lines(_design(), profile=profile) == []


def test_no_labor_lines_when_only_hourly_rate_set():
    """Hourly rate without any per-task hours = nothing to bill."""
    profile = _profile(hourly_rate=85.0)
    assert generate_labor_lines(_design(), profile=profile) == []


def test_no_labor_lines_when_only_task_hours_set():
    """Task hours without an hourly rate = no cost basis."""
    profile = _profile(per_ahu_install_hours=4.0)
    assert generate_labor_lines(_design(), profile=profile) == []


# ─── Emission per task ─────────────────────────────────────────────

def test_ahu_install_emits_line_with_correct_math():
    profile = _profile(hourly_rate=85.0, per_ahu_install_hours=4.0)
    lines = generate_labor_lines(_design(ahu=2, condenser=0), profile=profile)
    ahu = [l for l in lines if l["sku"] == "LABOR-AHU"]
    assert len(ahu) == 1
    # 2 AHUs × 4 hr = 8 hr × $85/hr = $680
    assert ahu[0]["quantity"] == 8.0
    assert ahu[0]["unit_cost"] == 85.0
    assert ahu[0]["total_cost"] == 680.0


def test_duct_lf_labor_uses_total_lf():
    profile = _profile(hourly_rate=60.0, per_duct_lf_hours=0.1)
    lines = generate_labor_lines(_design(ahu=0, condenser=0, rect_lf=500.0),
                                  profile=profile)
    duct = [l for l in lines if l["sku"] == "LABOR-DUCT-LF"]
    assert len(duct) == 1
    # 500 LF × 0.1 hr = 50 hr × $60 = $3000
    assert duct[0]["quantity"] == 50.0
    assert duct[0]["total_cost"] == 3000.0


def test_zero_count_task_emits_no_line():
    """ERV install rate set, but the design has no ERV. No phantom line."""
    profile = _profile(hourly_rate=85.0, per_erv_install_hours=2.0)
    lines = generate_labor_lines(_design(ahu=0, condenser=0, erv=0),
                                  profile=profile)
    assert lines == []


def test_multiple_tasks_emit_multiple_lines():
    profile = _profile(
        hourly_rate=80.0,
        per_ahu_install_hours=4.0,
        per_condenser_install_hours=3.0,
        per_erv_install_hours=2.0,
        per_duct_lf_hours=0.05,
    )
    lines = generate_labor_lines(
        _design(ahu=1, condenser=1, erv=1, rect_lf=200.0),
        profile=profile,
    )
    skus = {l["sku"] for l in lines}
    assert skus == {"LABOR-AHU", "LABOR-CONDENSER", "LABOR-ERV", "LABOR-DUCT-LF"}


# ─── Line shape ────────────────────────────────────────────────────

def test_emitted_lines_have_bom_compatible_shape():
    profile = _profile(hourly_rate=85.0, per_ahu_install_hours=4.0)
    line = generate_labor_lines(_design(), profile=profile)[0]
    # Fields the BOM formatter / SPA / PDF read:
    for k in ("sku", "section", "category", "description",
              "quantity", "unit", "unit_cost", "total_cost", "source"):
        assert k in line, f"missing field {k}"
    assert line["section"] == "Labor"
    assert line["category"] == "labor"
    assert line["unit"] == "hr"
    assert line["source"] == "rules_engine"


# ─── Profile round-trip ────────────────────────────────────────────

def test_client_profile_round_trips_labor_block():
    rates = LaborRates(
        hourly_rate=90.0,
        per_ahu_install_hours=4.5,
        per_condenser_install_hours=3.0,
        per_erv_install_hours=2.0,
        per_heat_kit_install_hours=1.0,
        per_duct_lf_hours=0.08,
    )
    profile = ClientProfile(
        client_id="x", client_name="X",
        supplier=SupplierInfo(), markup=MarkupTiers(),
        brands=BrandPreferences(),
        labor=rates,
    )
    rt = ClientProfile.from_dict(profile.to_dict())
    assert rt.labor.hourly_rate == 90.0
    assert rt.labor.per_ahu_install_hours == 4.5
    assert rt.labor.per_duct_lf_hours == 0.08
    assert rt.labor.is_configured


def test_client_profile_from_dict_with_no_labor_block():
    """Older profile docs in Firestore have no 'labor' key. Must
    default to a zeroed LaborRates so they keep round-tripping."""
    minimal = {
        "client_id": "old", "client_name": "Old",
        "supplier": {"supplier_name": "WSF"},
        "markup": {}, "brands": {}, "part_name_overrides": [],
    }
    p = ClientProfile.from_dict(minimal)
    assert p.labor.hourly_rate == 0.0
    assert not p.labor.is_configured
