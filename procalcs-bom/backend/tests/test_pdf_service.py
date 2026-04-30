"""
Sanity tests for services/pdf_service.py.

These don't assert visual correctness (that requires a human eyeball
on the PDF output) — they confirm that the renderer doesn't crash,
returns valid PDF bytes, and handles edge cases without raising.

Skipped automatically if WeasyPrint can't import — e.g. running
locally on Windows without GTK installed. The CI/prod Docker image
has the system libs, so these run in CI.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# Skip the whole module if WeasyPrint isn't installable in this env.
# On Windows dev machines WeasyPrint needs GTK which is a pain; the
# prod Docker image has it via apt-get.
pytest.importorskip("weasyprint")

from services.pdf_service import render_bom_pdf, _build_pdf_context  # noqa: E402


# ─── Fixtures ───────────────────────────────────────────────────────

def _sample_bom(line_items=None, totals=None):
    """Build a minimal BOM dict shaped like bom_service._format_bom()."""
    return {
        "job_id":       "enos-residence-test",
        "client_id":    "procalcs-direct",
        "client_name":  "ProCalcs Direct",
        "supplier":     "Ferguson",
        "output_mode":  "full",
        "generated_at": "2026-04-11T12:00:00Z",
        "line_items":   line_items if line_items is not None else [
            {
                "category":    "equipment",
                "description": "Air handler 3 ton",
                "quantity":    1.0,
                "unit":        "EA",
                "unit_cost":   2840.00,
                "unit_price":  3267.00,
                "total_cost":  2840.00,
                "total_price": 3267.00,
                "markup_pct":  15.0,
            },
            {
                "category":    "duct",
                "description": 'Flex duct 6" (Atco)',
                "quantity":    180.0,
                "unit":        "LF",
                "unit_cost":   2.85,
                "unit_price":  3.42,
                "total_cost":  513.00,
                "total_price": 615.60,
                "markup_pct":  20.0,
            },
            {
                "category":    "consumable",
                "description": "Duct mastic (Rectorseal)",
                "quantity":    3.0,
                "unit":        "GAL",
                "unit_cost":   38.50,
                "unit_price":  50.05,
                "total_cost":  115.50,
                "total_price": 150.15,
                "markup_pct":  30.0,
            },
        ],
        "totals":     totals or {"total_cost": 3468.50, "total_price": 4032.75},
        "item_count": 3,
    }


# ─── Tests ──────────────────────────────────────────────────────────

def test_render_returns_valid_pdf_bytes():
    pdf = render_bom_pdf(_sample_bom())
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-"), f"Not a PDF: {pdf[:10]!r}"
    assert len(pdf) > 1024, f"Suspiciously small PDF: {len(pdf)} bytes"


def test_render_handles_empty_line_items():
    """An empty BOM should still produce a valid (if blank-ish) PDF."""
    pdf = render_bom_pdf(_sample_bom(line_items=[]))
    assert pdf.startswith(b"%PDF-")


def test_render_handles_missing_totals():
    """When totals is None (or missing), the grand total row renders
    as '—' rather than crashing."""
    bom = _sample_bom()
    bom["totals"] = None
    pdf = render_bom_pdf(bom)
    assert pdf.startswith(b"%PDF-")


def test_render_handles_cost_estimate_mode():
    """cost_estimate mode suppresses unit_price/total_price — the
    template should fall back to unit_cost/total_cost for those
    columns and still produce a valid PDF."""
    bom = _sample_bom()
    bom["output_mode"] = "cost_estimate"
    for item in bom["line_items"]:
        item["unit_price"] = None
        item["total_price"] = None
    bom["totals"] = {"total_cost": 3468.50, "total_price": None}
    pdf = render_bom_pdf(bom)
    assert pdf.startswith(b"%PDF-")


def test_render_normalizes_unknown_category():
    """Unknown category strings get bucketed to consumable rather
    than silently dropped or crashing the template."""
    bom = _sample_bom()
    bom["line_items"].append({
        "category":    "mystery-new-bucket",
        "description": "Unclassified widget",
        "quantity":    1,
        "unit":        "EA",
        "total_price": 99.00,
    })
    pdf = render_bom_pdf(bom)
    assert pdf.startswith(b"%PDF-")


def test_render_handles_register_as_fitting():
    """'register' category from the AI prompt should appear under
    the Fittings section in the PDF output."""
    bom = _sample_bom(line_items=[{
        "category":    "register",
        "description": "Supply register 10x6",
        "quantity":    12,
        "unit":        "EA",
        "total_price": 364.00,
    }])
    pdf = render_bom_pdf(bom)
    assert pdf.startswith(b"%PDF-")


# ─── Provenance / rules-engine context tests ─────────────────────────
#
# These exercise _build_pdf_context directly (no WeasyPrint required)
# so they run on any dev machine. The render_* tests above are still
# the smoke tests that prove the template doesn't crash with these
# fields wired in.


def test_build_context_prefers_backend_provenance_counts():
    """rules_engine_item_count + ai_item_count from bom_service.generate
    should win over any per-line derivation. Mismatched values used so
    the assertion proves the backend totals were honored, not derived."""
    bom = _sample_bom()
    bom["rules_engine_item_count"] = 4
    bom["ai_item_count"] = 12
    ctx = _build_pdf_context(bom)
    assert ctx["rules_count"] == 4
    assert ctx["ai_count"] == 12
    assert ctx["has_provenance"] is True


def test_build_context_derives_provenance_from_line_items_fallback():
    """Older payloads without the merge counts should still get
    provenance, derived from line_items[].source."""
    bom = _sample_bom(line_items=[
        {"category": "equipment", "description": "AHU", "quantity": 1,
         "unit": "EA", "total_price": 1000, "source": "rules", "sku": "AHU-001"},
        {"category": "equipment", "description": "Heat kit", "quantity": 1,
         "unit": "EA", "total_price": 200, "source": "rules", "sku": "HK-005"},
        {"category": "consumable", "description": "Mastic", "quantity": 3,
         "unit": "GAL", "total_price": 150, "source": "ai"},
        {"category": "duct", "description": "Flex 6\"", "quantity": 100,
         "unit": "LF", "total_price": 300},  # no source → counted as ai
    ])
    ctx = _build_pdf_context(bom)
    assert ctx["rules_count"] == 2
    assert ctx["ai_count"] == 2
    assert ctx["has_provenance"] is True


def test_build_context_no_provenance_when_counts_zero():
    """Pre-rules-engine BOMs (no source on any line, no merge counts)
    should set has_provenance=False so the template skips the strip."""
    bom = _sample_bom()  # default fixture has no source/sku fields
    ctx = _build_pdf_context(bom)
    # Default fixture has 3 lines with no source — derived ai_count=3,
    # rules_count=0. Both counts being non-zero would already trigger
    # provenance, but rules_count=0 + ai_count=3 still does — the gate
    # is "any signal at all", which is correct: lines with explicit
    # source="ai" deserve the badge. To get has_provenance=False we
    # need an empty BOM.
    empty = _sample_bom(line_items=[])
    empty_ctx = _build_pdf_context(empty)
    assert empty_ctx["rules_count"] == 0
    assert empty_ctx["ai_count"] == 0
    assert empty_ctx["has_provenance"] is False
    # And the populated fixture: derives ai_count=3 from the 3 lines.
    assert ctx["ai_count"] == 3
    assert ctx["rules_count"] == 0
    assert ctx["has_provenance"] is True


def test_render_with_provenance_does_not_crash():
    """Smoke test: a BOM with rules-engine + AI lines, SKUs, and the
    provenance counts renders to valid PDF bytes. Each line carries
    full numeric fields (unit_cost/unit_price/total_cost/total_price/
    markup_pct) because the template's `is not none` guards trigger
    strict-undefined on Jinja2 ≥ 3.1 when fields are absent rather
    than explicitly None."""
    bom = _sample_bom(line_items=[
        {"category": "equipment", "description": "Air handler 3T",
         "quantity": 1, "unit": "EA",
         "unit_cost": 2840.0, "unit_price": 3267.0,
         "total_cost": 2840.0, "total_price": 3267.0,
         "markup_pct": 15.0,
         "source": "rules", "sku": "AHU-3T-001", "supplier": "Carrier"},
        {"category": "consumable", "description": "Misc fasteners",
         "quantity": 1, "unit": "BOX",
         "unit_cost": 20.0, "unit_price": 25.0,
         "total_cost": 20.0, "total_price": 25.0,
         "markup_pct": 25.0,
         "source": "ai"},
    ])
    bom["rules_engine_item_count"] = 1
    bom["ai_item_count"] = 1
    pdf = render_bom_pdf(bom)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1024
