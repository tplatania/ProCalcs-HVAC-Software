"""
HTTP-level tests for POST /api/v1/contractor-overrides/import (Day-16).

Covers the CSV upload happy path, header tolerance, dollar-formatted
prices, partial-failure reporting, and validation rejections.
"""

import io
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        _w = MagicMock(); _w.HTML = MagicMock(); _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w

for _k, _v in (
    ('DATABASE_URL',         'sqlite:///:memory:'),
    ('ANTHROPIC_API_KEY',    'dev-test'),
    ('FIRESTORE_PROJECT_ID', 'dev-test'),
):
    if not os.environ.get(_k):
        os.environ[_k] = _v
os.environ['SERVICE_SHARED_SECRET'] = ''


@pytest.fixture
def client():
    from app import create_app
    from extensions import db
    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


def _csv(text: str) -> dict:
    """Build a Werkzeug multipart payload from CSV text."""
    return {
        "file": (io.BytesIO(text.encode("utf-8")), "pricing.csv"),
        "client_id": "procalcs-direct",
    }


# ─── happy path ────────────────────────────────────────────────────

def test_import_inserts_new_rows(client):
    csv = (
        "supplier,sku,unit_price,notes\n"
        "GOOD,AHVE24BP1300A,2875.00,Q1 2026 pricing\n"
        "CARR,25HBC518AP0300,4150.50,\n"
    )
    r = client.post('/api/v1/contractor-overrides/import',
                    data=_csv(csv),
                    content_type='multipart/form-data')
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["inserted"] == 2
    assert d["updated"] == 0
    assert d["skipped"] == 0
    assert d["errors"] == []


def test_import_updates_existing_row(client):
    # Seed one row first.
    client.post('/api/v1/contractor-overrides', json={
        "client_id": "procalcs-direct",
        "supplier":  "GOOD",
        "sku":       "AHVE24BP1300A",
        "unit_price": 1000.00,
    })
    csv = "supplier,sku,unit_price\nGOOD,AHVE24BP1300A,2875.00\n"
    r = client.post('/api/v1/contractor-overrides/import',
                    data=_csv(csv),
                    content_type='multipart/form-data')
    d = r.get_json()["data"]
    assert d["updated"] == 1
    assert d["inserted"] == 0


# ─── header / value tolerance ──────────────────────────────────────

def test_import_accepts_header_synonyms_and_dollar_strings(client):
    # $2,875.00 must be quoted so the thousands comma isn't treated as
    # a column delimiter — matches what Excel writes when exporting CSV.
    csv = (
        "Src,Name,Price\n"
        'good,AHVE24BP1300A,"$2,875.00"\n'
        "CARR ,25HBC518AP0300, $4150 \n"
    )
    r = client.post('/api/v1/contractor-overrides/import',
                    data=_csv(csv),
                    content_type='multipart/form-data')
    d = r.get_json()["data"]
    assert d["inserted"] == 2
    assert d["skipped"] == 0

    # Verify the parsed numbers actually landed.
    r2 = client.get('/api/v1/contractor-overrides?client_id=procalcs-direct')
    items = r2.get_json()["data"]["items"]
    prices = sorted(o["unit_price"] for o in items)
    assert prices == [2875.0, 4150.0]


# ─── failure reporting ─────────────────────────────────────────────

def test_import_skips_rows_missing_required_fields(client):
    csv = (
        "supplier,sku,unit_price\n"
        ",AHVE24BP1300A,2875.00\n"     # missing supplier
        "GOOD,,2875.00\n"               # missing sku
        "GOOD,AHVE24BP1300A,\n"         # no override fields
        "CARR,25HBC518AP0300,4150\n"    # ok
    )
    r = client.post('/api/v1/contractor-overrides/import',
                    data=_csv(csv),
                    content_type='multipart/form-data')
    d = r.get_json()["data"]
    assert d["inserted"] == 1
    assert d["skipped"] == 3
    reasons = [e["reason"] for e in d["errors"]]
    assert any("supplier" in x for x in reasons)
    assert any("override fields" in x for x in reasons)


def test_import_rejects_missing_file(client):
    r = client.post('/api/v1/contractor-overrides/import',
                    data={"client_id": "procalcs-direct"},
                    content_type='multipart/form-data')
    assert r.status_code == 400
    assert "Missing" in r.get_json()["error"]


def test_import_rejects_missing_client_id(client):
    r = client.post('/api/v1/contractor-overrides/import',
                    data={"file": (io.BytesIO(b"supplier,sku\n"),
                                    "p.csv")},
                    content_type='multipart/form-data')
    assert r.status_code == 400
    assert "client_id" in r.get_json()["error"]


def test_import_rejects_unsupported_extension(client):
    r = client.post('/api/v1/contractor-overrides/import',
                    data={
                        "file": (io.BytesIO(b"x"), "pricing.pdf"),
                        "client_id": "procalcs-direct",
                    },
                    content_type='multipart/form-data')
    assert r.status_code == 400
    assert "Unrecognized" in r.get_json()["error"]


def test_import_rejects_empty_csv(client):
    r = client.post('/api/v1/contractor-overrides/import',
                    data=_csv("supplier,sku,unit_price\n"),
                    content_type='multipart/form-data')
    assert r.status_code == 400
    assert "Empty upload" in r.get_json()["error"]
