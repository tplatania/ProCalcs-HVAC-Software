"""
Tests for the Day-12 consumables rules extension to materials_rules.

Locks in:
  - per_lf_ratio quantity mode (LF ÷ divisor, rounded up)
  - duct_runs.total_lf  + fittings.total scope sources
  - Consumables section → 'consumable' category mapping
  - The five seeded SKUs (mastic, foil tape, hanger straps, screws,
    brushes) actually fire on a normal-shaped design and produce the
    quantities Tom would expect (no phantom 1000-gal mastic lines, no
    missing lines on small projects).

Without this coverage the consumables block silently regresses if
someone tweaks the divisors or removes a source.
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

from services.materials_rules import (
    Scope, compute_scope, resolve_quantity, generate_rule_lines,
    _resolve_source,
)
from services import sku_catalog


@pytest.fixture(autouse=True)
def _fresh_catalog():
    """Force a clean reload of the SKU catalog before each test, and
    tear down any leaked mock.patch() interventions from other test
    modules. test_bom_runs_routes patches sku_catalog.all_items inside
    a try/finally that re-creates the patch handle in the finally
    block — the stop() therefore runs on a fresh handle and the
    original patch leaks into subsequent tests, leaving all_items
    permanently returning []. mock.patch.stopall() is a no-op when
    nothing's leaked but rescues us when something has."""
    from unittest import mock
    mock.patch.stopall()
    sku_catalog.reload()
    yield
    mock.patch.stopall()
    sku_catalog.reload()


# ─── per_lf_ratio resolver ─────────────────────────────────────────

def test_per_lf_ratio_rounds_up():
    """750 LF ÷ 100 = 7.5 → rounds up to 8 gallons. No 'half a gallon'
    BOM lines — contractors order whole units."""
    scope = Scope(rectangular_lf=750.0)
    rule = {"mode": "per_lf_ratio", "source": "duct_runs.total_lf", "divisor": 100}
    assert resolve_quantity(rule, scope) == 8.0


def test_per_lf_ratio_returns_zero_when_no_duct():
    """No duct → no consumables. A pure-equipment job (e.g. swap-out
    of a condenser only) must not emit phantom mastic lines."""
    scope = Scope()
    rule = {"mode": "per_lf_ratio", "source": "duct_runs.total_lf", "divisor": 100}
    assert resolve_quantity(rule, scope) == 0.0


def test_per_lf_ratio_rejects_missing_or_zero_divisor():
    scope = Scope(rectangular_lf=100.0)
    assert resolve_quantity(
        {"mode": "per_lf_ratio", "source": "duct_runs.total_lf"}, scope
    ) == 0.0
    assert resolve_quantity(
        {"mode": "per_lf_ratio", "source": "duct_runs.total_lf", "divisor": 0}, scope
    ) == 0.0
    assert resolve_quantity(
        {"mode": "per_lf_ratio", "source": "duct_runs.total_lf", "divisor": "bad"}, scope
    ) == 0.0


# ─── total_lf + total_fittings sources ─────────────────────────────

def test_total_duct_lf_sums_across_shapes():
    scope = Scope(rectangular_lf=300.0, rheia_lf=200.0, round_vinyl_count=50)
    assert scope.total_duct_lf == 550.0
    assert _resolve_source("duct_runs.total_lf", scope) == 550.0


def test_total_fitting_count_sums_across_types():
    scope = Scope(
        elbow_count=10,
        rheia_takeoffs=5,
        rheia_high_sidewall_endpoints=4,
        rheia_ceiling_endpoints=6,
    )
    assert scope.total_fitting_count == 25
    assert _resolve_source("fittings.total", scope) == 25


# ─── End-to-end: real catalog fires consumables on a duct project ──

def _design_with_duct(rect_lf=500.0, rheia_lf=200.0, fittings=20):
    """Compact design_data shape with enough scope to trigger
    consumables. Numbers chosen so each consumable's qty is non-trivial.
    Field names match what compute_scope() actually reads
    (length_ft / diameter — NOT total_lf / diameter_in)."""
    return {
        "equipment": [{"type": "AHU"}],
        "duct_runs": [
            {"shape": "rectangular", "length_ft": rect_lf, "diameter": 12},
            {"shape": "round",       "length_ft": rheia_lf, "diameter": 3},
        ],
        "fittings": [{"type": "elbow"}] * fittings,
        "raw_rup_context": "rectangular duct 12x10, round 3-in flex",
    }


