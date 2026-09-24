"""
M-sheet ↔ BOM reconciliation → review flags (never mutates the BOM).
See services/msheet_reconcile.py.
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.msheet_reconcile import reconcile  # noqa: E402

_RAHIM = Path.home() / "Procalcs/bom-dana/Rahim II - Residence M Sheets.pdf"
_HAS_PDFPLUMBER = importlib.util.find_spec("pdfplumber") is not None


def _rahim_msheet():
    return {
        "has_text_layer": True,
        "equipment": [
            {"system_tag": "CU-1 / AHU-1", "condenser_model": "26SPA642WC0300",
             "ahu_model": "FJ5ANXC42L15", "refrigerant_type": "R-454B"},
            {"system_tag": "CU-2 / AHU-2", "condenser_model": "SUZ-AA12NL",
             "ahu_model": "SVZ-AP12NL", "refrig_pipe_dim_in": "1/4 / 3/8"},
        ],
        "detail_accessories": {"condensate_trap": True, "hurricane_strap": True,
                               "isomode_pad": True, "expansion_anchor": True},
        "air_devices": [{"cfm": 150, "neck_in": 8}, {"cfm": 43, "neck_in": 4}],
    }


def _bom(equipment_ids, *, auto=21, extra_lines=None):
    lines = [{"section": "Equipment", "generic_id": g, "description": g}
             for g in equipment_ids]
    lines += (extra_lines or [])
    return {"line_items": lines,
            "register_preflight": {"auto_count": auto, "total": 40}}


def _codes(flags):
    return {f["code"] for f in flags}


def test_missing_accessories_flagged_when_absent():
    bom = _bom(["26SPA642WC0300", "FJ5ANXC42L15", "SUZ-AA12NL***", "SVZ-AP12NL***"])
    flags = reconcile(_rahim_msheet(), bom)
    codes = _codes(flags)
    assert "missing_refrigerant" in codes
    assert "missing_condensate" in codes
    assert "missing_straps" in codes
    assert "grille_true_sizes" in codes
    # models all present → no equipment mismatch
    assert "equipment_mismatch" not in codes
    # refrigerant flag carries the schedule's dims
    ref = [f for f in flags if f["code"] == "missing_refrigerant"]
    assert any(f["proposed"].get("pipe_dim_in") == "1/4 / 3/8" for f in ref)


def test_equipment_mismatch_when_model_absent():
    bom = _bom(["26SPA642WC0300", "FJ5ANXC42L15"])  # Mitsubishi missing
    codes = _codes(reconcile(_rahim_msheet(), bom))
    assert "equipment_mismatch" in codes


def test_no_refrigerant_flag_when_bom_already_has_it():
    bom = _bom(["26SPA642WC0300", "FJ5ANXC42L15", "SUZ-AA12NL***", "SVZ-AP12NL***"],
               extra_lines=[{"section": "Accessories",
                             "description": "Refrigerant line set 1/4x3/8"}])
    assert "missing_refrigerant" not in _codes(reconcile(_rahim_msheet(), bom))


def test_no_grille_flag_when_no_auto_sized_registers():
    bom = _bom(["26SPA642WC0300"], auto=0)
    assert "grille_true_sizes" not in _codes(reconcile(_rahim_msheet(), bom))


def test_scanned_msheet_no_text_layer_yields_no_flags():
    assert reconcile({"has_text_layer": False}, _bom(["26SPA642WC0300"])) == []


def test_reconcile_never_mutates_bom():
    bom = _bom(["26SPA642WC0300", "FJ5ANXC42L15", "SUZ-AA12NL***", "SVZ-AP12NL***"])
    before = len(bom["line_items"])
    reconcile(_rahim_msheet(), bom)
    assert len(bom["line_items"]) == before  # flags only, no lines added


@pytest.mark.skipif(not (_RAHIM.exists() and _HAS_PDFPLUMBER),
                    reason="Rahim M-sheet / pdfplumber unavailable")
def test_end_to_end_real_msheet_plus_bom():
    from services.msheet_extract import extract_msheet
    ms = extract_msheet(_RAHIM.read_bytes())
    bom = _bom(["26SPA642WC0300", "FJ5ANXC42L15", "SUZ-AA12NL***", "SVZ-AP12NL***"])
    flags = reconcile(ms, bom)
    codes = _codes(flags)
    assert "missing_refrigerant" in codes and "grille_true_sizes" in codes
    # At least one system carries the schedule's pipe dims (the Mitsubishi
    # one; the Carrier column lists no pipe-dim row on this M-sheet).
    ref = [f for f in flags if f["code"] == "missing_refrigerant"]
    assert any(f["proposed"].get("pipe_dim_in") == "1/4 / 3/8" for f in ref)
