"""
test_rup_pipeline.py — End-to-end test of the .rup → design_data → BOM flow.

Uses the real Enos Residence sample from experiments/ as the fixture and
mocks the Anthropic client so we don't burn tokens in CI.

Run:
    pytest backend/tests/test_rup_pipeline.py -v
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Shim the `anthropic` package so bom_service can be imported locally
# without installing the real SDK. Real CI/prod deploys have it installed
# via procalcs-bom/backend/requirements.txt, in which case this shim is a
# harmless no-op because the real module gets imported first.
if "anthropic" not in sys.modules:
    _anthropic_stub = MagicMock()
    _anthropic_stub.Anthropic = MagicMock()
    sys.modules["anthropic"] = _anthropic_stub

# Same shim for google.cloud.firestore — profile_service imports it at
# module load time and we don't want to require the SDK in local dev.
if "google.cloud.firestore" not in sys.modules:
    _gcloud_stub = MagicMock()
    _firestore_stub = MagicMock()
    sys.modules.setdefault("google", _gcloud_stub)
    sys.modules.setdefault("google.cloud", _gcloud_stub)
    sys.modules["google.cloud.firestore"] = _firestore_stub
    _gcloud_stub.cloud = MagicMock()
    _gcloud_stub.cloud.firestore = _firestore_stub

from utils.rup_parser import parse_rup_bytes, parse_rup_file
from utils.validators import validate_bom_request


# ── Fixture: real Enos Residence .rup file ─────────────────────────────────

# experiments/Enos Residence Load Calcs.rup lives at the repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
ENOS_RUP = _REPO_ROOT / "experiments" / "Enos Residence Load Calcs.rup"


@pytest.fixture
def enos_design_data():
    """Parse the real Enos sample once per test module."""
    if not ENOS_RUP.exists():
        pytest.skip(f"Sample fixture not found at {ENOS_RUP}")
    return parse_rup_file(str(ENOS_RUP))


# ── Parser smoke tests ─────────────────────────────────────────────────────

def test_parser_returns_all_top_level_keys(enos_design_data):
    """The parser must always return the full top-level shape, even if
    individual fields are empty — downstream consumers rely on key
    presence."""
    expected_keys = {
        "project", "location", "building", "equipment",
        "duct_runs", "fittings", "registers", "rooms",
        "metadata", "raw_rup_context",
    }
    assert expected_keys.issubset(enos_design_data.keys())


def test_parser_extracts_project_identity(enos_design_data):
    project = enos_design_data["project"]
    assert project["name"] == "Enos Residence"
    assert "Rackensack" in project["address"]
    assert project["city"] == "Cave Creek"
    assert project["zip"] == "85331"
    assert project["county"] == "Maricopa"


def test_parser_extracts_contractor_block(enos_design_data):
    contractor = enos_design_data["project"]["contractor"]
    assert contractor["name"] == "Tom Platania"
    assert contractor["company"] == "ProCalcs, LLC"
    assert contractor["email"] == "tom@procalcs.net"
    assert contractor["license"] == "CAC1815254"
    # Phone in US 3-3-4 format
    assert len(contractor["phone"].replace("-", "").replace(" ", "")) == 10


def test_parser_extracts_drafter_block(enos_design_data):
    drafter = enos_design_data["project"]["drafter"]
    assert drafter["name"] == "Jayvee Layugn"
    assert "Design Studio" in drafter["company"]


def test_parser_maps_building_to_validator_enums(enos_design_data):
    """BldgType 'Single Level' and PREFS 'Ducts in Attic' must produce
    enum values that pass procalcs-bom's validate_bom_request."""
    building = enos_design_data["building"]
    assert building["type"] == "single_level"
    assert building["duct_location"] == "attic"