def test_consumables_fire_on_a_duct_project():
    lines = generate_rule_lines(_design_with_duct())
    cons = [l for l in lines if l.get("section") == "Consumables"]
    skus = {l["sku"] for l in cons}
    assert "MASTIC-RECT-GAL" in skus
    assert "FOIL-TAPE-NASHUA-ROLL" in skus
    assert "HANGER-STRAP-EA" in skus
    # Mastic-brush rides the duct LF too
    assert "MASTIC-BRUSH-EA" in skus


def test_consumables_quantities_match_expected_ratios():
    """500 LF rect + 200 LF rheia + (round=0 count) = 700 LF total.
    Mastic: 700 / 100 = 7 gal
    Foil tape: 700 / 50 = 14 rolls
    Hanger straps: 700 / 8 = 87.5 → 88
    Mastic brushes: 700 / 100 = 7
    """
    lines = generate_rule_lines(_design_with_duct(rect_lf=500.0, rheia_lf=200.0))
    by_sku = {l["sku"]: l for l in lines if l.get("section") == "Consumables"}
    assert by_sku["MASTIC-RECT-GAL"]["quantity"] == 7
    assert by_sku["FOIL-TAPE-NASHUA-ROLL"]["quantity"] == 14
    assert by_sku["HANGER-STRAP-EA"]["quantity"] == 88
    assert by_sku["MASTIC-BRUSH-EA"]["quantity"] == 7


def test_consumables_units_are_human_readable():
    """The 'unit' override on each rule must reach the line item so
    the SPA/PDF show GAL/ROLL/EA/BOX, not the resolver default 'lf'."""
    lines = generate_rule_lines(_design_with_duct())
    by_sku = {l["sku"]: l for l in lines if l.get("section") == "Consumables"}
    assert by_sku["MASTIC-RECT-GAL"]["unit"] == "GAL"
    assert by_sku["FOIL-TAPE-NASHUA-ROLL"]["unit"] == "ROLL"
    assert by_sku["HANGER-STRAP-EA"]["unit"] == "EA"
    assert by_sku["SHEETMETAL-SCREW-BOX"]["unit"] == "BOX"


def test_no_consumables_on_a_no_duct_design():
    """Equipment-only swap-out (e.g. condenser replacement) must not
    emit phantom consumables. The BOM should only have the equipment
    line itself."""
    design = {
        "equipment": [{"type": "Condenser"}],
        "duct_runs": [],
        "fittings": [],
        "raw_rup_context": "",
    }
    lines = generate_rule_lines(design)
    cons = [l for l in lines if l.get("section") == "Consumables"]
    # Duct-driven consumables suppressed
    duct_driven_skus = {"MASTIC-RECT-GAL", "FOIL-TAPE-NASHUA-ROLL",
                        "HANGER-STRAP-EA", "MASTIC-BRUSH-EA"}
    emitted = {l["sku"] for l in cons}
    assert duct_driven_skus.isdisjoint(emitted), (
        f"phantom consumables emitted with no duct: {emitted & duct_driven_skus}"
    )


def test_consumables_section_maps_to_consumable_category():
    """The legacy 'category' field on each line drives the SPA's chip
    color. Consumables section must map to the 'consumable' bucket."""
    lines = generate_rule_lines(_design_with_duct())
    cons = [l for l in lines if l.get("section") == "Consumables"]
    assert cons, "Sanity: expected consumables to fire"
    for l in cons:
        assert l.get("category") == "consumable", (
            f"{l['sku']} has wrong category: {l.get('category')}"
        )


# ─── Catalog integrity ─────────────────────────────────────────────

def test_consumables_section_accepted_by_validation():
    assert "Consumables" in sku_catalog.VALID_SECTIONS


def test_per_lf_ratio_mode_accepted_by_validation():
    assert "per_lf_ratio" in sku_catalog.VALID_QUANTITY_MODES
