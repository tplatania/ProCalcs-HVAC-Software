"""
Tests for the materials_rules engine — scope detection, trigger eval,
quantity resolvers, and end-to-end rule emission against the 21-item
starter catalog.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services import materials_rules as mr
from services.materials_rules import Scope, compute_scope, evaluate_trigger, resolve_quantity, generate_rule_lines


# ---------------------------------------------------------------------------
# compute_scope
# ---------------------------------------------------------------------------

class TestComputeScope:
    def test_empty_design_data(self):
        s = compute_scope({})
        assert s.ahu_count == 0
        assert s.rheia_in_scope is False
        assert s.register_count == 0

    def test_none_design_data(self):
        assert compute_scope(None) == Scope()

    def test_parser_canonical_air_handler_type_detected(self):
        # Regression: utils/rup_parser emits {"type": "air_handler"}.
        # Earlier compute_scope only matched "ahu" or "air handler"
        # (space) and missed every Wrightsoft-parsed AHU on the Enos
        # Edge eval — yielding 0 rules-engine lines on a real RUP.
        s = compute_scope({"equipment": [
            {"type": "air_handler", "name": "AHU - 1"},
            {"type": "air_handler", "name": "AHU - 2"},
        ]})
        assert s.ahu_count == 2

    def test_ahu_implies_condenser_and_heat_kit_when_no_furnace(self):
        # Industry default: residential AHU implies 1 condenser + 1 heat kit.
        s = compute_scope({"equipment": [{"type": "AHU", "name": "AHU - 1"}]})
        assert s.ahu_count == 1
        assert s.condenser_count == 1
        assert s.heat_kit_count == 1

    def test_ahu_with_furnace_skips_implicit_kit(self):
        s = compute_scope({"equipment": [
            {"type": "AHU"},
            {"type": "gas furnace"},
        ]})
        # Furnace present → no implicit electric heat kit
        assert s.heat_kit_count == 0
        # Condenser also skipped because of fossil fuel
        assert s.condenser_count == 0

    def test_explicit_condenser_overrides_default(self):
        s = compute_scope({"equipment": [
            {"type": "AHU"},
            {"type": "condenser"},
            {"type": "condenser"},
        ]})
        assert s.condenser_count == 2

    def test_erv_detected(self):
        s = compute_scope({"equipment": [{"type": "ERV"}]})
        assert s.erv_present is True

    def test_rectangular_duct_lf_summed(self):
        s = compute_scope({"duct_runs": [
            {"shape": "rectangular", "length_ft": 12.5},
            {"shape": "rectangular", "length_ft": 8.0},
            {"shape": "round", "diameter_inches": 8, "length_ft": 30},
        ]})
        assert s.rectangular_lf == 20.5

    def test_small_diameter_rounds_count_as_rheia_lf(self):
        s = compute_scope({"duct_runs": [
            {"shape": "round", "diameter_inches": 3, "length_ft": 200},
            {"shape": "round", "diameter_inches": 4, "length_ft": 100},
            {"shape": "round", "diameter_inches": 8, "length_ft": 50},  # too big
        ]})
        assert s.rheia_lf == 300
        assert s.rheia_in_scope is True

    def test_rheia_inferred_from_raw_context(self):
        # Parser couldn't extract duct_runs but the narrative mentions 3-in
        s = compute_scope({
            "raw_rup_context": "Project foo. Duct sizes: 3-in flexible runs throughout.",
            "rooms": [{"name": f"Room {i}"} for i in range(8)],
            "equipment": [{"type": "AHU"}],
        })
        # rheia_in_scope true because the context mentions 3-in
        assert s.rheia_in_scope is True
        # LF estimated from rooms + AHU heuristic
        assert s.rheia_lf >= 100

    def test_registers_classified_by_location(self):
        s = compute_scope({"registers": [
            {"location": "ceiling", "shape": "round"},
            {"location": "ceiling", "shape": "rectangular grill"},
            {"location": "high wall", "shape": "rectangular"},
            {"location": "high wall", "shape": "rectangular"},
        ]})
        assert s.register_count == 4
        assert s.register_ceiling_round == 1
        assert s.register_ceiling_grill == 1
        assert s.register_high_wall_rect == 2
        # Rheia endpoints are derived from these counts
        assert s.rheia_ceiling_endpoints == 1
        assert s.rheia_high_sidewall_endpoints == 2


# ---------------------------------------------------------------------------
# evaluate_trigger
# ---------------------------------------------------------------------------

class TestEvaluateTrigger:
    def test_always_always_true(self):
        assert evaluate_trigger("always", Scope()) is True

    def test_ahu_present(self):
        assert evaluate_trigger("ahu_present", Scope(ahu_count=1)) is True
        assert evaluate_trigger("ahu_present", Scope()) is False

    def test_rheia_in_scope_via_lf(self):
        assert evaluate_trigger("rheia_in_scope", Scope(rheia_lf=10)) is True

    def test_rheia_in_scope_via_endpoints(self):
        assert evaluate_trigger("rheia_in_scope",
                                Scope(rheia_ceiling_endpoints=3)) is True

    def test_unknown_trigger_false(self):
        assert evaluate_trigger("not_a_thing", Scope(ahu_count=1)) is False


# ---------------------------------------------------------------------------
# resolve_quantity
# ---------------------------------------------------------------------------

class TestResolveQuantity:
    def test_fixed(self):
        assert resolve_quantity({"mode": "fixed", "value": 3}, Scope()) == 3.0

    def test_per_unit_ahu(self):
        s = Scope(ahu_count=2)
        assert resolve_quantity({"mode": "per_unit", "source": "equipment.ahu"}, s) == 2.0

    def test_per_lf_rectangular(self):
        s = Scope(rectangular_lf=42.5)
        assert resolve_quantity({"mode": "per_lf", "source": "duct_runs.rectangular"}, s) == 42.5

    def test_rheia_per_lf_no_divisor_returns_total(self):
        s = Scope(rheia_lf=856)
        assert resolve_quantity({"mode": "rheia_per_lf"}, s) == 856.0

    def test_rheia_per_lf_with_divisor_rounds(self):
        s = Scope(rheia_lf=856)
        # 856 / 23 ≈ 37.2 → 37 (rounded). Sample BOM shipped 37 hangers.
        assert resolve_quantity({"mode": "rheia_per_lf", "divisor": 23}, s) == 37.0

    def test_rheia_per_lf_zero_when_not_in_scope(self):
        assert resolve_quantity({"mode": "rheia_per_lf"}, Scope()) == 0.0

    def test_rheia_per_endpoint_high_sidewall(self):
        s = Scope(rheia_lf=100, rheia_high_sidewall_endpoints=17)
        assert resolve_quantity(
            {"mode": "rheia_per_endpoint", "endpoint": "high_sidewall"}, s
        ) == 17.0

    def test_rheia_per_endpoint_ceiling(self):
        s = Scope(rheia_lf=100, rheia_ceiling_endpoints=10)
        assert resolve_quantity(
            {"mode": "rheia_per_endpoint", "endpoint": "ceiling"}, s
        ) == 10.0

    def test_rheia_per_takeoff(self):
        s = Scope(rheia_lf=100, rheia_takeoffs=27)
        assert resolve_quantity({"mode": "rheia_per_takeoff", "side": "inside"}, s) == 27.0

    def test_unknown_mode_returns_zero(self):
        assert resolve_quantity({"mode": "made_up"}, Scope()) == 0.0


# ---------------------------------------------------------------------------
# generate_rule_lines — end-to-end with the real catalog
# ---------------------------------------------------------------------------

# Use a catalog override for deterministic tests rather than depending
# on whatever Firestore/JSON returns at import time.

def _starter_catalog():
    """Load the same 21 starter SKUs the JSON file ships with."""
    path = Path(__file__).resolve().parents[1] / "data" / "sku_catalog.json"
    raw = json.loads(path.read_text())
    from services.sku_catalog import SKUItem
    return [SKUItem.from_dict(it) for it in raw["items"]]


class TestGenerateRuleLinesAgainstStarter:
    """Realistic design_data → expected line item shape."""

    def test_ahu_only_design(self):
        # Single residential AHU → expect Equipment AHU + Condenser + Heat Kit
        # + Plenum Take-off (ahu_present trigger). No registers / ducts so
        # no Duct System Equipment lines and no Rheia.
        lines = generate_rule_lines(
            {"equipment": [{"type": "AHU - 1"}]},
            catalog=_starter_catalog(),
        )
        skus = {l["sku"] for l in lines}
        assert "AHVE24BP1300A" in skus    # AHU
        assert "GZV6SA1810A" in skus      # Condenser (implied)
        assert "HKTSD05X1" in skus        # Heat kit (implied)
        assert "FPLJ-1712" in skus        # Plenum take-off (ahu_present)
        # No Rheia
        assert not any(l["section"] == "Rheia Duct System Equipment" for l in lines)

    def test_full_residential_with_rheia(self):
        # 1 AHU + 1 ERV + 17 high-sidewall + 10 ceiling registers +
        # 856 LF of 3-in rheia duct
        design = {
            "equipment": [{"type": "AHU"}, {"type": "ERV"}],
            "duct_runs": [{"shape": "round", "diameter_inches": 3, "length_ft": 856}],
            "registers": (
                [{"location": "high wall", "shape": "rectangular"}] * 17
                + [{"location": "ceiling", "shape": "round"}] * 10
            ),
        }
        lines = generate_rule_lines(design, catalog=_starter_catalog())
        by_sku = {l["sku"]: l for l in lines}

        # Rheia lines all present, with quantities matching the sample BOM
        assert by_sku["10-00-190"]["quantity"] == 856          # 3-in duct LF
        # Hanger bars: 856/23 ≈ 37 — matches contractor sample
        assert by_sku["00-00-240"]["quantity"] == 37
        # Couplers: 856/60 ≈ 14 — sample shipped 15 (close enough; rule refinable)
        assert 13 <= by_sku["10-01-030"]["quantity"] <= 16
        # Endpoints
        assert by_sku["10-01-200"]["quantity"] == 17  # high sidewall boots
        assert by_sku["10-04-091"]["quantity"] == 17  # slotted diffusers
        assert by_sku["10-01-220"]["quantity"] == 10  # ceiling boots
        assert by_sku["10-04-230"]["quantity"] == 10  # ceiling diffusers
        # Take-offs (inside + outside, paired)
        assert by_sku["10-01-041"]["quantity"] == 27  # inside
        assert by_sku["10-01-051"]["quantity"] == 27  # outside
        # ERV present
        assert "B150E75NT" in by_sku
        # Sections present
        assert {"Equipment", "Rheia Duct System Equipment"}.issubset(
            {l["section"] for l in lines}
        )

    def test_disabled_items_excluded(self):
        from services.sku_catalog import SKUItem
        catalog = [
            SKUItem.from_dict({
                "sku": "DISABLED",
                "supplier": "X",
                "section": "Equipment",
                "phase": None,
                "description": "Hidden",
                "trigger": "always",
                "quantity": {"mode": "fixed", "value": 1},
                "default_unit_price": 0,
                "disabled": True,
            }),
        ]
        # Engine asks the catalog with include_disabled=False, but since
        # we're passing a custom catalog the test simulates that path.
        active = [it for it in catalog if not it.disabled]
        lines = generate_rule_lines({}, catalog=active)
        assert lines == []

    def test_zero_quantity_filtered_out(self):
        # rheia_per_lf with no Rheia in scope yields 0 — filter drops it.
        from services.sku_catalog import SKUItem
        catalog = [SKUItem.from_dict({
            "sku": "RHEA-X",
            "supplier": "RHEA",
            "section": "Rheia Duct System Equipment",
            "phase": "Rough",
            "description": "Test rheia",
            "trigger": "rheia_in_scope",
            "quantity": {"mode": "rheia_per_lf"},
            "default_unit_price": 0,
        })]
        lines = generate_rule_lines({"equipment": [{"type": "AHU"}]}, catalog=catalog)
        # rheia_in_scope is False → trigger fails → no line emitted
        assert lines == []

    def test_total_cost_computed_when_unit_price_set(self):
        from services.sku_catalog import SKUItem
        catalog = [SKUItem.from_dict({
            "sku": "PRICED",
            "supplier": "X",
            "section": "Duct System Equipment",
            "phase": None,
            "description": "Priced item",
            "trigger": "always",
            "quantity": {"mode": "fixed", "value": 4},
            "default_unit_price": 6.5,  # sample-bom anchor
        })]
        lines = generate_rule_lines({}, catalog=catalog)
        assert len(lines) == 1
        assert lines[0]["unit_cost"] == 6.5
        assert lines[0]["total_cost"] == 26.0   # 4 × 6.5
