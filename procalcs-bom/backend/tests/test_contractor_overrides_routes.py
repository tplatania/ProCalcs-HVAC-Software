"""
HTTP-level tests for /api/v1/contractor-overrides (Day-13).

Covers GET list, POST upsert (insert + update), DELETE, validation
errors, and that updated_by is taken from the X-Actor-Email header.
"""

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


# ─── POST upsert ───────────────────────────────────────────────────

def test_post_inserts_new_row(client):
    r = client.post('/api/v1/contractor-overrides', json={
        "client_id": "procalcs-direct",
        "supplier":  "GOOD",
        "sku":       "AHVE24BP1300A",
        "unit_price": 2875.00,
    }, headers={"X-Actor-Email": "richard@procalcs.net"})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["success"]
    data = body["data"]
    assert data["unit_price"] == 2875.00
    assert data["updated_by"] == "richard@procalcs.net"
    assert data["sku"] == "AHVE24BP1300A"
    assert data["supplier"] == "GOOD"


def test_post_updates_existing_row(client):
    payload = {"client_id": "c1", "supplier": "GOOD", "sku": "X1",
               "unit_price": 100.0}
    client.post('/api/v1/contractor-overrides', json=payload)
    r = client.post('/api/v1/contractor-overrides', json={
        **payload, "unit_price": 200.0,
    })
    assert r.status_code == 200
    assert r.get_json()["data"]["unit_price"] == 200.0


def test_post_rejects_missing_keys(client):
    r = client.post('/api/v1/contractor-overrides', json={
        "client_id": "c1", "supplier": "", "sku": "X1",
    })
    assert r.status_code == 400
    assert "required" in r.get_json()["error"].lower()


def test_post_rejects_negative_price(client):
    r = client.post('/api/v1/contractor-overrides', json={
        "client_id": "c1", "supplier": "GOOD", "sku": "X1",
        "unit_price": -5.0,
    })
    assert r.status_code == 400
    assert "negative" in r.get_json()["error"].lower()


def test_post_rejects_non_numeric_price(client):
    r = client.post('/api/v1/contractor-overrides', json={
        "client_id": "c1", "supplier": "GOOD", "sku": "X1",
        "unit_price": "not a number",
    })
    assert r.status_code == 400
    assert "number" in r.get_json()["error"].lower()


# ─── GET list ──────────────────────────────────────────────────────

def test_get_returns_overrides_for_contractor(client):
    client.post('/api/v1/contractor-overrides', json={
        "client_id": "c1", "supplier": "GOOD", "sku": "X1", "unit_price": 10.0,
    })
    client.post('/api/v1/contractor-overrides', json={
        "client_id": "c1", "supplier": "GOOD", "sku": "X2", "unit_price": 20.0,
    })
    r = client.get('/api/v1/contractor-overrides?client_id=c1')
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["count"] == 2
    assert {it["sku"] for it in data["items"]} == {"X1", "X2"}


def test_get_isolates_by_contractor(client):
    client.post('/api/v1/contractor-overrides', json={
        "client_id": "a", "supplier": "GOOD", "sku": "X", "unit_price": 1.0})
    client.post('/api/v1/contractor-overrides', json={
        "client_id": "b", "supplier": "GOOD", "sku": "X", "unit_price": 2.0})
    a = client.get('/api/v1/contractor-overrides?client_id=a').get_json()["data"]
    assert a["count"] == 1
    assert a["items"][0]["unit_price"] == 1.0


def test_get_requires_client_id(client):
    r = client.get('/api/v1/contractor-overrides')
    assert r.status_code == 400
    assert "client_id" in r.get_json()["error"]


# ─── DELETE ────────────────────────────────────────────────────────

def test_delete_removes_row(client):
    posted = client.post('/api/v1/contractor-overrides', json={
        "client_id": "c1", "supplier": "GOOD", "sku": "X1", "unit_price": 10.0,
    }).get_json()["data"]
    r = client.delete(f'/api/v1/contractor-overrides/{posted["id"]}')
    assert r.status_code == 200
    assert r.get_json()["data"]["deleted_id"] == posted["id"]
    remaining = client.get('/api/v1/contractor-overrides?client_id=c1').get_json()["data"]
    assert remaining["count"] == 0


def test_delete_returns_404_for_unknown_id(client):
    r = client.delete('/api/v1/contractor-overrides/999999')
    assert r.status_code == 404
