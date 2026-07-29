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


# ─── Day-26 — regenerate dispatches wrightsoft runs correctly ──────

def test_regenerate_wrightsoft_run_uses_wrightsoft_builder(app, client, monkeypatch):
    """A run whose parsed_design_data carries wrightsoft_lines must
    re-run through build_bom_from_wrightsoft_lines (which re-applies
    contractor overrides), NOT bom_service.generate — the AI path
    produced junk (9 null-sku lines) when fed wrightsoft data."""
    import services.profile_service as ps

    profile = {
        "client_id": "test-contractor", "client_name": "Test", "is_active": True,
        "supplier": {"supplier_name": "S"},
        "markup": {"equipment_pct": 15, "materials_pct": 25,
                   "consumables_pct": 30, "labor_pct": 0},
        "markup_tiers": [], "brands": {}, "part_name_overrides": [],
        "default_output_mode": "full", "include_labor": False, "notes": "",
    }
    monkeypatch.setattr(ps, "get_profile_by_id", lambda cid: profile)

    with app.app_context():
        parent = BomRun.record(
            client_id="test-contractor", job_id="ws-job", output_mode="full",
            parsed_design_data={
                "source_pipeline": "wrightsoft_bom",
                "wrightsoft_lines": [
                    {"generic_id": "10-00-190", "quantity": 5,
                     "description": "3-in Duct Uninsulated", "src": "Rheia"},
                ],
            },
            generated_bom={"line_items": [{"sku": "10-00-190", "quantity": 5}]},
        )
        db.session.commit()
        parent_id = parent.id

    resp = client.post(f"/api/v1/bom-runs/{parent_id}/regenerate", json={})
    assert resp.status_code == 200, resp.get_json()
    bom = resp.get_json()["data"]
    skus = [(li.get("sku") or li.get("generic_id")) for li in bom["line_items"]]
    # The wrightsoft builder echoes real part ids — never null skus.
    assert "10-00-190" in skus
    assert all(s for s in skus)
    with app.app_context():
        child = BomRun.query.get(bom["run_id"])
        assert child.regenerated_from_id == parent_id


# ─── Day-29 — regenerate carries applied corrections forward ───────

def test_regenerate_carries_patch_ops_to_child(app, client, monkeypatch):
    """Tim (Randolph Cabin) built a 26-op grille reconciliation, hit
    regenerate, and lost every correction — twice. Corrections must
    carry into the regenerated run and ride the response."""
    import services.profile_service as ps
    profile = {
        "client_id": "test-contractor", "client_name": "Test", "is_active": True,
        "supplier": {"supplier_name": "S"},
        "markup": {"equipment_pct": 15, "materials_pct": 25,
                   "consumables_pct": 30, "labor_pct": 0},
        "markup_tiers": [], "brands": {}, "part_name_overrides": [],
        "default_output_mode": "full", "include_labor": False, "notes": "",
    }
    monkeypatch.setattr(ps, "get_profile_by_id", lambda cid: profile)

    with app.app_context():
        parent = BomRun.record(
            client_id="test-contractor", job_id="ws-job", output_mode="full",
            parsed_design_data={
                "source_pipeline": "wrightsoft_bom",
                "wrightsoft_lines": [
                    {"generic_id": "FRGRMFT-1212", "quantity": 29,
                     "description": "Rect metal floor grille 12x12", "src": "WSF"},
                ],
            },
            generated_bom={"line_items": [{"sku": "FRGRMFT-1212", "quantity": 29}]},
        )
        db.session.commit()
        parent_id = parent.id

    # apply an expert correction to the parent
    client.post(f"/api/v1/bom-runs/{parent_id}/patches", json={
        "op": "update_line", "sku": "FRGRMFT-1212",
        "fields": {"quantity": 4}, "reason": "M Sheets show 4, not 29",
    }, headers={"X-Procalcs-User-Email": "tim@reliableheating.team"})

    resp = client.post(f"/api/v1/bom-runs/{parent_id}/regenerate", json={})
    assert resp.status_code == 200, resp.get_json()
    bom = resp.get_json()["data"]
    # response carries the ops for immediate client-side replay
    assert any(o["sku"] == "FRGRMFT-1212" for o in bom.get("patch_ops", [])), \
        "regenerate response must carry parent's corrections"
    # child run persists them
    with app.app_context():
        child = BomRun.query.get(bom["run_id"])
        assert child.patch_ops and child.patch_ops[0]["fields"] == {"quantity": 4}
