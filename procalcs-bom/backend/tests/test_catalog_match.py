"""
Phase 3.7 (May 2026) — tests for services/catalog_match.py.

Verifies the per-equipment SKU lookup that sits between the rules
engine and the AI fallback. Covers:

  - Equipment-type → trigger mapping (air_handler→ahu_present,
    condenser→condenser_present, ERV/HRV→erv_present, etc.)
  - Capacity derivation from {tonnage, cfm, capacity_btu} fields
    (tonnage wins, CFM falls back, explicit btu honored)
  - Tolerance-band picker (catalog_exact > catalog_band > catalog_default)
  - Contractor scoping (contractor-scoped SKUs win over globals)
  - Coalescing same-SKU per-equipment matches into single rows
  - Disabled SKUs ignored
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services import sku_catalog
from services import catalog_match


# ─── Test SKU factory ──────────────────────────────────────────────

def _sku(
    sku_id: str,
    *,
    trigger: str = "ahu_present",
    capacity_btu: int | None = None,
    capacity_min: int | None = None,
    capacity_max: int | None = None,
    contractor_id: str | None = None,
    description: str | None = None,
    disabled: bool = False,
    section: str = "Equipment",
    supplier: str = "GOOD",
    manufacturer: str | None = "Goodman",
    default_unit_price: float = 100.0,
) -> sku_catalog.SKUItem:
    return sku_catalog.SKUItem(
        sku=sku_id,
        supplier=supplier,
        section=section,
        phase=None,
        description=description or f"Test SKU {sku_id}",
        trigger=trigger,
        quantity={"mode": "fixed", "value": 1},
        default_unit_price=default_unit_price,
        notes="",
        disabled=disabled,
        wrightsoft_codes=(),
        capacity_btu=capacity_btu,
        capacity_min_btu=capacity_min,
        capacity_max_btu=capacity_max,
        manufacturer=manufacturer,
        contractor_id=contractor_id,
    )


# ─── _trigger_for_equipment ─────────────────────────────────────────

class TestTriggerForEquipment:
    def test_air_handler_maps_to_ahu_present(self):
        assert catalog_match._trigger_for_equipment("air_handler") == "ahu_present"

    def test_condenser_maps_to_condenser_present(self):
        assert catalog_match._trigger_for_equipment("condenser") == "condenser_present"

    def test_heat_pump_rides_on_condenser_trigger(self):
        assert catalog_match._trigger_for_equipment("heat_pump") == "condenser_present"

    def test_furnace_rides_on_ahu_trigger(self):
        assert catalog_match._trigger_for_equipment("furnace") == "ahu_present"

    def test_erv_and_hrv_both_map_to_erv_present(self):
        assert catalog_match._trigger_for_equipment("erv") == "erv_present"
        assert catalog_match._trigger_for_equipment("hrv") == "erv_present"

    def test_unknown_returns_none(self):
        assert catalog_match._trigger_for_equipment("flux_capacitor") is None
        assert catalog_match._trigger_for_equipment(None) is None
        assert catalog_match._trigger_for_equipment("") is None

    def test_normalizes_case_and_spaces(self):
        assert catalog_match._trigger_for_equipment("  AIR HANDLER ") == "ahu_present"


# ─── _equipment_capacity_btu ────────────────────────────────────────

class TestEquipmentCapacityBtu:
    def test_tonnage_wins_when_present(self):
        # 2 tons → 24,000 BTU
        eq = {"type": "air_handler", "tonnage": 2.0, "cfm": 800}
        assert catalog_match._equipment_capacity_btu(eq) == 24_000

    def test_falls_back_to_cfm_when_no_tonnage(self):
        # 800 CFM → 800 * 30 = 24,000 BTU
        eq = {"type": "air_handler", "tonnage": None, "cfm": 800}
        assert catalog_match._equipment_capacity_btu(eq) == 24_000

    def test_explicit_btu_honored_when_no_other(self):
        eq = {"type": "air_handler", "capacity_btu": 36_000}
        assert catalog_match._equipment_capacity_btu(eq) == 36_000

    def test_returns_none_when_no_signal(self):
        assert catalog_match._equipment_capacity_btu({}) is None
        assert catalog_match._equipment_capacity_btu({"type": "air_handler"}) is None

    def test_handles_string_numerics(self):
        # JSON sometimes serializes numbers as strings
        eq = {"type": "air_handler", "tonnage": "3.0"}
        assert catalog_match._equipment_capacity_btu(eq) == 36_000

    def test_returns_none_on_garbage(self):
        eq = {"type": "air_handler", "tonnage": "not-a-number"}
        # tonnage parse fails, no cfm, no btu → None
        assert catalog_match._equipment_capacity_btu(eq) is None


# ─── _pick_sku_by_capacity ──────────────────────────────────────────

class TestPickSkuByCapacity:
    def test_exact_match_wins_over_band(self):
        candidates = [
            _sku("BAND-24", capacity_min=22_000, capacity_max=26_000),
            _sku("EXACT-24", capacity_btu=24_000),
        ]
        sku, conf = catalog_match._pick_sku_by_capacity(candidates, 24_000)
        assert sku.sku == "EXACT-24"
        assert conf == "catalog_exact"

    def test_band_match_when_no_exact(self):
        candidates = [_sku("BAND-24", capacity_min=22_000, capacity_max=26_000)]
        sku, conf = catalog_match._pick_sku_by_capacity(candidates, 23_500)
        assert sku.sku == "BAND-24"
        assert conf == "catalog_band"

    def test_default_when_no_capacity_info(self):
        candidates = [_sku("NO-CAP")]
        sku, conf = catalog_match._pick_sku_by_capacity(candidates, None)
        assert sku.sku == "NO-CAP"
        assert conf == "catalog_default"

    def test_no_match_when_empty(self):
        sku, conf = catalog_match._pick_sku_by_capacity([], 24_000)
        assert sku is None
        assert conf == "no_match"

    def test_default_fallback_when_target_outside_all_bands(self):
        # 50K BTU — no SKU matches that band, but we still emit
        # something rather than dropping the equipment item entirely.
        candidates = [_sku("BAND-24", capacity_min=22_000, capacity_max=26_000)]
        sku, conf = catalog_match._pick_sku_by_capacity(candidates, 50_000)
        assert sku.sku == "BAND-24"
        assert conf == "catalog_default"


# ─── _candidate_skus_for_trigger ────────────────────────────────────

class TestCandidateSkus:
    def test_filters_by_trigger(self):
        catalog = [
            _sku("AHU-1", trigger="ahu_present"),
            _sku("COND-1", trigger="condenser_present"),
        ]
        cands = catalog_match._candidate_skus_for_trigger("ahu_present", None, catalog)
        assert [c.sku for c in cands] == ["AHU-1"]

    def test_global_skus_match_when_contractor_id_none(self):
        catalog = [
            _sku("GLOBAL-AHU", contractor_id=None),
            _sku("BEAZER-AHU", contractor_id="beazer-homes-az"),
        ]
        cands = catalog_match._candidate_skus_for_trigger("ahu_present", None, catalog)
        assert [c.sku for c in cands] == ["GLOBAL-AHU"]

    def test_contractor_scoped_first_then_global(self):
        catalog = [
            _sku("GLOBAL-AHU", contractor_id=None),
            _sku("BEAZER-AHU", contractor_id="beazer-homes-az"),
        ]
        cands = catalog_match._candidate_skus_for_trigger(
            "ahu_present", "beazer-homes-az", catalog
        )
        # Both match; contractor-scoped first
        assert cands[0].sku == "BEAZER-AHU"
        assert cands[1].sku == "GLOBAL-AHU"

    def test_disabled_skus_skipped(self):
        catalog = [
            _sku("AHU-1", disabled=True),
            _sku("AHU-2", disabled=False),
        ]
        cands = catalog_match._candidate_skus_for_trigger("ahu_present", None, catalog)
        assert [c.sku for c in cands] == ["AHU-2"]


# ─── match_equipment_to_catalog (integration) ───────────────────────

class TestMatchEquipmentToCatalog:
    def test_emits_one_line_per_equipment_with_correct_sku(self):
        catalog = [
            _sku("GOOD-AHU-24K", capacity_btu=24_000),
            _sku("GOOD-AHU-36K", capacity_btu=36_000),
        ]
        equipment = [
            {"name": "AHU 1", "type": "air_handler", "tonnage": 2.0},  # 24K
            {"name": "AHU 2", "type": "air_handler", "tonnage": 3.0},  # 36K
            {"name": "AHU 3", "type": "air_handler", "tonnage": 2.0},  # 24K again
        ]
        out = catalog_match.match_equipment_to_catalog(
            equipment, contractor_id=None, catalog=catalog,
        )
        assert len(out) == 3
        skus = [line["sku"] for line in out]
        assert skus == ["GOOD-AHU-24K", "GOOD-AHU-36K", "GOOD-AHU-24K"]
        assert all(line["confidence"] == "catalog_exact" for line in out)

    def test_skips_unknown_equipment_types(self):
        catalog = [_sku("AHU-1")]
        equipment = [{"type": "flux_capacitor"}]
        assert catalog_match.match_equipment_to_catalog(
            equipment, contractor_id=None, catalog=catalog
        ) == []

    def test_skips_when_no_candidates_for_trigger(self):
        catalog = [_sku("COND-1", trigger="condenser_present")]
        equipment = [{"type": "air_handler", "tonnage": 2.0}]
        assert catalog_match.match_equipment_to_catalog(
            equipment, contractor_id=None, catalog=catalog
        ) == []

    def test_empty_or_missing_equipment_returns_empty(self):
        assert catalog_match.match_equipment_to_catalog([], None) == []
        assert catalog_match.match_equipment_to_catalog(None, None) == []  # type: ignore[arg-type]

    def test_contractor_scoped_sku_wins_over_global(self):
        catalog = [
            _sku("GLOBAL-AHU", capacity_btu=24_000, contractor_id=None),
            _sku("BEAZER-AHU", capacity_btu=24_000, contractor_id="beazer-homes-az"),
        ]
        equipment = [{"type": "air_handler", "tonnage": 2.0}]
        out = catalog_match.match_equipment_to_catalog(
            equipment, contractor_id="beazer-homes-az", catalog=catalog,
        )
        assert out[0]["sku"] == "BEAZER-AHU"


# ─── coalesce_matched_lines ─────────────────────────────────────────

class TestCoalesceMatchedLines:
    def test_folds_same_sku_into_one_line_with_qty_n(self):
        catalog = [_sku("GOOD-AHU-24K", capacity_btu=24_000)]
        equipment = [
            {"name": f"AHU {i}", "type": "air_handler", "tonnage": 2.0}
            for i in range(5)
        ]
        per_instance = catalog_match.match_equipment_to_catalog(
            equipment, contractor_id=None, catalog=catalog,
        )
        coalesced = catalog_match.coalesce_matched_lines(per_instance)
        assert len(coalesced) == 1
        assert coalesced[0]["sku"] == "GOOD-AHU-24K"
        assert coalesced[0]["quantity"] == 5.0

    def test_keeps_distinct_skus_separate(self):
        catalog = [
            _sku("GOOD-AHU-24K", capacity_btu=24_000),
            _sku("GOOD-AHU-36K", capacity_btu=36_000),
        ]
        equipment = [
            {"type": "air_handler", "tonnage": 2.0},
            {"type": "air_handler", "tonnage": 3.0},
            {"type": "air_handler", "tonnage": 2.0},
        ]
        per_instance = catalog_match.match_equipment_to_catalog(
            equipment, contractor_id=None, catalog=catalog,
        )
        coalesced = catalog_match.coalesce_matched_lines(per_instance)
        assert {ln["sku"]: ln["quantity"] for ln in coalesced} == {
            "GOOD-AHU-24K": 2.0,
            "GOOD-AHU-36K": 1.0,
        }

    def test_strips_internal_match_key_and_target_btu(self):
        catalog = [_sku("AHU-1", capacity_btu=24_000)]
        equipment = [{"type": "air_handler", "tonnage": 2.0}]
        per = catalog_match.match_equipment_to_catalog(
            equipment, contractor_id=None, catalog=catalog,
        )
        coalesced = catalog_match.coalesce_matched_lines(per)
        assert "_match_key" not in coalesced[0]
        assert "_target_btu" not in coalesced[0]
        # User-facing fields preserved
        assert coalesced[0]["confidence"] == "catalog_exact"
        assert coalesced[0]["source"] == "catalog_match"


# ─── Integration with bom_service.generate (phantom suppression) ────
#
# When catalog_match emits a per-equipment line for trigger T (e.g.
# ahu_present), the rules engine must not also emit OTHER SKUs that
# would fire on T — otherwise we get phantom rows like a 60K AHU
# materializing in a project that has no 60K equipment, just because
# trigger=ahu_present is true and the rules engine fires every
# matching SKU regardless of capacity. Real-money problem.
#
# This test pins the dedupe behavior introduced in Phase 3.7
# (services/bom_service.py).

class TestPhantomSuppressionInBomGenerate:
    @pytest.fixture
    def goodman_catalog(self):
        return [
            _sku("GOOD-AHU-24K", trigger="ahu_present", capacity_btu=24000,
                 capacity_min=22000, capacity_max=26000,
                 description="Goodman AHU 24K"),
            _sku("GOOD-AHU-36K", trigger="ahu_present", capacity_btu=36000,
                 capacity_min=34000, capacity_max=38000,
                 description="Goodman AHU 36K"),
            # Phantom candidate — fires on ahu_present trigger but no 60K
            # equipment in the test design. Must be suppressed.
            _sku("GOOD-AHU-60K", trigger="ahu_present", capacity_btu=60000,
                 capacity_min=56000, capacity_max=64000,
                 description="Goodman AHU 60K phantom"),
            _sku("GOOD-HEATKIT-5KW", trigger="heat_kit_present",
                 description="Goodman Heat Kit 5kW"),
        ]

    @pytest.fixture
    def two_ahu_design(self):
        return {
            "project":  {"name": "Phantom-test"},
            "building": {"type": "single_level", "duct_location": "attic"},
            "equipment": [
                {"name": "AHU-1", "type": "air_handler", "tonnage": 2.0},  # 24K
                {"name": "AHU-2", "type": "air_handler", "tonnage": 3.0},  # 36K
            ],
            "rooms": [], "duct_runs": [], "fittings": [], "registers": [],
            "raw_rup_context": "Test.",
        }

    def test_60k_phantom_suppressed_when_no_60k_equipment(
        self, goodman_catalog, two_ahu_design,
    ):
        """The 60K AHU SKU must NOT appear in BOM output even though
        trigger=ahu_present is true. catalog_match captured the AHU
        trigger via per-equipment matches; rules engine should yield."""
        from unittest.mock import patch
        from services import bom_service

        mock_profile = {
            "client_id": "x", "client_name": "X", "is_active": True,
            "supplier": {"supplier_name": "S"},
            "markup": {"equipment_pct": 15, "materials_pct": 25,
                       "consumables_pct": 30, "labor_pct": 0},
            "markup_tiers": [], "brands": {}, "part_name_overrides": [],
            "default_output_mode": "full", "include_labor": False, "notes": "",
        }
        sku_index = {s.sku: s for s in goodman_catalog}

        with patch("services.bom_service.get_profile_by_id", return_value=mock_profile), \
             patch("services.bom_service._call_ai_for_quantities",
                   return_value={"drawn_items": [], "consumables": []}), \
             patch("services.sku_catalog.all_items", return_value=goodman_catalog), \
             patch("services.sku_catalog.get", side_effect=lambda s: sku_index.get(s)), \
             patch("services.materials_rules.sku_catalog.all_items",
                   return_value=goodman_catalog):
            bom = bom_service.generate("x", "phantom-test-job", two_ahu_design)

        emitted_skus = {li.get("sku") for li in bom["line_items"]}
        assert "GOOD-AHU-60K" not in emitted_skus, (
            f"phantom 60K AHU leaked into BOM: {emitted_skus}"
        )
        # The two real AHUs are present
        assert "GOOD-AHU-24K" in emitted_skus
        assert "GOOD-AHU-36K" in emitted_skus

    def test_heat_kit_survives_different_trigger(
        self, goodman_catalog, two_ahu_design,
    ):
        """The heat kit SKU has trigger=heat_kit_present, NOT
        ahu_present, so catalog_match's claim on ahu_present must
        not suppress it."""
        from unittest.mock import patch
        from services import bom_service

        mock_profile = {
            "client_id": "x", "client_name": "X", "is_active": True,
            "supplier": {"supplier_name": "S"},
            "markup": {"equipment_pct": 15, "materials_pct": 25,
                       "consumables_pct": 30, "labor_pct": 0},
            "markup_tiers": [], "brands": {}, "part_name_overrides": [],
            "default_output_mode": "full", "include_labor": False, "notes": "",
        }
        sku_index = {s.sku: s for s in goodman_catalog}

        with patch("services.bom_service.get_profile_by_id", return_value=mock_profile), \
             patch("services.bom_service._call_ai_for_quantities",
                   return_value={"drawn_items": [], "consumables": []}), \
             patch("services.sku_catalog.all_items", return_value=goodman_catalog), \
             patch("services.sku_catalog.get", side_effect=lambda s: sku_index.get(s)), \
             patch("services.materials_rules.sku_catalog.all_items",
                   return_value=goodman_catalog):
            bom = bom_service.generate("x", "heat-kit-test-job", two_ahu_design)

        skus = [li.get("sku") for li in bom["line_items"]]
        assert "GOOD-HEATKIT-5KW" in skus, (
            f"heat kit (different trigger) wrongly suppressed: {skus}"
        )


# ─── Phase 5 — Section assignment in BOM output ──────────────────────
#
# Every line item must carry a `section` field for SPA + PDF grouping.
# Catalog and rules-engine lines pull section from the SKU Catalog;
# AI lines fall through the _AI_CATEGORY_TO_SECTION map. Default
# "Duct System Equipment" so unmapped categories stay visible.

class TestSectionAssignment:
    """Pin the Phase 5 section-assignment behavior so AI lines always
    land in the right section bucket and nothing leaks unsectioned."""

    def test_section_for_line_honors_explicit(self):
        from services.bom_service import _section_for_line
        assert _section_for_line({"section": "Equipment"}) == "Equipment"
        assert _section_for_line({"section": "Rheia Duct System Equipment"}) == "Rheia Duct System Equipment"

    def test_section_for_line_maps_ai_categories(self):
        from services.bom_service import _section_for_line
        assert _section_for_line({"category": "equipment"}) == "Equipment"
        assert _section_for_line({"category": "duct"}) == "Duct System Equipment"
        assert _section_for_line({"category": "fitting"}) == "Duct System Equipment"
        assert _section_for_line({"category": "register"}) == "Duct System Equipment"
        assert _section_for_line({"category": "consumable"}) == "Duct System Equipment"

    def test_section_for_line_defaults_unknown_to_duct_system(self):
        from services.bom_service import _section_for_line
        # Default keeps the line visible rather than letting it fall
        # off the bottom of an unbucketed PDF section.
        assert _section_for_line({"category": "mystery"}) == "Duct System Equipment"
        assert _section_for_line({}) == "Duct System Equipment"

    def test_section_for_line_explicit_blank_falls_back_to_category(self):
        from services.bom_service import _section_for_line
        # Defensive: an empty string in section should NOT short-circuit
        # the category fallback. Whitespace-only too.
        assert _section_for_line({"section": "", "category": "equipment"}) == "Equipment"
        assert _section_for_line({"section": "  ", "category": "equipment"}) == "Equipment"


# ─── Phase 7 — AI prompt grounding ───────────────────────────────────
#
# When catalog_match + rules_engine emit lines, _build_ai_prompt
# receives them and renders an "ALREADY COVERED" block telling Claude
# which SKUs are already in the BOM. This reduces hallucination + saves
# output tokens. Backwards compatible — calls without claimed_lines
# (legacy tests, fresh deployments) get the original prompt.

class TestPromptGrounding:
    """Pin the Phase 7 prompt-grounding behavior so the catalog
    context flows through to Claude without breaking the prompt
    template's existing format placeholders."""

    @pytest.fixture
    def profile(self):
        from models.client_profile import ClientProfile
        return ClientProfile.from_dict({
            "client_id": "x", "client_name": "X", "is_active": True,
            "supplier": {"supplier_name": "S"},
            "markup": {"equipment_pct": 15, "materials_pct": 25,
                       "consumables_pct": 30, "labor_pct": 0},
            "markup_tiers": [], "brands": {}, "part_name_overrides": [],
            "default_output_mode": "full", "include_labor": False, "notes": "",
        })

    @pytest.fixture
    def design_data(self):
        return {
            "building":         {"type": "single_level", "duct_location": "attic"},
            "duct_runs":        [], "fittings":  [], "equipment": [],
            "registers":        [], "rooms":     [], "raw_rup_context": "",
        }

    def test_no_already_covered_block_when_claimed_omitted(self, profile, design_data):
        from services.bom_service import _build_ai_prompt
        prompt = _build_ai_prompt(design_data, profile)
        assert "ALREADY COVERED" not in prompt

    def test_no_already_covered_block_when_claimed_empty(self, profile, design_data):
        from services.bom_service import _build_ai_prompt
        prompt = _build_ai_prompt(design_data, profile, claimed_lines=[])
        assert "ALREADY COVERED" not in prompt

    def test_already_covered_block_lists_each_claimed_sku(self, profile, design_data):
        from services.bom_service import _build_ai_prompt
        claimed = [
            {"source": "catalog_match", "sku": "GOOD-AHU-24K",
             "description": "Goodman AHU 24K"},
            {"source": "rules_engine", "sku": "RHEA-3IN-DUCT",
             "description": "3-in Rheia duct"},
        ]
        prompt = _build_ai_prompt(design_data, profile, claimed_lines=claimed)
        assert "ALREADY COVERED" in prompt
        assert "GOOD-AHU-24K" in prompt
        assert "RHEA-3IN-DUCT" in prompt
        assert "Goodman AHU 24K" in prompt
        assert "3-in Rheia duct" in prompt

    def test_block_includes_source_label_per_line(self, profile, design_data):
        from services.bom_service import _build_ai_prompt
        claimed = [
            {"source": "catalog_match", "sku": "X", "description": "X-desc"},
            {"source": "rules_engine",  "sku": "Y", "description": "Y-desc"},
        ]
        prompt = _build_ai_prompt(design_data, profile, claimed_lines=claimed)
        # Designers reading prompt logs benefit from knowing which layer
        # emitted each line (catalog_match vs rules_engine).
        assert "[catalog_match]" in prompt
        assert "[rules_engine]" in prompt

    def test_lines_with_no_sku_or_description_handled_gracefully(self, profile, design_data):
        from services.bom_service import _build_ai_prompt
        claimed = [
            {"source": "rules_engine"},   # no sku, no description
            {"source": "catalog_match", "sku": "OK", "description": "Okay"},
        ]
        # Should not crash and should still include the well-formed line.
        prompt = _build_ai_prompt(design_data, profile, claimed_lines=claimed)
        assert "ALREADY COVERED" in prompt
        assert "(no-sku)" in prompt
        assert "OK" in prompt

    def test_call_ai_for_quantities_passes_through_claimed_lines(self, profile, design_data):
        """Smoke-test that the kwarg threads through to the prompt."""
        from unittest.mock import patch, MagicMock
        from services import bom_service

        # Capture the prompt actually sent to Anthropic
        captured = {}
        def fake_create(**kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"]
            stub_response = MagicMock()
            stub_response.content = [MagicMock(text='{"drawn_items": [], "consumables": []}')]
            return stub_response

        # Need a Flask app context for current_app.config
        from flask import Flask
        app = Flask(__name__)
        app.config["ANTHROPIC_API_KEY"] = "test-key"
        app.config["ANTHROPIC_MODEL"] = "claude-test"
        app.config["ANTHROPIC_MAX_TOKENS"] = 1024

        claimed = [{"source": "catalog_match", "sku": "GOOD-AHU-24K",
                    "description": "Goodman AHU 24K"}]

        with app.app_context(), \
             patch("services.bom_service.anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = fake_create
            mock_anthropic.return_value = mock_client

            bom_service._call_ai_for_quantities(
                design_data, profile, claimed_lines=claimed,
            )

        assert "ALREADY COVERED" in captured["prompt"]
        assert "GOOD-AHU-24K" in captured["prompt"]


# ─── Phase 2 of Path B (May 2026) — catalog-aware AI prompt ──────────
#
# AI prompt now includes an "AVAILABLE CATALOG SKUs" block listing
# entries Claude can reference by exact sku string. _apply_pricing
# preserves the AI-emitted sku and looks up catalog metadata
# (cost / supplier / section / manufacturer). Closes the SKU
# hallucination gap on Easy + Avg RUPs whose parser leaves
# equipment[] empty (no catalog_match candidates).

class TestAvailableCatalogBlock:
    @pytest.fixture
    def profile(self):
        from models.client_profile import ClientProfile
        return ClientProfile.from_dict({
            "client_id": "test-contractor", "client_name": "X",
            "is_active": True, "supplier": {"supplier_name": "S"},
            "markup": {"equipment_pct": 15, "materials_pct": 25,
                       "consumables_pct": 30, "labor_pct": 0},
            "markup_tiers": [], "brands": {}, "part_name_overrides": [],
            "default_output_mode": "full", "include_labor": False, "notes": "",
        })

    def test_lists_catalog_skus_in_prompt(self, profile):
        from unittest.mock import patch
        from services import bom_service, sku_catalog
        cat = [
            _sku("GOOD-AHU-24K", capacity_btu=24000, description="Goodman AHU 24K"),
            _sku("GOOD-COND-24K", trigger="condenser_present",
                 capacity_btu=24000, description="Goodman Condenser 24K"),
        ]
        with patch.object(sku_catalog, "all_items", return_value=cat):
            block = bom_service._build_available_catalog_block(profile, claimed_lines=[])
        assert "AVAILABLE CATALOG SKUs" in block
        assert "GOOD-AHU-24K" in block
        assert "GOOD-COND-24K" in block
        assert "[24000 BTU]" in block
        assert "(Goodman)" in block

    def test_excludes_claimed_skus(self, profile):
        from unittest.mock import patch
        from services import bom_service, sku_catalog
        cat = [
            _sku("GOOD-AHU-24K", description="AHU"),
            _sku("GOOD-COND-24K", description="Condenser"),
        ]
        claimed = [{"source": "catalog_match", "sku": "GOOD-AHU-24K", "description": "AHU"}]
        with patch.object(sku_catalog, "all_items", return_value=cat):
            block = bom_service._build_available_catalog_block(profile, claimed_lines=claimed)
        assert "GOOD-AHU-24K" not in block
        assert "GOOD-COND-24K" in block

    def test_filters_by_contractor_scope(self, profile):
        """Beazer-scoped SKUs included for Beazer profile, hidden for others.
        Global SKUs (contractor_id None) always included."""
        from unittest.mock import patch
        from services import bom_service, sku_catalog
        cat = [
            _sku("GLOBAL-AHU", contractor_id=None, description="Global AHU"),
            _sku("BEAZER-AHU", contractor_id="beazer-homes-az", description="Beazer AHU"),
            _sku("OTHER-AHU", contractor_id="other-contractor", description="Other AHU"),
        ]
        # Profile is "test-contractor" — should see GLOBAL only
        with patch.object(sku_catalog, "all_items", return_value=cat):
            block = bom_service._build_available_catalog_block(profile, claimed_lines=[])
        assert "GLOBAL-AHU" in block
        assert "BEAZER-AHU" not in block
        assert "OTHER-AHU" not in block

    def test_returns_empty_when_no_catalog(self, profile):
        from unittest.mock import patch
        from services import bom_service, sku_catalog
        with patch.object(sku_catalog, "all_items", return_value=[]):
            assert bom_service._build_available_catalog_block(profile, claimed_lines=[]) == ""

    def test_returns_empty_when_all_skus_claimed(self, profile):
        from unittest.mock import patch
        from services import bom_service, sku_catalog
        cat = [_sku("X", description="X")]
        claimed = [{"source": "rules_engine", "sku": "X"}]
        with patch.object(sku_catalog, "all_items", return_value=cat):
            assert bom_service._build_available_catalog_block(profile, claimed_lines=claimed) == ""

    def test_falls_back_silently_when_catalog_unavailable(self, profile):
        """Firestore creds missing in tests — block returns empty rather
        than crashing _build_ai_prompt."""
        from unittest.mock import patch
        from services import bom_service, sku_catalog
        with patch.object(sku_catalog, "all_items", side_effect=RuntimeError("no creds")):
            assert bom_service._build_available_catalog_block(profile, claimed_lines=[]) == ""


class TestApplyPricingPreservesSku:
    """When AI emits a `sku` field, _apply_pricing preserves it and
    looks up catalog metadata (cost, supplier, section, manufacturer)."""

    @pytest.fixture
    def profile(self):
        from models.client_profile import ClientProfile
        return ClientProfile.from_dict({
            "client_id": "x", "client_name": "X", "is_active": True,
            "supplier": {"supplier_name": "S"},
            "markup": {"equipment_pct": 15, "materials_pct": 25,
                       "consumables_pct": 30, "labor_pct": 0},
            "markup_tiers": [], "brands": {}, "part_name_overrides": [],
            "default_output_mode": "full", "include_labor": False, "notes": "",
        })

    def test_ai_sku_resolves_to_catalog_metadata(self, profile):
        from unittest.mock import patch
        from services import bom_service, sku_catalog
        catalog_sku = _sku(
            "GOOD-AHU-24K", description="Goodman AHU 24K",
            default_unit_price=1850.0, supplier="GOOD",
            section="Equipment", manufacturer="Goodman",
        )
        ai_response = {
            "drawn_items": [{
                "category": "equipment",
                "description": "Goodman 2-ton AHU",
                "quantity": 1, "unit": "EA",
                "sku": "GOOD-AHU-24K",
            }],
            "consumables": [],
        }
        with patch.object(sku_catalog, "get", side_effect=lambda s: catalog_sku if s == "GOOD-AHU-24K" else None):
            priced = bom_service._apply_pricing(ai_response, profile, "full")
        assert len(priced) == 1
        line = priced[0]
        assert line["sku"] == "GOOD-AHU-24K"
        assert line["source"] == "ai_with_catalog_sku"
        assert line["unit_cost"] == 1850.0  # from catalog
        assert line["supplier"] == "GOOD"
        assert line["section"] == "Equipment"
        assert line["manufacturer"] == "Goodman"

    def test_unknown_ai_sku_keeps_sku_marks_inferred(self, profile):
        """AI may reference a sku we don't have (typo, future SKU,
        hallucination). Preserve the sku string for visibility, mark
        source=ai_inferred, fall back to legacy unit-cost lookup."""
        from unittest.mock import patch
        from services import bom_service, sku_catalog
        ai_response = {
            "drawn_items": [{
                "category": "equipment",
                "description": "Mystery part",
                "quantity": 1, "unit": "EA",
                "sku": "MADE-UP-SKU-999",
            }],
            "consumables": [],
        }
        with patch.object(sku_catalog, "get", return_value=None):
            priced = bom_service._apply_pricing(ai_response, profile, "full")
        line = priced[0]
        assert line["sku"] == "MADE-UP-SKU-999"
        assert line["source"] == "ai_inferred"
        # No catalog match — falls back to legacy description lookup (probably 0)
        assert "supplier" not in line
        assert "section" not in line

    def test_no_sku_field_unchanged_behavior(self, profile):
        """Pre-Phase-2 behavior: AI lines without sku field don't get
        source/sku/supplier/section keys added. Backwards compat."""
        from services import bom_service
        ai_response = {
            "drawn_items": [{
                "category": "consumable",
                "description": "Mastic",
                "quantity": 3, "unit": "GAL",
            }],
            "consumables": [],
        }
        priced = bom_service._apply_pricing(ai_response, profile, "full")
        line = priced[0]
        assert "sku" not in line
        assert "source" not in line
        assert "supplier" not in line
