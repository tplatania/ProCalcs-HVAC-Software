"""
Phase 11 — tests for services.bom_diff (server-side mirror of
src/lib/bom-diff.ts in designer-desktop). Used by the regression-suite
endpoint to auto-flag drift without round-trips.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.bom_diff import diff_summary, is_regression


def _bom(items, totals=None):
    line_items = items
    total_cost  = (totals or {}).get("total_cost",  sum(li.get("total_cost",  0) for li in line_items))
    total_price = (totals or {}).get("total_price", sum(li.get("total_price", 0) for li in line_items))
    return {
        "line_items": line_items,
        "totals": {"total_cost": total_cost, "total_price": total_price},
        "item_count": len(line_items),
    }


class TestDiffSummary:
    def test_identical_boms_have_no_changes(self):
        items = [{"sku": "A", "quantity": 1, "total_cost": 10, "total_price": 13}]
        s = diff_summary(_bom(items), _bom(items))
        assert s["unchanged"] == 1
        assert s["added"] == 0 and s["removed"] == 0 and s["changed"] == 0
        assert s["total_cost_delta"] == 0
        assert is_regression(s) is False

    def test_added_sku_flagged(self):
        left = _bom([{"sku": "A", "quantity": 1, "total_cost": 10, "total_price": 13}])
        right = _bom([
            {"sku": "A", "quantity": 1, "total_cost": 10, "total_price": 13},
            {"sku": "B", "quantity": 2, "total_cost": 50, "total_price": 65},
        ])
        s = diff_summary(left, right)
        assert s["added"] == 1
        assert s["item_count_delta"] == 1
        assert s["total_cost_delta"] == 50
        assert is_regression(s) is True

    def test_removed_sku_flagged(self):
        left = _bom([
            {"sku": "A", "quantity": 1, "total_cost": 10, "total_price": 13},
            {"sku": "B", "quantity": 1, "total_cost": 5,  "total_price": 6},
        ])
        right = _bom([{"sku": "A", "quantity": 1, "total_cost": 10, "total_price": 13}])
        s = diff_summary(left, right)
        assert s["removed"] == 1
        assert is_regression(s) is True

    def test_qty_change_flagged_as_changed(self):
        left = _bom([{"sku": "X", "quantity": 1, "total_cost": 10, "total_price": 13}])
        right = _bom([{"sku": "X", "quantity": 5, "total_cost": 10, "total_price": 13}])
        s = diff_summary(left, right)
        assert s["changed"] == 1
        assert is_regression(s) is True

    def test_subcent_jitter_treated_unchanged(self):
        left = _bom([{"sku": "A", "quantity": 1, "total_cost": 10.001, "total_price": 13.0049}])
        right = _bom([{"sku": "A", "quantity": 1, "total_cost": 10.0049, "total_price": 13.0001}])
        s = diff_summary(left, right)
        assert s["unchanged"] == 1
        assert s["changed"] == 0
        assert is_regression(s) is False

    def test_handles_null_sides(self):
        right = _bom([{"sku": "A", "quantity": 1, "total_cost": 10, "total_price": 13}])
        s = diff_summary(None, right)
        assert s["added"] == 1
        assert s["left_item_count"] == 0
        assert s["right_item_count"] == 1
        assert is_regression(s) is True

    def test_uses_bom_level_totals(self):
        # Per-line totals zero (output_mode hides them) but BOM-level totals set.
        left = _bom([{"sku": "A", "quantity": 1}], totals={"total_cost": 100, "total_price": 130})
        right = _bom([{"sku": "A", "quantity": 1}], totals={"total_cost": 110, "total_price": 143})
        s = diff_summary(left, right)
        assert s["total_cost_delta"] == 10
        assert s["total_price_delta"] == 13
