"""
test_bom.py — pytest suite for ProCalcs BOM
Tests critical paths: validators, profile model, pricing logic.
Follows ProCalcs Design Standards v2.0
Run: pytest backend/tests/test_bom.py -v
"""

import pytest
import sys
import os

# Add backend to path so imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.validators import (
    validate_profile_payload,
    validate_markup_tiers,
    validate_supplier_costs,
    validate_bom_request,
)
from models.client_profile import (
    ClientProfile,
    SupplierInfo,
    MarkupTiers,
    BrandPreferences,
    PartNameOverride,
)


# ===============================
# Fixtures
# ===============================

@pytest.fixture
def valid_profile_payload():
    """Minimal valid profile payload."""
    return {
        "client_id":   "beazer-001",
        "client_name": "Beazer Homes",
        "created_by":  "richard@procalcs.net",
        "supplier": {
            "supplier_name":           "Ferguson",
            "mastic_cost_per_gallon":  18.50,
            "tape_cost_per_roll":      12.00,
            "strapping_cost_per_roll": 22.00,
            "screws_cost_per_box":     8.50,
            "brush_cost_each":         2.25,
            "flex_duct_cost_per_foot": 1.10,
            "rect_duct_cost_per_sqft": 0.85,
        },
        "markup": {
            "equipment_pct":   15.0,
            "materials_pct":   20.0,
            "consumables_pct": 25.0,
            "labor_pct":       0.0,
        },
        "brands": {
            "ac_brand":      "Carrier",
            "mastic_brand":  "Rectorseal",
            "tape_brand":    "Nashua",
        }
    }


@pytest.fixture
def valid_bom_request():
    """Minimal valid BOM generation request."""
    return {
        "client_id": "beazer-001",
        "job_id":    "job-2026-001",
        "design_data": {
            "duct_runs": [
                {"size": "12x8", "length_ft": 14, "type": "rectangular"},
                {"size": "8in", "length_ft": 22, "type": "flex"},
            ],
            "fittings": [
                {"type": "elbow", "size": "12x8", "quantity": 2},
                {"type": "collar", "size": "8in", "quantity": 4},
            ],
            "equipment": [
                {"type": "split_ac", "brand": "Carrier", "model": "24ACC636A003",
                 "tonnage": 3.0},
                {"type": "gas_furnace", "brand": "Carrier", "model": "58TP1B0A12114",
                 "afue": 80},
            ],
            "registers": [
                {"type": "supply", "size": "4x10", "quantity": 6},
                {"type": "return", "size": "16x25", "quantity": 1},
            ],
            "building": {
                "type": "single_level",
                "duct_location": "attic",
            }
        }
    }


@pytest.fixture
def sample_profile():
    """A fully built ClientProfile for pricing tests."""
    return ClientProfile(
        client_id="beazer-001",
        client_name="Beazer Homes",
        supplier=SupplierInfo(
            supplier_name="Ferguson",
            mastic_cost_per_gallon=18.50,
            tape_cost_per_roll=12.00,
            strapping_cost_per_roll=22.00,
            screws_cost_per_box=8.50,
            brush_cost_each=2.25,
            flex_duct_cost_per_foot=1.10,
            rect_duct_cost_per_sqft=0.85,
        ),
        markup=MarkupTiers(
            equipment_pct=15.0,
            materials_pct=20.0,
            consumables_pct=25.0,
        ),
        brands=BrandPreferences(
            ac_brand="Carrier",
            mastic_brand="Rectorseal",
            tape_brand="Nashua",
        ),
        part_name_overrides=[
            PartNameOverride(
                standard_name="4-inch collar",
                client_name="4\" snap collar",
                client_sku="FRG-COL-4IN"
            )
        ]
    )


# ===============================
# Validator Tests — Profile
# ===============================

class TestValidateProfilePayload:

    def test_valid_payload_returns_no_errors(self, valid_profile_payload):
        errors = validate_profile_payload(valid_profile_payload)
        assert errors == []

    def test_missing_client_id_returns_error(self, valid_profile_payload):
        valid_profile_payload['client_id'] = ''
        errors = validate_profile_payload(valid_profile_payload)
        assert any('client_id' in e for e in errors)

    def test_missing_client_name_returns_error(self, valid_profile_payload):
        valid_profile_payload['client_name'] = ''
        errors = validate_profile_payload(valid_profile_payload)
        assert any('client_name' in e for e in errors)

    def test_none_body_returns_error(self):
        errors = validate_profile_payload(None)
        assert len(errors) > 0

    def test_client_id_too_long_returns_error(self, valid_profile_payload):
        valid_profile_payload['client_id'] = 'x' * 101
        errors = validate_profile_payload(valid_profile_payload)
        assert any('client_id' in e for e in errors)


