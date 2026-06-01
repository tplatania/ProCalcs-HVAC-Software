"""
Tests for the Day-14 Phase-4 known-duct-lengths emission
(bom_service._emit_known_duct_lines) and its AI-prompt suppression.

When the user pastes Wrightsoft's Supply Actual Ln table into the BOM
Engine form, the backend emits one deterministic duct line per
(size, direction) — NO AI involved. The AI prompt is told to skip
duct emission entirely so we don't double-count.

Richard's Lot 1 T333 / 79th Ct scenarios:
    round_supply  4" → 524.1 LF
                  6" → 50.0 LF
                  8" → 979.2 LF
                  10" → 211.5 LF
After paste, those four numbers MUST appear as four duct lines with
the exact quantities.
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


def _profile():
    from models.client_profile import (
        ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences,
    )
    return ClientProfile(
        client_id="duct-known",
        client_name="Duct Known Test",
        supplier=SupplierInfo(supplier_name="WSF"),
        markup=MarkupTiers(materials_pct=15.0),
        brands=BrandPreferences(),
        part_name_overrides=[],
    )


# ─── Emission shape + math ─────────────────────────────────────────

def test_no_known_lengths_emits_no_lines():
    from services.bom_service import _emit_known_duct_lines
    assert _emit_known_duct_lines({}, _profile()) == []
    assert _emit_known_duct_lines({"duct_summary": {}}, _profile()) == []
    assert _emit_known_duct_lines(
        {"duct_summary": {"known_lengths_ft": {}}},
        _profile(),
    ) == []


def test_emits_one_line_per_round_supply_diameter():
    from services.bom_service import _emit_known_duct_lines
    design = {"duct_summary": {"known_lengths_ft": {
        "round_supply": {4: 524.1, 6: 50.0, 8: 979.2, 10: 211.5},
    }}}
    out = _emit_known_duct_lines(design, _profile())
    assert len(out) == 4
    by_qty = {l["quantity"]: l for l in out}
    assert 524.1 in by_qty and 50.0 in by_qty
    assert 979.2 in by_qty and 211.5 in by_qty
    for l in out:
        assert l["category"] == "duct"
        assert l["section"] == "Duct System Equipment"
        assert l["source"] == "user_known_lengths"
        assert l["unit"] == "LF"
        assert "supply" in l["description"]


def test_round_supply_and_return_get_distinct_lines():
    from services.bom_service import _emit_known_duct_lines
    design = {"duct_summary": {"known_lengths_ft": {
        "round_supply": {10: 200},
        "round_return": {10: 100},
    }}}
    out = _emit_known_duct_lines(design, _profile())
    assert len(out) == 2
    sup = next(l for l in out if "supply" in l["description"])
    ret = next(l for l in out if "return" in l["description"])
    assert sup["quantity"] == 200
    assert ret["quantity"] == 100


def test_rect_sizes_emit_with_size_in_description():
    from services.bom_service import _emit_known_duct_lines
    design = {"duct_summary": {"known_lengths_ft": {
        "rect_supply": {"12x10": 350.0, "20x16": 80.0},
    }}}
    out = _emit_known_duct_lines(design, _profile())
    assert len(out) == 2
    descs = [l["description"] for l in out]
    assert any("12x10" in d for d in descs)
    assert any("20x16" in d for d in descs)


def test_skips_zero_or_negative_quantities():
    from services.bom_service import _emit_known_duct_lines
    design = {"duct_summary": {"known_lengths_ft": {
        "round_supply": {4: 0, 6: -5, 8: 100},
    }}}
    out = _emit_known_duct_lines(design, _profile())
    assert len(out) == 1
    assert out[0]["quantity"] == 100


def test_tolerates_string_keyed_diameters_from_json():
    """JSON serialization stringifies dict keys; the emitter must
    coerce '4' back to int 4."""
    from services.bom_service import _emit_known_duct_lines
    design = {"duct_summary": {"known_lengths_ft": {
        "round_supply": {"4": 524.1, "10": 211.5},
    }}}
    out = _emit_known_duct_lines(design, _profile())
    assert len(out) == 2
    descs = [l["description"] for l in out]
    assert any("4-in" in d for d in descs)
    assert any("10-in" in d for d in descs)


# ─── AI-prompt suppression ─────────────────────────────────────────

def test_prompt_tells_ai_to_skip_ducts_when_known_lf_present():
    from services.bom_service import _build_ai_prompt
    design = {
        "building": {"type": "two_story", "duct_location": "attic"},
        "equipment": [], "duct_runs": [], "fittings": [], "registers": [],
        "rooms": [], "raw_rup_context": "",
        "duct_summary": {
            "type_counts": {"VinlFlx": 20},
            "round_diameters_present": [4, 6, 8, 10],
            "rect_sizes_present": [],
            "supply_path_count": 20,
            "return_path_count": 5,
            "known_lengths_ft": {"round_supply": {4: 524.1}},
        },
    }
    prompt = _build_ai_prompt(design, _profile(), claimed_lines=[])
    assert "USER PROVIDED" in prompt
    assert "DO NOT emit" in prompt
    assert "duct" in prompt.lower()


def test_prompt_omits_skip_instruction_when_no_known_lf():
    from services.bom_service import _build_ai_prompt
    design = {
        "building": {"type": "two_story", "duct_location": "attic"},
        "equipment": [], "duct_runs": [], "fittings": [], "registers": [],
        "rooms": [], "raw_rup_context": "",
        "duct_summary": {
            "type_counts": {"VinlFlx": 20},
            "round_diameters_present": [4, 6, 8, 10],
            "rect_sizes_present": [],
            "supply_path_count": 20,
            "return_path_count": 5,
        },
    }
    prompt = _build_ai_prompt(design, _profile(), claimed_lines=[])
    assert "USER PROVIDED" not in prompt
