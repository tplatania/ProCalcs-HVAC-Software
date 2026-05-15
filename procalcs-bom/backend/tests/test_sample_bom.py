"""
Phase 7 — tests for services.sample_bom (XLS / XLSX parser) and
services.bom_comparator (sample-vs-generated diff math). Both are
exercised through the model layer rather than the HTTP route here;
the route is covered separately in test_bom_runs_routes.py.
"""
from __future__ import annotations

import os
import sys
from io import BytesIO

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.sample_bom import parse_sample_bom_bytes
from services.bom_comparator import compare_bom


# ─── Tiny .xlsx fixture builder ─────────────────────────────────────

def _build_xlsx(rows: list[list]) -> bytes:
    """Return raw .xlsx bytes containing the given rows on Sheet1.
    Used so the suite isn't dependent on a checked-in binary file."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─── parse_sample_bom_bytes ─────────────────────────────────────────

class TestParseSampleBom:
    def test_extracts_sku_qty_description_section(self):
        rows = [
            ["Src", "Name", "Description", "Phase", "Qty", "Un", "Tax", "Price", "Ext price"],
            ["", "", "Equipment", "", "", "", "", "", ""],
            ["GOODMAN", "AHVE24BP1300A", "AHU", "None", 1, "", "", 0, 0],
            ["GOODMAN", "GZV6SA1810A", "Condenser", "None", 1, "", "", 0, 0],
            ["", "", "Subtotal, Equipment", "", "", "", "", "", 0],
            ["", "", "Duct System Equipment", "", "", "", "", "", ""],
            ["PGM", "FBTI-1212-10", "Ceiling round boot", "None", 2, "", "", 43.6, 87.2],
        ]
        out = parse_sample_bom_bytes(_build_xlsx(rows), filename="sample.xlsx")
        assert len(out) == 3
        assert out[0]["sku"] == "AHVE24BP1300A"
        assert out[0]["section"] == "Equipment"
        assert out[0]["quantity"] == 1
        assert out[2]["sku"] == "FBTI-1212-10"
        assert out[2]["section"] == "Duct System Equipment"
        assert out[2]["total_price"] == 87.2

    def test_skips_blank_and_subtotal_rows(self):
        rows = [
            ["Src", "Name", "Description", "Qty"],
            [None, None, None, None],
            ["", "", "Subtotal, X", ""],
            ["A", "SKU-1", "Desc", 5],
        ]
        out = parse_sample_bom_bytes(_build_xlsx(rows), filename="x.xlsx")
        assert len(out) == 1
        assert out[0]["sku"] == "SKU-1"

    def test_returns_empty_when_no_recognizable_header(self):
        rows = [["foo", "bar"], ["a", "b"]]
        assert parse_sample_bom_bytes(_build_xlsx(rows), filename="x.xlsx") == []

    def test_raises_on_empty_bytes(self):
        with pytest.raises(ValueError):
            parse_sample_bom_bytes(b"", filename="x.xlsx")

    def test_handles_filename_without_extension_via_magic(self):
        rows = [
            ["Src", "Name", "Description", "Qty"],
            ["A", "SKU-1", "Desc", 1],
        ]
        out = parse_sample_bom_bytes(_build_xlsx(rows), filename="")
        assert len(out) == 1


# ─── compare_bom ────────────────────────────────────────────────────

def _gen_bom(items: list[dict]) -> dict:
    return {
        "line_items": items,
        "item_count": len(items),
        "totals": {"total_cost": 0, "total_price": 0},
    }


class TestCompareBom:
    def test_perfect_sku_match_yields_100pct(self):
        sample = [{"sku": "A", "description": "AHU", "quantity": 1}]
        gen = _gen_bom([{"sku": "A", "description": "AHU", "quantity": 1}])
        report = compare_bom(sample, gen)
        m = report.metrics
        assert m.matched == 1
        assert m.missing == 0
        assert m.extra == 0
        assert m.sku_match_rate == 1.0
        assert m.sku_match_with_qty_rate == 1.0

    def test_sku_match_with_qty_drift_outside_tolerance_is_qty_mismatch(self):
        sample = [{"sku": "HANGER", "description": "Hangers", "quantity": 5}]
        gen = _gen_bom([{"sku": "HANGER", "description": "Hangers", "quantity": 50}])
        report = compare_bom(sample, gen)
        assert report.metrics.qty_mismatch == 1
        assert report.metrics.matched == 0
        # Still counts in headline rate (SKU was found), but not in strict rate
        assert report.metrics.sku_match_rate == 1.0
        assert report.metrics.sku_match_with_qty_rate == 0.0

    def test_qty_within_tolerance_counts_as_matched(self):
        sample = [{"sku": "X", "description": "X", "quantity": 100}]
        gen = _gen_bom([{"sku": "X", "description": "X", "quantity": 103}])  # 3% drift
        report = compare_bom(sample, gen)
        assert report.metrics.matched == 1
        assert report.metrics.qty_mismatch == 0

    def test_missing_when_sample_sku_absent_from_gen(self):
        sample = [
            {"sku": "FOUND", "description": "x", "quantity": 1},
            {"sku": "GAP",   "description": "y", "quantity": 1},
        ]
        gen = _gen_bom([{"sku": "FOUND", "description": "x", "quantity": 1}])
        report = compare_bom(sample, gen)
        assert report.metrics.missing == 1
        assert report.metrics.matched == 1
        # 1 of 2 sample lines covered = 50%
        assert report.metrics.sku_match_rate == 0.5

    def test_extra_when_gen_has_sku_not_in_sample(self):
        sample = [{"sku": "A", "description": "x", "quantity": 1}]
        gen = _gen_bom([
            {"sku": "A", "description": "x", "quantity": 1},
            {"sku": "B", "description": "y", "quantity": 1},
        ])
        report = compare_bom(sample, gen)
        assert report.metrics.extra == 1
        assert report.metrics.matched == 1

    def test_sku_match_is_case_insensitive(self):
        sample = [{"sku": "ahu-24k", "description": "x", "quantity": 1}]
        gen = _gen_bom([{"sku": "AHU-24K", "description": "x", "quantity": 1}])
        report = compare_bom(sample, gen)
        assert report.metrics.matched == 1

    def test_description_fallback_when_sample_has_no_sku(self):
        # Sample line has only description ("AHU"); generated has full
        # description but no matching SKU. Substring pairing should win.
        sample = [{"sku": "", "description": "AHU", "quantity": 1}]
        gen = _gen_bom([{"sku": "", "description": "Air handler 24K BTU AHU", "quantity": 1}])
        report = compare_bom(sample, gen)
        assert report.metrics.matched == 1, report.to_dict()
        assert report.metrics.missing == 0

    def test_handles_empty_sample(self):
        report = compare_bom([], _gen_bom([{"sku": "A", "description": "x", "quantity": 1}]))
        assert report.metrics.sample_count == 0
        assert report.metrics.extra == 1
        # Headline rate falls back to 0 instead of dividing by zero
        assert report.metrics.sku_match_rate == 0.0

    def test_handles_empty_generated(self):
        report = compare_bom(
            [{"sku": "A", "description": "x", "quantity": 1}],
            _gen_bom([]),
        )
        assert report.metrics.missing == 1
        assert report.metrics.sku_match_rate == 0.0

    def test_per_line_payload_includes_status(self):
        sample = [{"sku": "A", "description": "x", "quantity": 1}]
        gen = _gen_bom([{"sku": "A", "description": "x", "quantity": 1}])
        report = compare_bom(sample, gen)
        d = report.to_dict()
        assert d["lines"][0]["status"] == "matched"
        assert d["lines"][0]["sku"] == "A"