class TestValidateMarkupTiers:

    def test_valid_markups_return_no_errors(self):
        errors = validate_markup_tiers({
            "equipment_pct": 15.0,
            "materials_pct": 20.0,
            "consumables_pct": 25.0,
            "labor_pct": 0.0,
        })
        assert errors == []

    def test_negative_markup_returns_error(self):
        errors = validate_markup_tiers({"equipment_pct": -5.0})
        assert any('equipment_pct' in e for e in errors)

    def test_non_numeric_markup_returns_error(self):
        errors = validate_markup_tiers({"materials_pct": "twenty"})
        assert any('materials_pct' in e for e in errors)

    def test_empty_markup_returns_no_errors(self):
        # Markup is optional on create
        errors = validate_markup_tiers({})
        assert errors == []

    def test_none_markup_returns_no_errors(self):
        errors = validate_markup_tiers(None)
        assert errors == []


# ===============================
# Validator Tests — BOM Request
# ===============================

class TestValidateBomRequest:

    def test_valid_request_returns_no_errors(self, valid_bom_request):
        errors = validate_bom_request(valid_bom_request)
        assert errors == []

    def test_missing_client_id_returns_error(self, valid_bom_request):
        valid_bom_request['client_id'] = ''
        errors = validate_bom_request(valid_bom_request)
        assert any('client_id' in e for e in errors)

    def test_missing_job_id_returns_error(self, valid_bom_request):
        valid_bom_request['job_id'] = ''
        errors = validate_bom_request(valid_bom_request)
        assert any('job_id' in e for e in errors)

    def test_missing_design_data_returns_error(self, valid_bom_request):
        del valid_bom_request['design_data']
        errors = validate_bom_request(valid_bom_request)
        assert any('design_data' in e for e in errors)

    def test_empty_design_data_returns_error(self, valid_bom_request):
        valid_bom_request['design_data'] = {}
        errors = validate_bom_request(valid_bom_request)
        assert len(errors) > 0

    def test_invalid_building_type_returns_error(self, valid_bom_request):
        valid_bom_request['design_data']['building']['type'] = 'underground_bunker'
        errors = validate_bom_request(valid_bom_request)
        assert any('building.type' in e for e in errors)

    def test_invalid_duct_location_returns_error(self, valid_bom_request):
        valid_bom_request['design_data']['building']['duct_location'] = 'moon'
        errors = validate_bom_request(valid_bom_request)
        assert any('building.duct_location' in e for e in errors)

    def test_none_body_returns_error(self):
        errors = validate_bom_request(None)
        assert len(errors) > 0


# ===============================
# ClientProfile Model Tests
# ===============================

class TestClientProfileModel:

    def test_to_dict_includes_all_fields(self, sample_profile):
        d = sample_profile.to_dict()
        assert d['client_id']   == 'beazer-001'
        assert d['client_name'] == 'Beazer Homes'
        assert d['supplier']['supplier_name']          == 'Ferguson'
        assert d['markup']['equipment_pct']            == 15.0
        assert d['brands']['mastic_brand']             == 'Rectorseal'
        assert len(d['part_name_overrides'])           == 1
        assert d['part_name_overrides'][0]['client_sku'] == 'FRG-COL-4IN'

    def test_from_dict_roundtrip(self, sample_profile):
        """Serialize to dict and back — should produce identical profile."""
        d = sample_profile.to_dict()
        restored = ClientProfile.from_dict(d)
        assert restored.client_id                   == sample_profile.client_id
        assert restored.supplier.mastic_cost_per_gallon == sample_profile.supplier.mastic_cost_per_gallon
        assert restored.markup.materials_pct        == sample_profile.markup.materials_pct
        assert len(restored.part_name_overrides)    == len(sample_profile.part_name_overrides)

    def test_from_dict_handles_missing_fields_gracefully(self):
        """Partial data should not crash — missing fields get defaults."""
        profile = ClientProfile.from_dict({"client_id": "test-001", "client_name": "Test"})
        assert profile.client_id == 'test-001'
        assert profile.supplier.mastic_cost_per_gallon == 0.0
        assert profile.markup.equipment_pct == 0.0
        assert profile.part_name_overrides == []
        assert profile.is_active is True
        # Extended fields default to empty/falsy
        assert profile.brand_color == ''
        assert profile.logo_url == ''
        assert profile.supplier.contact_name == ''
        assert profile.supplier.contact_email == ''
        assert profile.markup_tiers == []

    def test_extended_fields_round_trip(self):
        """brand_color / logo_url / supplier.contact_* / markup_tiers
        must survive a to_dict -> from_dict cycle. This is the invariant
        the Designer Desktop SPA depends on to stop losing user input."""
        from models.client_profile import MarkupTier

        original = ClientProfile(
            client_id="roundtrip-test",
            client_name="Round Trip Test",
            brand_color="#f97316",
            logo_url="https://example.com/logo.png",
            supplier=SupplierInfo(
                supplier_name="Ferguson",
                contact_name="Jane Doe",
                contact_email="jane@ferguson.com",
                mastic_cost_per_gallon=18.50,
            ),
            markup=MarkupTiers(equipment_pct=15.0, materials_pct=20.0),
            markup_tiers=[
                MarkupTier(label="High Value", min_amount=5000.0,
                           max_amount=20000.0, markup_percent=10.0),
                MarkupTier(label="Premium", min_amount=20000.0,
                           max_amount=None, markup_percent=8.0),
            ],
        )
        restored = ClientProfile.from_dict(original.to_dict())

        assert restored.brand_color == "#f97316"
        assert restored.logo_url == "https://example.com/logo.png"
        assert restored.supplier.contact_name == "Jane Doe"
        assert restored.supplier.contact_email == "jane@ferguson.com"
        assert len(restored.markup_tiers) == 2
        assert restored.markup_tiers[0].label == "High Value"
        assert restored.markup_tiers[0].min_amount == 5000.0
        assert restored.markup_tiers[0].max_amount == 20000.0
        assert restored.markup_tiers[0].markup_percent == 10.0
        # Unbounded upper tier
        assert restored.markup_tiers[1].max_amount is None


