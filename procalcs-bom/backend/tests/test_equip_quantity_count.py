"""
test_equip_quantity_count.py — Day-27.

parse_equipment must COUNT identical placed instances (2 identical
Trane systems → qty 2) instead of collapsing them to one. Normal
single-instance files must be unchanged (qty 1). Regression guard for
Richard's 79th-Ct under-count.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import utils.rup_equip_parser as ep


class _FakeReader:
    """Yields N sentinel cursors; _decode_equip is monkeypatched to
    map each sentinel to a prepared row."""
    def __init__(self, n): self._n = n
    def find_all_tags(self, name):
        assert name == "EQUIP"
        return list(range(self._n))


def _rows(monkeypatch, rows):
    seq = iter(rows)
    monkeypatch.setattr(ep, "_decode_equip", lambda cur: next(seq))
    return _FakeReader(len(rows))


def test_identical_instances_are_counted(monkeypatch):
    sysrow = {"equipment_type": "Split AC", "condenser_model": "5TTV0X60A1",
              "coil_model": "5TAMXD07AV51", "manufacturer": "Trane"}
    reader = _rows(monkeypatch, [dict(sysrow), dict(sysrow)])  # 2 identical
    out = ep.parse_equipment(reader)
    assert len(out) == 1
    assert out[0]["quantity"] == 2.0
    assert out[0]["condenser_model"] == "5TTV0X60A1"


def test_single_instances_stay_qty_one(monkeypatch):
    a = {"equipment_type": "Split ASHP", "condenser_model": "27TPA848AC0300",
         "coil_model": "FT5ANXC48L"}
    b = {"equipment_type": "Split ASHP", "condenser_model": "27TPA824A00300",
         "coil_model": "FT5ANXB24L"}
    out = ep.parse_equipment(_rows(monkeypatch, [a, b]))
    assert [r["quantity"] for r in out] == [1.0, 1.0]
    assert len(out) == 2


def test_templates_dropped_not_counted(monkeypatch):
    row = {"equipment_type": "Elec strip", "condenser_model": "BAYEAAC08BK1",
           "coil_model": None}
    # two real + one template (None) → qty 2, template ignored
    out = ep.parse_equipment(_rows(monkeypatch, [dict(row), None, dict(row)]))
    assert len(out) == 1
    assert out[0]["quantity"] == 2.0


def test_order_of_first_appearance_preserved(monkeypatch):
    x = {"equipment_type": "A", "condenser_model": "X", "coil_model": None}
    y = {"equipment_type": "B", "condenser_model": "Y", "coil_model": None}
    out = ep.parse_equipment(_rows(monkeypatch, [x, y, dict(x)]))
    assert [r["condenser_model"] for r in out] == ["X", "Y"]
    assert out[0]["quantity"] == 2.0 and out[1]["quantity"] == 1.0
