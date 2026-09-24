"""
M-sheet extraction (Richard NE 132nd #5 / Dana — the mechanical schedule
supplies the accessories the .rup lacks).

Locks the HIGH-confidence extraction (equipment schedule + detail
accessories) against the Rahim II M-sheet. The PDF is a customer file
(not committed) and pdfplumber may not be installed everywhere, so this
skips cleanly when either is absent.
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.msheet_extract import (  # noqa: E402
    extract_equipment_schedule, extract_detail_accessories, extract_msheet,
)

_RAHIM = Path.home() / "Procalcs/bom-dana/Rahim II - Residence M Sheets.pdf"
_HAS_PDFPLUMBER = importlib.util.find_spec("pdfplumber") is not None
_needs = pytest.mark.skipif(
    not (_RAHIM.exists() and _HAS_PDFPLUMBER),
    reason="Rahim M-sheet PDF and/or pdfplumber not available")


# ── Pure-text unit tests (no PDF / no pdfplumber needed) ──────────────

_SCHED = (
    "CU NUMBER                 CU-1\n"
    "NOMINAL TONNAGE           3.5 ton(s)\n"
    "MODEL                     26SPA642WC0300\n"
    "MCA/MOP 22.7/40.0\n"
    "AHU-MODEL                 FJ5ANXC42L15\n"
    "REFRIGERANT               R-454B\n"
    "Model Number  SUZ-AA12NL\n"
    "Model  SVZ-AP12NL\n"
    "Refrig Pipe Dim High/Low Pressure (inch) (See Note 4)  1/4 / 3/8\n"
    "Max Pipe Length from BC or 1st Joint (feet)  0.0\n"
)


def test_equipment_schedule_parses_both_systems():
    systems = extract_equipment_schedule(_SCHED)
    tags = {s["system_tag"] for s in systems}
    assert tags == {"CU-1 / AHU-1", "CU-2 / AHU-2"}
    carrier = next(s for s in systems if s["system_tag"].startswith("CU-1"))
    assert carrier["condenser_model"] == "26SPA642WC0300"
    assert carrier["ahu_model"] == "FJ5ANXC42L15"
    assert carrier["tonnage"] == "3.5"
    assert carrier["refrigerant_type"] == "R-454B"
    mit = next(s for s in systems if s["system_tag"].startswith("CU-2"))
    assert mit["condenser_model"] == "SUZ-AA12NL"
    assert mit["ahu_model"] == "SVZ-AP12NL"
    assert mit["refrig_pipe_dim_in"] == "1/4 / 3/8"
    assert mit["max_pipe_length_ft"] == "0.0"


def test_detail_accessories_flags():
    text = ("16 GA. HURRICANE\nSTRAP\nISOMODE PAD\nEXPANSION ANCHOR\n"
            "MANUALLY PRIME FILL TRAP BEFORE START-UP")
    acc = extract_detail_accessories(text)
    assert acc["hurricane_strap"] is True     # split across a line break
    assert acc["condensate_trap"] is True
    assert acc["isomode_pad"] is True
    assert acc["expansion_anchor"] is True


# ── End-to-end on the real Rahim M-sheet ─────────────────────────────

@_needs
def test_rahim_msheet_end_to_end():
    out = extract_msheet(_RAHIM.read_bytes())
    assert out["has_text_layer"] is True
    models = {s.get("condenser_model") for s in out["equipment"]} | \
             {s.get("ahu_model") for s in out["equipment"]}
    # All four .rup equipment models are named in the schedule.
    for m in ("26SPA642WC0300", "FJ5ANXC42L15", "SUZ-AA12NL", "SVZ-AP12NL"):
        assert m in models
    # The accessory data the .rup can't give:
    mit = next(s for s in out["equipment"] if s["system_tag"].startswith("CU-2"))
    assert mit["refrig_pipe_dim_in"] == "1/4 / 3/8"
    assert out["detail_accessories"]["condensate_trap"] is True
    # Thermostats are honestly not counted from the text layer.
    assert out["thermostats"]["count"] is None
