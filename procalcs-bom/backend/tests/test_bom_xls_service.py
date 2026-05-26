"""
Sanity tests for services/bom_xls_service.py and the /render-xls route.

These verify the renderer produces a valid .xlsx file with the
expected structure (header, section dividers, per-section subtotals,
grand total) without asserting visual styling — that's better checked
by a human eyeball on the actual file.

The endpoint test exercises the same code path the SPA hits when the
user clicks "Download XLS" on the Wrightsoft BOM result page.
"""

import io
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Day-2 weasyprint stub — create_app() pulls in pdf_service which
# requires weasyprint. We don't actually exercise the PDF path here,
# so a stub keeps tests runnable on dev boxes without GTK installed.
if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        _w = MagicMock()
        _w.HTML = MagicMock()
        _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w

# Required env BEFORE importing app. Direct assignment (not setdefault)
# because some dev shells export these as empty strings, which would
# cause validate_config to fail at app boot.
for _k, _v in (
    ('DATABASE_URL',         'sqlite:///:memory:'),
    ('ANTHROPIC_API_KEY',    'dev-test'),
    ('FIRESTORE_PROJECT_ID', 'dev-test'),
):
    if not os.environ.get(_k):
        os.environ[_k] = _v
# Force empty so the auth middleware fails open — tests don't thread tokens.
os.environ['SERVICE_SHARED_SECRET'] = ''

from openpyxl import load_workbook  # noqa: E402

from services.bom_xls_service import render_bom_xlsx  # noqa: E402


# ─── Fixtures ──────────────────────────────────────────────────────

def _bom(line_items=None, totals=None):
    return {
        "job_id":          "wrightsoft-79th-ct-test",
        "client_id":       "procalcs-direct",
        "profile_name":    "ProCalcs Direct",
        "source_pipeline": "wrightsoft",
        "generated_at":    "2026-05-26T14:30:00Z",
        "item_count":      len(line_items or []),
        "totals":          totals or {"total_price": 12345.67, "total_cost": 10000.00},
        "line_items":      line_items or [
            {
                "section":     "Equipment",
                "generic_id":  "38MARBQ24AA3",
                "description": "Carrier 38MARBQ24AA3 — Heat Pump, Outdoor Split, 24,000 BTU",
                "manufacturer":"CARR",
                "sku":         "38MARBQ24AA3",
                "quantity":    1,
                "unit":        "EA",
                "unit_cost":   2840.00,
                "total_price": 3267.00,
                "source":      "wrightsoft_dfunit",
            },
            {
                "section":     "Duct System Equipment",
                "generic_id":  "DSRND06",
                "description": "Round duct 6 in",
                "manufacturer":"WSF",
                "sku":         "WSF-RD-06",
                "quantity":    50,
                "unit":        "FT",
                "unit_cost":   1.20,
                "total_price": 69.00,
                "source":      "wrightsoft_mapped",
            },
            {
                "section":     "Duct System Equipment",
                "generic_id":  "DFRTRS04",
                "description": "Transition fitting",
                "manufacturer":"WSF",
                "sku":         "WSF-TR-04",
                "quantity":    4,
                "unit":        "EA",
                "unit_cost":   8.50,
                "total_price": 39.10,
                "source":      "wrightsoft_mapped",
            },
            {
                "section":     "Other",
                "generic_id":  "MYSTERY01",
                "description": "Mystery part",
                "manufacturer":None,
                "sku":         None,
                "quantity":    2,
                "unit":        "EA",
                "unit_cost":   0.0,
                "total_price": 0.0,
                "source":      "wrightsoft_unmapped",
            },
        ],
    }


# ─── Renderer ──────────────────────────────────────────────────────

def test_renders_valid_xlsx_bytes():
    out = render_bom_xlsx(_bom())
    assert isinstance(out, bytes)
    assert len(out) > 1000  # not empty / not a tiny error doc
    # openpyxl can re-open what we just wrote — confirms it's a real workbook
    wb = load_workbook(io.BytesIO(out))
    assert "BOM" in wb.sheetnames


