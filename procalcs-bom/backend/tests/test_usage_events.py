"""
test_usage_events.py — Day-25 adoption/learning-loop telemetry.

Covers the three things that must not silently regress:
  1. provenance derivation (test actors → 'test', everyone else → 'real')
  2. /summary excludes test-provenance rows by default
  3. /impact loop-closure math: an override counts as re-applied only
     on runs AFTER it was created, by non-test actors.
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:  # noqa: BLE001
        _w = MagicMock()
        _w.HTML = MagicMock()
        _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('ANTHROPIC_API_KEY', 'dev-test')
os.environ.setdefault('FIRESTORE_PROJECT_ID', 'dev-test')
os.environ.setdefault('SERVICE_SHARED_SECRET', '')

from app import create_app
from extensions import db
from models import BomRun, ContractorOverride, UsageEvent
from models.usage_event import provenance_for


@pytest.fixture
def app():
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


# ─── Provenance derivation ─────────────────────────────────────────

def test_provenance_test_actor_default_list():
    assert provenance_for("gerald@procalcs.net") == "test"
    assert provenance_for("GERALD@procalcs.net") == "test"
    assert provenance_for("richard@reliableheating.com") == "real"
    assert provenance_for(None) == "real"


def test_provenance_env_override(monkeypatch):
    monkeypatch.setenv("TEST_ACTOR_EMAILS", "qa@x.com")
    assert provenance_for("qa@x.com") == "test"
    assert provenance_for("gerald@procalcs.net") == "real"


# ─── POST /usage-events ────────────────────────────────────────────

def test_record_event_derives_provenance_server_side(client):
    r = client.post("/api/v1/usage-events", json={
        "event": "chat_message", "client_id": "c1",
        "detail": {"snipes": 2},
    }, headers={"X-Procalcs-User-Email": "gerald@procalcs.net"})
    assert r.status_code == 201
    assert r.get_json()["data"]["provenance"] == "test"

    r = client.post("/api/v1/usage-events", json={"event": "chat_message"},
                    headers={"X-Procalcs-User-Email": "team@reliable.com"})
    assert r.get_json()["data"]["provenance"] == "real"


def test_record_event_rejects_unknown_event(client):
    r = client.post("/api/v1/usage-events", json={"event": "made_up"})
    assert r.status_code == 400


# ─── GET /summary ──────────────────────────────────────────────────

def test_summary_excludes_test_rows_by_default(app, client):
    with app.app_context():
        UsageEvent.record(event="chat_message", actor_email="gerald@procalcs.net")
        UsageEvent.record(event="chat_message", actor_email="rich@reliable.com")
        UsageEvent.record(event="override_saved", actor_email="rich@reliable.com")
    data = client.get("/api/v1/usage-events/summary").get_json()["data"]
    assert data["total_events"] == 2
    assert data["by_event"] == {"chat_message": 1, "override_saved": 1}
    assert data["actors"] == [{"email": "rich@reliable.com", "events": 2}]

    incl = client.get("/api/v1/usage-events/summary?include_test=1").get_json()["data"]
    assert incl["total_events"] == 3


# ─── GET /impact — loop-closure math ───────────────────────────────

def _mk_run(client_id, email, created_at, override_ids):
    run = BomRun.record(
        client_id=client_id, job_id=f"job-{created_at.isoformat()}",
        output_mode="full", parsed_design_data={},
        generated_bom={"line_items": [
            {"sku": f"S{i}", "override_id": oid} for i, oid in enumerate(override_ids)
        ]},
        created_by_email=email,
    )
    run.created_at = created_at
    db.session.commit()
    return run


def test_impact_counts_only_later_nontest_runs(app, client):
    t0 = datetime(2026, 7, 1)
    with app.app_context():
        ov = ContractorOverride.upsert(
            contractor_id="c1", supplier="WSF", sku="SKU-1",
            unit_price=42.0, updated_by="rich@reliable.com",
        )
        db.session.commit()
        ov.created_at = t0
        db.session.commit()
        oid = ov.id
        # Before the override existed — must NOT count.
        _mk_run("c1", "rich@reliable.com", t0 - timedelta(days=1), [oid])
        # Two later real runs — count.
        _mk_run("c1", "rich@reliable.com", t0 + timedelta(days=1), [oid])
        _mk_run("c1", "amy@reliable.com",  t0 + timedelta(days=2), [oid])
        # Later, but test actor — must NOT count by default.
        _mk_run("c1", "gerald@procalcs.net", t0 + timedelta(days=3), [oid])
        # Later, no actor email (smoke-suite style) — must NOT count.
        _mk_run("c1", None, t0 + timedelta(days=4), [oid])

    data = client.get("/api/v1/usage-events/impact?client_id=c1").get_json()["data"]
    assert data["totals"]["overrides"] == 1
    assert data["totals"]["overrides_reapplied"] == 1
    assert data["totals"]["total_reapplications"] == 2
    assert data["totals"]["runs_scanned"] == 3  # test + no-email excluded
    assert data["top"][0]["sku"] == "SKU-1"
    assert data["top"][0]["reapplied_runs"] == 2


def test_impact_excludes_test_authored_overrides(app, client):
    with app.app_context():
        ContractorOverride.upsert(
            contractor_id="c1", supplier="WSF", sku="SKU-T",
            unit_price=1.0, updated_by="gerald@procalcs.net",
        )
        db.session.commit()
    data = client.get("/api/v1/usage-events/impact?client_id=c1").get_json()["data"]
    assert data["totals"]["overrides"] == 0
    incl = client.get(
        "/api/v1/usage-events/impact?client_id=c1&include_test=1"
    ).get_json()["data"]
    assert incl["totals"]["overrides"] == 1
