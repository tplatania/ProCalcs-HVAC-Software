"""
Tests for utils/rup_home_run_parser.py — per-register home-run duct
lengths from DUCT blocks (the Rheia 3-in duct / SKU 10-00-190 takeoff
source).

Two layers:

1. Synthetic-bytes unit tests — build minimal DUCT records (both
   observed tail shapes: empty extra-property string and the "SB"
   variant) and verify the decode + trunk-node exclusion rule. No
   corpus file needed.

2. Corpus ground-truth test — decode a real Reliable .rup and check
   the summed footage reproduces the paired Rheia BOM xls total
   (Creekside Lot 100: 597 ft, validated exact on 2026-07-15).
   Skipped when the corpus isn't present (it is never checked in).
"""
from __future__ import annotations

import math
import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.rup_reader import RupReader
from utils.rup_home_run_parser import home_run_total_ft, parse_home_run_lengths

CORPUS_RUP = Path(
    "/Users/geraldvillaran/Procalcs/RUPs-from-zoho/Creekside/Lot Specifics/"
    "Lot 100 T072 SCL REV SE/Lot 100 T072 CO2 SEER2 ACH/Finals/Current/"
    "Lot 100 T072R Plan SCL.rup"
)
CORPUS_XLS_TOTAL_FT = 597.0  # SKU 10-00-190 qty in the paired BOM xls


# ─── Synthetic-record builders ─────────────────────────────────────────

def _s(text: str) -> bytes:
    """u32 byte-length prefixed UTF-16LE string (§0.3 wire format)."""
    body = text.encode("utf-16-le")
    return struct.pack("<I", len(body)) + body


def _duct_record(label: str, length_ft: float, *, obj_id: int = 0x100,
                 seq: int = 1, supply_parent: str = "dmn1",
                 return_parent: str = "rb1", code: str = "VinlFlx",
                 extra_prop: str = "") -> bytes:
    """One !BEG=DUCT ... !END=DUCT span per the layout in
    rup_home_run_parser's docstring."""
    body = struct.pack("<II", 13, obj_id)             # schema, id
    body += _s(label) + _s(supply_parent) + _s(return_parent)
    body += struct.pack("<15f", *([1.0] * 15))        # design numbers
    body += _s(code)
    body += _s("p") + _s("p") + _s("c") + _s("c")     # property strings
    body += _s(extra_prop)                            # extra ("" or "SB")
    body += struct.pack("<III", 0, 0, 0)              # reserved zeros
    body += struct.pack("<II", seq, 0)                # seq, zero
    body += b"\x00\x00"                               # u16 pad
    body += struct.pack("<ff", length_ft, 2.0)        # LENGTH, trail const
    return _s("!BEG=DUCT") + body + _s("!END=DUCT")


def _rup(*records: bytes) -> bytes:
    header = ".WS.rsu.WSF.0004.\r\n\r\n".encode("utf-16-le")
    return header + b"".join(records)


# ─── Synthetic decode tests ────────────────────────────────────────────

def test_decodes_runout_length_and_fields():
    data = _rup(_duct_record("BATH 2-A", 16.8188, obj_id=0x659, seq=27))
    rows = parse_home_run_lengths(RupReader(data))
    assert len(rows) == 1
    row = rows[0]
    assert row["label"] == "BATH 2-A"
    assert row["id"] == 0x659
    assert row["seq"] == 27
    assert row["duct_code"] == "VinlFlx"
    assert math.isclose(row["length_ft"], 16.819, abs_tol=0.001)


def test_extra_property_string_variant_does_not_shift_the_tail():
    """The 'SB' extra-property rows were the day-1 mis-parse: the tail
    shifted 8 bytes and the length read as 0. Lock the fix in."""
    data = _rup(
        _duct_record("BATH 2", 43.0708, seq=10, extra_prop="SB"),
        _duct_record("BEDROOM 3", 35.5708, seq=6, extra_prop=""),
    )
    rows = parse_home_run_lengths(RupReader(data))
    assert [r["label"] for r in rows] == ["BATH 2", "BEDROOM 3"]
    assert math.isclose(rows[0]["length_ft"], 43.071, abs_tol=0.001)
    assert math.isclose(rows[1]["length_ft"], 35.571, abs_tol=0.001)


def test_trunk_and_branch_nodes_are_excluded():
    """Nodes referenced as parents (dmn1/st1/rb1) and unlabeled nodes
    are duct-tree internals, never register home-runs."""
    data = _rup(
        _duct_record("PDR", 26.4175, seq=21),
        _duct_record("dmn1", 0.1, supply_parent="st1", return_parent=""),
        _duct_record("st1", 0.1, supply_parent="", return_parent=""),
        _duct_record("rb1", 0.0, supply_parent="", return_parent=""),
        _duct_record("", 0.0, supply_parent="", return_parent="",
                     code="ShtMetl"),
    )
    rows = parse_home_run_lengths(RupReader(data))
    assert [r["label"] for r in rows] == ["PDR"]


def test_total_helper_sums_runouts():
    data = _rup(
        _duct_record("A", 10.25, seq=1),
        _duct_record("B", 20.50, seq=2),
        _duct_record("dmn1", 0.1, supply_parent="", return_parent=""),
    )
    # helper rounds to 1 decimal (30.75 → 30.8)
    assert home_run_total_ft(RupReader(data)) == pytest.approx(30.75, abs=0.06)


# ─── Corpus ground-truth test ──────────────────────────────────────────

@pytest.mark.skipif(not CORPUS_RUP.exists(),
                    reason="Reliable corpus not present on this machine")
def test_creekside_lot100_matches_rheia_bom_footage():
    """Σ decoded home-run lengths must reproduce the Rheia plugin's
    3-in duct takeoff (10-00-190) from the paired BOM xls. The xls
    total is ceil(Σ) — whole-foot round-up of the exact sum."""
    reader = RupReader(CORPUS_RUP.read_bytes())
    rows = parse_home_run_lengths(reader)
    assert len(rows) == 24                      # one per register runout
    total = sum(r["length_ft"] for r in rows)
    assert math.ceil(total) == CORPUS_XLS_TOTAL_FT
    # every run physically plausible
    assert all(3.0 < r["length_ft"] < 60.0 for r in rows)
