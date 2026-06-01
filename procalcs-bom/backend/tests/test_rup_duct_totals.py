"""
Tests for the Day-14 Phase 4 per-RUP known-duct-LF cache
(models.rup_duct_totals + routes.rup_duct_totals_routes).

Locks in:
  - SHA-256 hash is the cache key (stable across re-uploads)
  - upsert is idempotent on the same hash (insert → update, no dup)
  - lookup returns None for unknown hash, the row for known hash
  - GET / POST endpoints follow the standard envelope
  - Malformed shapes get 400, not 500
  - /parse-rup bundles cached totals into duct_summary on re-upload
    (the value of this whole feature — single round trip)
"""

import hashlib
import io
import json
import os
import sys
from pathlib import Path
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


RUP_FIXTURE = Path("/Users/geraldvillaran/Procalcs/RUPs/79th Ct Residence Load Calcs.rup")


@pytest.fixture
def app():
    from app import create_app
    from extensions import db
    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# ─── Hash + model ──────────────────────────────────────────────────

def test_compute_rup_hash_is_stable():
    from models.rup_duct_totals import compute_rup_hash
    payload = b"some-rup-bytes"
    h1 = compute_rup_hash(payload)
    h2 = compute_rup_hash(payload)
    assert h1 == h2
    assert h1 == hashlib.sha256(payload).hexdigest()
    assert len(h1) == 64


def test_upsert_inserts_then_updates(app):
    from extensions import db
    from models.rup_duct_totals import RupDuctTotals
    h = "a" * 64
    RupDuctTotals.upsert(
        rup_hash=h,
        known_lengths_ft={"round_supply": {"4": 100}},
        source_filename="test.rup",
        updated_by="alice@procalcs.net",
    )
    db.session.commit()
    row1 = RupDuctTotals.lookup(h)
    assert row1.known_lengths_ft == {"round_supply": {"4": 100}}
    assert row1.updated_by == "alice@procalcs.net"

    # Update — same hash, different totals + updated_by
    RupDuctTotals.upsert(
        rup_hash=h,
        known_lengths_ft={"round_supply": {"4": 524.1, "6": 50.0}},
        updated_by="richard@procalcs.net",
    )
    db.session.commit()
    rows = db.session.query(RupDuctTotals).filter_by(rup_hash=h).all()
    assert len(rows) == 1  # no duplicate
    assert rows[0].known_lengths_ft == {"round_supply": {"4": 524.1, "6": 50.0}}
    assert rows[0].updated_by == "richard@procalcs.net"
    # Filename from original insert preserved when not overridden
    assert rows[0].source_filename == "test.rup"


def test_lookup_returns_none_for_unknown(app):
    from models.rup_duct_totals import RupDuctTotals
    assert RupDuctTotals.lookup("0" * 64) is None
    assert RupDuctTotals.lookup("") is None


# ─── REST endpoints ────────────────────────────────────────────────

def test_get_returns_null_for_unknown_hash(client):
    r = client.get("/api/v1/rup-duct-totals/" + "f" * 64)
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["data"] is None


def test_get_rejects_short_hash(client):
    r = client.get("/api/v1/rup-duct-totals/short")
    assert r.status_code == 400
    body = r.get_json()
    assert body["success"] is False
    assert "rup_hash" in body["error"]


def test_post_upsert_then_get_roundtrip(client):
    h = "b" * 64
    payload = {
        "rup_hash": h,
        "known_lengths_ft": {
            "round_supply": {"4": 524.1, "10": 211.5},
            "rect_supply":  {"12x10": 350.0},
        },
        "source_filename": "79th-ct.rup",
    }
    r = client.post(
        "/api/v1/rup-duct-totals",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert r.status_code == 200, r.get_json()
    saved = r.get_json()["data"]
    assert saved["rup_hash"] == h
    assert saved["known_lengths_ft"]["round_supply"]["4"] == 524.1
    # Round-trip via GET
    r2 = client.get(f"/api/v1/rup-duct-totals/{h}")
    fetched = r2.get_json()["data"]
    assert fetched["known_lengths_ft"] == payload["known_lengths_ft"]


def test_post_rejects_bad_shape(client):
    h = "c" * 64
    r = client.post(
        "/api/v1/rup-duct-totals",
        data=json.dumps({"rup_hash": h,
                         "known_lengths_ft": {"round_supply": "not-a-dict"}}),
        content_type="application/json",
    )
    assert r.status_code == 400


# ─── /parse-rup integration ────────────────────────────────────────

def test_parse_rup_includes_hash_in_response(client):
    if not RUP_FIXTURE.exists():
        pytest.skip(f"RUP fixture missing: {RUP_FIXTURE}")
    r = client.post(
        "/api/v1/bom/parse-rup",
        data=RUP_FIXTURE.read_bytes(),
        content_type="application/octet-stream",
    )
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert "rup_hash" in data
    assert len(data["rup_hash"]) == 64


def test_parse_rup_bundles_cached_totals_on_reupload(client):
    """The pay-off: after one upsert, the next /parse-rup of the same
    file returns the cached totals embedded in duct_summary — no
    second round trip needed by the SPA."""
    if not RUP_FIXTURE.exists():
        pytest.skip(f"RUP fixture missing: {RUP_FIXTURE}")
    rup_bytes = RUP_FIXTURE.read_bytes()
    from models.rup_duct_totals import compute_rup_hash
    h = compute_rup_hash(rup_bytes)

    # Pre-cache Richard's known totals for this file
    client.post(
        "/api/v1/rup-duct-totals",
        data=json.dumps({
            "rup_hash": h,
            "known_lengths_ft": {
                "round_supply": {"4": 524.1, "6": 50.0,
                                 "8": 979.2, "10": 211.5},
            },
            "source_filename": "79th Ct Residence Load Calcs.rup",
        }),
        content_type="application/json",
    )

    # Re-upload and confirm totals come back in duct_summary
    r = client.post(
        "/api/v1/bom/parse-rup",
        data=rup_bytes,
        content_type="application/octet-stream",
    )
    data = r.get_json()["data"]
    klf = data["duct_summary"].get("known_lengths_ft")
    assert klf is not None, "expected cached totals to be bundled"
    assert klf["round_supply"]["4"] == 524.1
    assert klf["round_supply"]["10"] == 211.5
    # Audit fields surface too
    assert data["duct_summary"].get("known_lengths_cached_at")
