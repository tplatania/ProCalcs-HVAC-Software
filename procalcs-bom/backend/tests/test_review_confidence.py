"""Tests for services.review_confidence (confidence & materiality layer)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.review_confidence import build_review_summary


def _bom(lines):
    b = {"line_items": lines}
    build_review_summary(b)
    return b


def test_no_flags_gives_empty_summary():
    b = _bom([{"sku": "A", "total_price": 100}])
    rs = b["review_summary"]
    assert rs["flagged_count"] == 0
    assert rs["priority_count"] == 0
    assert rs["by_confidence"] == {"low": 0, "medium": 0, "high": 0}


def test_flag_gets_materiality_and_confidence_default():
    b = _bom([{"sku": "A", "total_price": 250, "verify_reason": "check"}])
    li = b["line_items"][0]
    assert li["verify_materiality"] == 250.0
    assert li["verify_confidence"] == "medium"   # default when unset


def test_priority_is_low_confidence_or_high_dollar():
    b = _bom([
        {"sku": "cheap_low", "total_price": 10, "verify_reason": "x", "verify_confidence": "low"},
        {"sku": "cheap_med", "total_price": 10, "verify_reason": "x", "verify_confidence": "medium"},
        {"sku": "rich_med",  "total_price": 4000, "verify_reason": "x", "verify_confidence": "medium"},
        {"sku": "filler",    "total_price": 6000},
    ])
    rs = b["review_summary"]
    skus = {p["sku"] for p in rs["priority_lines"]}
    assert "cheap_low" in skus      # low confidence → priority
    assert "rich_med" in skus       # high dollar → priority
    assert "cheap_med" not in skus  # medium + cheap → not priority


def test_priority_sorted_low_confidence_first_then_dollar():
    b = _bom([
        {"sku": "rich_med", "total_price": 9000, "verify_reason": "x", "verify_confidence": "medium"},
        {"sku": "low1",     "total_price": 5,   "verify_reason": "x", "verify_confidence": "low"},
    ])
    order = [p["sku"] for p in b["review_summary"]["priority_lines"]]
    assert order[0] == "low1"   # low confidence outranks high dollar


def test_high_dollar_threshold_scales_with_bom_but_has_floor():
    small = _bom([{"sku": "A", "total_price": 100, "verify_reason": "x"}])
    assert small["review_summary"]["high_dollar_threshold"] == 500.0  # floor
    big = _bom([{"sku": "A", "total_price": 40000, "verify_reason": "x"}])
    assert big["review_summary"]["high_dollar_threshold"] == 2000.0   # 5%