def test_parser_enumerates_all_eight_ahus(enos_design_data):
    """Enos is an 8-AHU job; all of them should be enumerated."""
    equipment = enos_design_data["equipment"]
    assert len(equipment) == 8
    names = [e["name"] for e in equipment]
    assert names == [f"AHU - {i}" for i in range(1, 9)]
    # Each entry has the full shape, even if values are None
    for eq in equipment:
        assert set(eq.keys()) >= {"name", "type", "cfm", "tonnage", "model"}
        assert eq["type"] == "air_handler"


def test_parser_extracts_real_rooms(enos_design_data):
    """We expect 25+ real rooms after filtering section-marker garbage."""
    rooms = enos_design_data["rooms"]
    assert len(rooms) >= 25

    names = [r["name"] for r in rooms]
    # A handful of rooms that must be present in a residence this size
    must_have = {"KITCHEN", "MASTER BEDROOM", "DINING", "LAUNDRY"}
    assert must_have.issubset(set(names))

    # None of the filtered section markers should leak through
    must_not_have = {"ECDUCTSYS", "SJD", "TDUCTSYS", "SURFACE"}
    assert must_not_have.isdisjoint(set(names))

    # Every room has an AHU assignment
    for room in rooms:
        assert room["ahu"].startswith("AHU - ")


def test_parser_raw_context_is_substantial(enos_design_data):
    """The raw_rup_context must be rich enough for the AI fallback to
    infer duct footage, register counts, and fitting quantities."""
    ctx = enos_design_data["raw_rup_context"]
    assert len(ctx) > 800
    # Spot-check that key landmarks made it into the narrative
    assert "Enos Residence" in ctx
    assert "single_level" in ctx
    assert "attic" in ctx
    assert "AHU - 1" in ctx
    assert "KITCHEN" in ctx
    assert "cfm" in ctx.lower()
    # Duct dimensions line is present
    assert "Duct dimensions observed" in ctx


def test_parser_metadata_reflects_file(enos_design_data):
    meta = enos_design_data["metadata"]
    assert meta["source_file"] == "Enos Residence Load Calcs.rup"
    assert meta["version"].startswith("25.")   # Wrightsoft v25.x
    assert meta["section_count"] >= 30


# ── Validator integration ─────────────────────────────────────────────────

def test_parser_output_passes_bom_validator(enos_design_data):
    """The parser's output plugged straight into validate_bom_request must
    pass — this is the end-to-end contract with the BOM engine."""
    request_body = {
        "client_id":   "procalcs-direct",
        "job_id":      "enos-2025-11",
        "design_data": enos_design_data,
    }
    errors = validate_bom_request(request_body)
    assert errors == [], f"Validator rejected parser output: {errors}"


def test_validator_rejects_empty_design_data(enos_design_data):
    """Sanity: if every structured array is empty AND no equipment, the
    validator should still reject the request. (This tests the invariant
    that the parser's equipment array satisfies has_content.)"""
    empty_body = {
        "client_id":   "procalcs-direct",
        "job_id":      "enos-2025-11",
        "design_data": {"building": enos_design_data["building"]},
    }
    errors = validate_bom_request(empty_body)
    assert any("design_data" in e or "duct_runs" in e for e in errors)


# ── End-to-end pipeline with mocked Anthropic ─────────────────────────────

_FAKE_CLAUDE_RESPONSE = json.dumps({
    "drawn_items": [
        {"category": "equipment", "description": "Air handler 3 ton", "quantity": 1.0, "unit": "EA"},
        {"category": "duct",      "description": "16\" round flex duct", "quantity": 42.0, "unit": "LF"},
        {"category": "fitting",   "description": "90 elbow 16\"", "quantity": 6.0, "unit": "EA"},
        {"category": "register",  "description": "Supply register 10x6", "quantity": 12.0, "unit": "EA"},
    ],
    "consumables": [
        {"category": "consumable", "description": "Duct mastic (Rectorseal)", "quantity": 3.0, "unit": "GAL"},
        {"category": "consumable", "description": "Foil tape (Nashua)", "quantity": 4.0, "unit": "ROLL"},
        {"category": "consumable", "description": "Sheet metal screws", "quantity": 2.0, "unit": "BOX"},
    ],
    "estimator_notes": "Residential 8-AHU job, ducts in vented attic",
})


