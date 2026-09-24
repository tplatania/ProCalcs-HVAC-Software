"""
Duct-cut per-piece counting (NE 132nd, Richard 2026-09-24).

Richard's finding: the "Duct Cuts (per piece)" table collapsed every
flex size to 1 cut / 2 joints, because it was built from the aggregated
BOM (one line per size) instead of the .rup's per-run geometry. Joints
drive tape + mastic, so the undercount cascades.

Fix: flex is counted per physical round segment from duct_geometry;
rigid trunk (rect/sheet metal) stays 1 run per size ("1 trunk run of
the same size is fine" — his reply #2). Family comes from the SKU.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.bom_quick_order import build_duct_cuts_summary  # noqa: E402

_NE132 = Path.home() / "Procalcs/bom-dana/NE 132nd Terrance Residence RE.rup"

# Real NE 132nd duct line items (aggregated — one row per size).
_LINES = [
    {"generic_id": "DDVn04MI", "quantity": 7.26},   # flex 4"
    {"generic_id": "DDVn07MI", "quantity": 34.31},  # flex 7"
    {"generic_id": "DDVn06MI", "quantity": 9.0},    # flex 6"
    {"generic_id": "DRFg1210MI", "quantity": 18.0}, # rect fiberglass trunk
]
# Round segments from the .rup drawing geometry (Richard's layout).
_GEOM = (
    [{"shape": "round", "diameter_in": 4.0, "cut_length_ft": L}
     for L in (1.25, 5.3, 0.51)] +
    [{"shape": "round", "diameter_in": 7.0, "cut_length_ft": L}
     for L in (7.2, 1.9, 1.5, 7.0, 1.5, 7.0, 1.5, 2.75, 2.25)] +
    [{"shape": "round", "diameter_in": 6.0, "cut_length_ft": 9.0}] +
    # a rect trunk segment — must NOT split the trunk line
    [{"shape": "rect", "width_in": 12.0, "height_in": 10.0, "cut_length_ft": 5.0}]
)


def _by_size(rows):
    return {r["size"]: r for r in rows}


def test_flex_counted_per_piece_from_geometry():
    rows = _by_size(build_duct_cuts_summary(_LINES, _GEOM))
    # 4" flex → 3 pieces, 6 joints (was 1/2)
    assert rows['4"']["cut_count"] == 3
    assert rows['4"']["total_joints"] == 6
    # 7" flex → 9 pieces, 18 joints
    assert rows['7"']["cut_count"] == 9
    assert rows['7"']["total_joints"] == 18
    # 6" flex → 1 piece, 2 joints (already correct)
    assert rows['6"']["cut_count"] == 1
    assert rows['6"']["total_joints"] == 2


def test_rect_trunk_stays_one_run_per_size():
    rows = _by_size(build_duct_cuts_summary(_LINES, _GEOM))
    trunk = rows["12x10"]
    assert trunk["family"] == "Rectangular fiberglass duct"
    assert trunk["cut_count"] == 1     # Richard #2: 1 trunk run/size
    assert trunk["total_joints"] == 2


def test_without_geometry_falls_back_to_one_cut():
    # No geometry → previous behavior (1 cut/size), never crashes.
    rows = _by_size(build_duct_cuts_summary(_LINES, None))
    assert rows['4"']["cut_count"] == 1
    assert rows['7"']["cut_count"] == 1


def test_flex_size_absent_from_geometry_keeps_fallback():
    # A flex size with no matching round geometry keeps its single cut.
    lines = [{"generic_id": "DDVn20MI", "quantity": 12.0}]  # 20", no geom
    rows = _by_size(build_duct_cuts_summary(lines, _GEOM))
    assert rows['20"']["cut_count"] == 1


@pytest.mark.skipif(not _NE132.exists(), reason="NE 132nd .rup not present")
def test_ne132_geometry_reproduces_richard_counts():
    from utils.rup_reader import RupReader
    from utils.rup_duct_geometry import join_duct_geometry
    geom = join_duct_geometry(RupReader(_NE132.read_bytes()))
    counts = {}
    for g in geom:
        if g.get("shape") == "round" and g.get("diameter_in"):
            counts[int(round(g["diameter_in"]))] = counts.get(int(round(g["diameter_in"])), 0) + 1
    # Richard's hand analysis: 4"=3, 6"=1, 7"=9, 8"=2, 16"=1
    assert counts.get(4) == 3
    assert counts.get(6) == 1
    assert counts.get(7) == 9
    assert counts.get(8) == 2
    assert counts.get(16) == 1
