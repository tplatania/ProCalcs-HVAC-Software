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

from services.pdf_service import render_bom_pdf  # noqa: E402


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