@pytest.fixture
def fake_anthropic_client():
    """Mock anthropic.Anthropic so no real API call is made."""
    fake_client = MagicMock()
    fake_message = MagicMock()
    fake_message.content = [MagicMock(text=_FAKE_CLAUDE_RESPONSE)]
    fake_client.messages.create.return_value = fake_message
    return fake_client


@pytest.fixture
def fake_profile():
    """A minimal ClientProfile stub with non-zero costs and markups so
    the pricing pipeline produces observable numbers."""
    from models.client_profile import (
        ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences,
    )
    return ClientProfile(
        client_id="procalcs-direct",
        client_name="ProCalcs Direct",
        is_active=True,
        supplier=SupplierInfo(
            supplier_name="Ferguson",
            mastic_cost_per_gallon=38.50,
            tape_cost_per_roll=12.75,
            strapping_cost_per_roll=24.00,
            screws_cost_per_box=18.50,
            brush_cost_each=4.25,
            flex_duct_cost_per_foot=2.85,
            rect_duct_cost_per_sqft=6.40,
        ),
        markup=MarkupTiers(
            equipment_pct=15.0,
            materials_pct=20.0,
            consumables_pct=30.0,
            labor_pct=0.0,
        ),
        brands=BrandPreferences(
            ac_brand="Carrier",
            mastic_brand="Rectorseal",
            tape_brand="Nashua",
            flex_duct_brand="Atco",
        ),
    )


def test_bom_service_prompt_includes_raw_context(enos_design_data, fake_profile):
    """The extended prompt builder must include the raw_rup_context block
    when the input design_data came from the .rup parser."""
    from services.bom_service import _build_ai_prompt
    prompt = _build_ai_prompt(enos_design_data, fake_profile)
    assert "RUP FILE CONTEXT" in prompt
    assert "Enos Residence" in prompt
    assert "single_level" in prompt
    assert "Rooms (" in prompt
    assert "KITCHEN" in prompt


def test_full_pipeline_with_mocked_ai(enos_design_data, fake_profile, fake_anthropic_client):
    """End-to-end: parse Enos .rup → feed design_data to bom_service.generate
    with a mocked Anthropic client → get back a priced BOM."""
    from services import bom_service

    with patch.object(bom_service, 'anthropic') as mock_mod, \
         patch.object(bom_service, 'get_profile_by_id', return_value=fake_profile.to_dict()):
        mock_mod.Anthropic.return_value = fake_anthropic_client

        from flask import Flask
        app = Flask(__name__)
        app.config['ANTHROPIC_API_KEY'] = 'test-key'
        app.config['ANTHROPIC_MODEL'] = 'claude-sonnet-4'
        app.config['ANTHROPIC_MAX_TOKENS'] = 4096

        with app.app_context():
            bom = bom_service.generate(
                client_id="procalcs-direct",
                job_id="enos-2025-11",
                design_data=enos_design_data,
                output_mode="full",
            )

    assert bom["job_id"] == "enos-2025-11"
    assert bom["client_id"] == "procalcs-direct"
    assert bom["supplier"] == "Ferguson"
    assert bom["item_count"] >= 5
    assert bom["totals"]["total_cost"] is not None
    assert bom["totals"]["total_price"] is not None
    # Sanity: price must be >= cost (markup is non-negative)
    assert bom["totals"]["total_price"] >= bom["totals"]["total_cost"]


# ── Error handling ─────────────────────────────────────────────────────────

def test_parser_rejects_non_rup_bytes():
    """A non-Wrightsoft file should either return a safe empty-ish result
    or degrade gracefully — never raise an unhandled exception."""
    fake = b"this is not a wrightsoft file at all" * 100
    result = parse_rup_bytes(fake, source_name="junk.bin")
    # Fields exist but most are empty
    assert result["equipment"] == []
    assert result["rooms"] == []
    assert result["building"]["type"] == "other"
    assert result["building"]["duct_location"] == "other"
