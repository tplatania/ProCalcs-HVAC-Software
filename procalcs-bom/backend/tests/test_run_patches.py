"""
test_run_patches.py — Day-25 run-scoped surgical corrections.

Patches fix one run's BOM only (quantity edits, removals, additions
from the review chat). They must never touch contractor_overrides,
and rule-phrased corrections must produce a rule_candidate event
instead of any standing rule.
"""

import sys
import os
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


@pytest.fixture
def run_id(app):
    with app.app_context():
        run = BomRun.record(
            client_id="c1", job_id="job-1", output_mode="full",
            parsed_design_data={}, generated_bom={"line_items": [
                {"sku": "SKU-1", "quantity": 10},
            ]},
        )
        db.session.commit()
        return run.id


def test_patch_appends_and_returns_ops(client, run_id):
    r = client.post(f"/api/v1/bom-runs/{run_id}/patches", json={
        "op": "update_line", "sku": "SKU-1",
        "fields": {"quantity": 12},
        "reason": "field crew reports 12 boots on this plan",
        "snipe_ref": "row:li:SKU-1",
    }, headers={"X-Procalcs-User-Email": "rich@reliable.com"})
    assert r.status_code == 200
    ops = r.get_json()["data"]["patch_ops"]
    assert len(ops) == 1
    assert ops[0]["op"] == "update_line"
    assert ops[0]["fields"] == {"quantity": 12}
    assert ops[0]["author"] == "rich@reliable.com"
    assert ops[0]["snipe_ref"] == "row:li:SKU-1"

    # second patch appends, not replaces
    r2 = client.post(f"/api/v1/bom-runs/{run_id}/patches", json={
        "op": "remove_line", "sku": "SKU-1", "reason": "not used here",
    })
    assert len(r2.get_json()["data"]["patch_ops"]) == 2


def test_patch_included_in_run_detail(client, run_id):
    client.post(f"/api/v1/bom-runs/{run_id}/patches", json={
        "op": "remove_line", "sku": "SKU-1", "reason": "dup",
    })
    detail = client.get(f"/api/v1/bom-runs/{run_id}").get_json()["data"]
    assert len(detail["patch_ops"]) == 1


def test_patch_validation(client, run_id):
    assert client.post(f"/api/v1/bom-runs/{run_id}/patches", json={
        "op": "explode", "sku": "S", "reason": "r"}).status_code == 400
    assert client.post(f"/api/v1/bom-runs/{run_id}/patches", json={
        "op": "remove_line", "sku": "", "reason": "r"}).status_code == 400
    # update without fields is meaningless
    assert client.post(f"/api/v1/bom-runs/{run_id}/patches", json={
        "op": "update_line", "sku": "S", "reason": "r"}).status_code == 400
    assert client.post("/api/v1/bom-runs/99999/patches", json={
        "op": "remove_line", "sku": "S", "reason": "r"}).status_code == 404


def test_patch_never_touches_overrides(app, client, run_id):
    client.post(f"/api/v1/bom-runs/{run_id}/patches", json={
        "op": "update_line", "sku": "SKU-1",
        "fields": {"quantity": 12}, "reason": "count fix",
    })
    with app.app_context():
        assert ContractorOverride.query.count() == 0


def test_rule_candidate_event(app, client, run_id):
    client.post(f"/api/v1/bom-runs/{run_id}/patches", json={
        "op": "update_line", "sku": "SKU-1",
        "fields": {"quantity": 12},
        "reason": "boots are ALWAYS runs+1 for this builder",
        "rule_candidate": True,
    }, headers={"X-Procalcs-User-Email": "rich@reliable.com"})
    with app.app_context():
        events = {e.event for e in UsageEvent.query.all()}
        assert "patch_applied" in events
        assert "rule_candidate" in events
        rc = UsageEvent.query.filter_by(event="rule_candidate").one()
        assert "ALWAYS" in rc.detail["reason"]
