"""
Tests for the Day-14 Phase-2 duct-summary extraction
(utils.rup_parser._extract_duct_summary) and its constraint block in
the AI prompt (services.bom_service).

Locks in:
  - DTYPREF counts come through deterministically (ShtMetl / VinlFlx
    / RectFbg / etc.).
  - Round diameters caught by the 'cfm N "' branch-pattern AND the
    explicit 'round/vinyl/D=' patterns.
  - Rectangular sizes from 'Duct W " x H "' normalized to "HxL"
    (larger-first) so 12x10 and 10x12 don't both appear.
  - 79th Ct Residence fixture round_diameters_present == [4, 6, 8, 10]
    — the exact set Richard's Comparison Summary 4.0 expects.
  - AI prompt carries the constraint when duct_summary is non-empty.
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
    if not RUP_FIXTURE.exists():
        pytest.skip(f"RUP fixture missing: {RUP_FIXTURE}")
    from utils.rup_parser import parse_rup_bytes
    return parse_rup_bytes(RUP_FIXTURE.read_bytes())


# ─── Parser extraction ─────────────────────────────────────────────

def test_duct_summary_present_on_parsed_design():
    d = _design_data()
    assert "duct_summary" in d
    ds = d["duct_summary"]
    assert "type_counts" in ds
    assert "round_diameters_present" in ds
    assert "rect_sizes_present" in ds


def test_dtypref_type_counts_for_79th_ct():
    """Richard's project: 24 sheet metal, 20 vinyl flex, 4 rect
    fiberglass — direct read from DTYPREF section."""
    ds = _design_data()["duct_summary"]
    assert ds["type_counts"] == {"ShtMetl": 24, "VinlFlx": 20, "RectFbg": 4}


def test_round_diameters_match_richards_table():
    """Comparison Summary 4.0 supply table:
        4" = 524.1 ft, 6" = 50.0 ft, 8" = 979.2 ft, 10" = 211.5 ft
    Diameters [4, 6, 8, 10] must come through exactly — no
    hallucinated 12/16/18/20/24 leaking in."""
    ds = _design_data()["duct_summary"]
    assert ds["round_diameters_present"] == [4, 6, 8, 10]


def test_path_counts_distinguish_supply_and_return():
    """Phase 3 — duct_summary carries supply_path_count + return_path_count
    so the AI knows the RUP has return ducts to emit (Richard's
    'RETURNS are not included yet' fix).

    79th Ct prefix counts from the actual binary:
      st (supply trunks)   = 43
      sr+srs (supply rect) = 19
      rb (return branches) = 9
      rt (return trunks)   = 6
    Supply total ≥ 60, return total = 15."""
    ds = _design_data()["duct_summary"]
    assert ds["supply_path_count"] >= 60
    assert ds["return_path_count"] == 15  # 9 rb + 6 rt
    pbp = ds["path_count_by_prefix"]
    assert pbp.get("rb") == 9
    assert pbp.get("rt") == 6
    assert pbp.get("st") == 43


def test_rect_sizes_normalized_larger_first():
    """'12 " x 10 "' and '10 " x 12 "' must collapse to one entry
    ('12x10') so reviewers don't see duplicate-shaped sizes."""
    ds = _design_data()["duct_summary"]
    sizes = ds["rect_sizes_present"]
    # All entries: larger dim first
    for s in sizes:
        a, b = s.split("x")
        assert int(a) >= int(b), f"size {s} not normalized larger-first"


def test_duct_summary_handles_missing_dtypref():
    """A RUP without a DTYPREF section must produce empty type_counts,
    not crash. Defensive for older / sparser RUPs."""
    from utils.rup_parser import _extract_duct_summary
    out = _extract_duct_summary(b"", {})
    assert out["type_counts"] == {}
    assert out["round_diameters_present"] == []
    assert out["rect_sizes_present"] == []


# ─── AI-prompt constraint block ────────────────────────────────────

def test_prompt_includes_duct_constraint_when_summary_present():
    """The constraint block must show up in the AI prompt with the
    types + diameters + sizes verbatim. Forces Claude to bound its
    output to what the RUP actually has."""
    from models.client_profile import (
        ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences,
    )
    from services.bom_service import _build_ai_prompt as _build_prompt
    profile = ClientProfile(
        client_id="x", client_name="X",
        supplier=SupplierInfo(), markup=MarkupTiers(),
        brands=BrandPreferences(), part_name_overrides=[],
    )
    design = {
        "building": {"type": "two_story", "duct_location": "attic"},
        "equipment": [], "duct_runs": [], "fittings": [], "registers": [],
        "rooms": [], "raw_rup_context": "",
        "duct_summary": {
            "type_counts": {"ShtMetl": 24, "VinlFlx": 20, "RectFbg": 4},
            "round_diameters_present": [4, 6, 8, 10],
            "rect_sizes_present": ["12x10", "20x16"],
            "supply_path_count": 62,
            "return_path_count": 15,
            "path_count_by_prefix": {"st": 43, "sr": 12, "srs": 7, "rb": 9, "rt": 6},
        },
    }
    prompt = _build_prompt(design, profile, claimed_lines=[])
    assert "DUCT SYSTEM CONSTRAINT" in prompt
    assert "ShtMetl (24 segments)" in prompt
    assert "VinlFlx (20 segments)" in prompt
    assert "4\"" in prompt and "6\"" in prompt and "8\"" in prompt and "10\"" in prompt
    assert "12x10" in prompt
    assert "OMIT it" in prompt
    # Phase 3 — return-side instruction
    assert "Return paths drawn: 15" in prompt
    assert "RETURN DUCT" in prompt
    assert "must emit return-side" in prompt.lower()


def test_prompt_skips_constraint_when_summary_empty():
    from models.client_profile import (
        ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences,
    )
    from services.bom_service import _build_ai_prompt as _build_prompt
    profile = ClientProfile(
        client_id="x", client_name="X",
        supplier=SupplierInfo(), markup=MarkupTiers(),
        brands=BrandPreferences(), part_name_overrides=[],
    )
    design = {
        "building": {"type": "single_level", "duct_location": "attic"},
        "equipment": [], "duct_runs": [], "fittings": [], "registers": [],
        "rooms": [], "raw_rup_context": "",
        # no duct_summary
    }
    prompt = _build_prompt(design, profile, claimed_lines=[])
    assert "DUCT SYSTEM CONSTRAINT" not in prompt