def test_contains_section_dividers_and_subtotals():
    wb = load_workbook(io.BytesIO(render_bom_xlsx(_bom())))
    ws = wb.active
    text_cells = [
        c.value for row in ws.iter_rows() for c in row
        if isinstance(c.value, str)
    ]
    assert "Equipment" in text_cells
    assert "Duct System Equipment" in text_cells
    # Per-section subtotals labelled with the section name
    assert any(
        isinstance(v, str) and v.startswith("Subtotal — Equipment")
        for v in text_cells
    )
    assert any(
        isinstance(v, str) and v.startswith("Subtotal — Duct System Equipment")
        for v in text_cells
    )


def test_grand_total_present_and_matches_declared_total():
    wb = load_workbook(io.BytesIO(render_bom_xlsx(_bom())))
    ws = wb.active
    # Walk rows to find the GRAND TOTAL row, then read column 9 (Total $)
    found = None
    for row in ws.iter_rows():
        for cell in row:
            if cell.value == "GRAND TOTAL":
                found = cell.row
                break
        if found:
            break
    assert found is not None, "GRAND TOTAL row missing"
    grand_value = ws.cell(row=found, column=9).value
    assert grand_value == 12345.67  # matches totals.total_price


def test_subtotal_sums_match_line_items():
    bom = _bom()
    wb = load_workbook(io.BytesIO(render_bom_xlsx(bom)))
    ws = wb.active

    # Expected subtotals by section, computed from fixture
    expected = {
        "Equipment":             3267.00,
        "Duct System Equipment": 69.00 + 39.10,
        "Other":                 0.0,
    }
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("Subtotal — "):
                section = cell.value.replace("Subtotal — ", "")
                if section in expected:
                    sub_val = ws.cell(row=cell.row, column=9).value
                    assert abs(float(sub_val) - expected[section]) < 0.01, (
                        f"section {section}: got {sub_val} expected {expected[section]}"
                    )


def test_unknown_section_routed_to_section_block():
    # Items with a section the renderer doesn't recognize go under
    # 'Other' rather than being silently dropped.
    bom = _bom(line_items=[{
        "section":     "AlienCategory",
        "generic_id":  "X1",
        "description": "Mystery",
        "quantity":    1, "unit": "EA",
        "unit_cost":   1.0, "total_price": 1.0,
        "source":      "wrightsoft_mapped",
    }])
    wb = load_workbook(io.BytesIO(render_bom_xlsx(bom)))
    ws = wb.active
    sections = [
        c.value for row in ws.iter_rows() for c in row
        if isinstance(c.value, str) and not c.value.startswith("Subtotal")
    ]
    # The alien section name appears (not silently re-routed)
    assert "AlienCategory" in sections


def test_empty_line_items_rejected_at_caller():
    # render_bom_xlsx itself doesn't reject empty line_items — that's the
    # route's job. It should still produce a valid (essentially-empty)
    # workbook so the contract is "always returns bytes."
    bom = _bom(line_items=[])
    out = render_bom_xlsx(bom)
    wb = load_workbook(io.BytesIO(out))
    ws = wb.active
    # Just the grand-total row + header, no section dividers
    text_cells = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    assert "GRAND TOTAL" in text_cells


# ─── Endpoint ──────────────────────────────────────────────────────

@pytest.fixture
def client():
    from app import create_app
    from extensions import db
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


def test_endpoint_returns_xlsx_bytes(client):
    response = client.post(
        "/api/v1/bom/render-xls",
        json={"bom": _bom()},
    )
    assert response.status_code == 200
    assert response.mimetype == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    # Verify it's a real workbook
    wb = load_workbook(io.BytesIO(response.data))
    assert "BOM" in wb.sheetnames
    # Suggested filename uses job_id
    cd = response.headers.get("Content-Disposition", "")
    assert "wrightsoft-79th-ct-test.xlsx" in cd


def test_endpoint_rejects_missing_bom(client):
    response = client.post("/api/v1/bom/render-xls", json={})
    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "BomResponse" in body["error"]
