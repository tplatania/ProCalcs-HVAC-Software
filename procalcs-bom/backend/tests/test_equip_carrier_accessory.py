"""
Regression: EQUIP-block equipment whose manufacturer identity is in
display_mfr (not mfr_catalog_key) must still be extracted.

Dana (2026-09-17, Rahim II): the Carrier system + its electric heat
strip (KFFEH2601C10) were dropped because Carrier leaves
mfr_catalog_key empty and carries the name only in display_mfr, while
the old discriminator required mfr_catalog_key. Mitsubishi (which
populates mfr_catalog_key) extracted fine; Carrier didn't.

The .rup fixture is a local customer file (not committed) → the
end-to-end test skips when absent. The discriminator behavior is also
locked with synthetic decodes that need no fixture.
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.rup_equip_parser import _decode_equip  # noqa: E402
from utils.rup_reader import RupReader             # noqa: E402

_RAHIM = Path.home() / "Procalcs/bom-dana/Rahim II - Residence Manual D.rup"


def _equip_block(equipment_type, drawing_tag, display_mfr, mfr_key,
                 part_source, condenser_model, coil_model) -> bytes:
    """Build one EQUIP block body matching _decode_equip's layout:
    u32 schema=11, u32 id, u32 flag, 4 zero pad, then 7 utf16 CStrings."""
    def cstr(s: str) -> bytes:
        # RupReader utf16_string: <u32 byte_len><UTF-16LE bytes>.
        b = s.encode("utf-16-le")
        return struct.pack("<I", len(b)) + b
    body = struct.pack("<III", 11, 1, 2) + b"\x00\x00\x00\x00"
    for s in (equipment_type, drawing_tag, display_mfr, mfr_key,
              part_source, condenser_model, coil_model):
        body += cstr(s)
    return body


def _decode(**kw):
    block = _equip_block(**kw)
    return _decode_equip(RupReader(block).cursor_at(0))


def test_carrier_shape_accepted():
    # Carrier heat strip: name in display_mfr, mfr_key empty, has model.
    row = _decode(equipment_type="Elec strip", drawing_tag="",
                  display_mfr="Carrier", mfr_key="", part_source="",
                  condenser_model="KFFEH2601C10", coil_model="")
    assert row is not None
    assert row["condenser_model"] == "KFFEH2601C10"
    assert row["manufacturer"] == "Carrier"


def test_mitsubishi_shape_still_accepted():
    row = _decode(equipment_type="Elec strip", drawing_tag="",
                  display_mfr="Mitsubishi Electric",
                  mfr_key="Mitsubishi Electric", part_source="",
                  condenser_model="EH03-SVZ-S", coil_model="")
    assert row is not None


def test_template_and_mixed_rejected():
    # Empty template (no model / no mfr) → dropped.
    assert _decode(equipment_type="Split AC", drawing_tag="", display_mfr="",
                   mfr_key="", part_source="", condenser_model="",
                   coil_model="") is None
    # (mixed) aggregate placeholder → dropped.
    assert _decode(equipment_type="Elec strip", drawing_tag="",
                   display_mfr="(mixed)", mfr_key="", part_source="",
                   condenser_model="(mixed)", coil_model="") is None


@pytest.mark.skipif(not _RAHIM.exists(), reason="Rahim II .rup not present")
def test_rahim_carrier_heat_strip_extracted():
    from services.bom_from_rup import build_lines_from_rup
    lines = build_lines_from_rup(_RAHIM.read_bytes(), source_name="rahim",
                                 rheia_takeoff=False)
    gids = {str(l.get("generic_id")) for l in lines
            if l.get("section_hint") == "Equipment"}
    assert "KFFEH2601C10" in gids   # Carrier heat strip (was missing)
    assert "EH03-SVZ-S" in gids      # Mitsubishi heat strip (was fine)