# ===============================
# Pricing Logic Tests
# ===============================

class TestPricingLogic:
    """
    Tests for _apply_pricing and _get_unit_cost.
    These test the math layer — the most critical rule:
    Python does all arithmetic, never the AI.
    """

    def test_mastic_cost_lookup(self, sample_profile):
        from services.bom_service import _get_unit_cost
        cost = _get_unit_cost("Duct mastic (Rectorseal)", "consumable", sample_profile)
        assert cost == 18.50

    def test_tape_cost_lookup(self, sample_profile):
        from services.bom_service import _get_unit_cost
        cost = _get_unit_cost("Foil tape (Nashua)", "consumable", sample_profile)
        assert cost == 12.00

    def test_unknown_item_returns_zero_not_crash(self, sample_profile):
        from services.bom_service import _get_unit_cost
        cost = _get_unit_cost("Some unknown widget", "other", sample_profile)
        assert cost == 0.0

    def test_markup_pct_equipment(self, sample_profile):
        from services.bom_service import _get_markup_pct
        pct = _get_markup_pct("equipment", sample_profile)
        assert pct == 15.0

    def test_markup_pct_consumable(self, sample_profile):
        from services.bom_service import _get_markup_pct
        pct = _get_markup_pct("consumable", sample_profile)
        assert pct == 25.0

    def test_markup_pct_unknown_category_returns_zero(self, sample_profile):
        from services.bom_service import _get_markup_pct
        pct = _get_markup_pct("mystery_category", sample_profile)
        assert pct == 0.0

    def test_apply_pricing_total_math_is_correct(self, sample_profile):
        """Verify Python correctly calculates totals from AI quantities."""
        from services.bom_service import _apply_pricing

        raw = {
            "drawn_items": [],
            "consumables": [
                {"category": "consumable",
                 "description": "Duct mastic (Rectorseal)",
                 "quantity": 2.0,
                 "unit": "GAL"},
            ]
        }
        items = _apply_pricing(raw, sample_profile, "full")
        assert len(items) == 1
        item = items[0]
        # cost: 2.0 GAL * $18.50 = $37.00
        assert item['total_cost'] == 37.00
        # price: $18.50 * 1.25 markup = $23.125 → $23.12 per GAL
        # total price: 2.0 * $23.125 = $46.25
        assert item['total_price'] == 46.25

    def test_part_name_override_applied(self, sample_profile):
        """Client's custom part name should replace standard name."""
        from services.bom_service import _apply_pricing

        raw = {
            "drawn_items": [
                {"category": "fitting",
                 "description": "4-inch collar",
                 "quantity": 4.0,
                 "unit": "EA"}
            ],
            "consumables": []
        }
        items = _apply_pricing(raw, sample_profile, "full")
        assert items[0]['description'] == '4\" snap collar'


class TestFormatRuleLinesForBom:
    """
    The rules engine emits SKU dicts with catalog-sourced unit_cost.
    _format_rule_lines_for_bom should reshape them into the same
    line-item shape _apply_pricing produces and apply profile markup.
    """

    def test_applies_category_markup(self, sample_profile):
        from services.bom_service import _format_rule_lines_for_bom
        rule_lines = [{
            "sku": "AHVE24BP1300A",
            "supplier": "GOODMAN",
            "section": "Equipment",
            "category": "equipment",
            "phase": None,
            "description": "Goodman 2-ton air handler",
            "quantity": 1.0,
            "unit": "ea",
            "unit_cost": 1000.0,
            "total_cost": 1000.0,
        }]
        out = _format_rule_lines_for_bom(rule_lines, sample_profile)
        assert len(out) == 1
        # equipment markup is 15% in the sample profile
        assert out[0]["markup_pct"] == 15.0
        assert out[0]["unit_price"] == 1150.0
        assert out[0]["total_price"] == 1150.0
        assert out[0]["source"] == "rules_engine"
        assert out[0]["sku"] == "AHVE24BP1300A"

    def test_zero_unit_cost_yields_zero_totals(self, sample_profile):
        from services.bom_service import _format_rule_lines_for_bom
        rule_lines = [{
            "sku": "FREEBIE",
            "category": "consumable",
            "description": "No-price item",
            "quantity": 5.0,
            "unit": "ea",
            "unit_cost": 0.0,
            "total_cost": 0.0,
        }]
        out = _format_rule_lines_for_bom(rule_lines, sample_profile)
        assert out[0]["total_cost"] == 0.0
        assert out[0]["total_price"] == 0.0
