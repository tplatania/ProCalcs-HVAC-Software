"""External users are restricted to their configured contractor data."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:  # noqa: BLE001
        stub = MagicMock(); stub.HTML = MagicMock(); stub.CSS = MagicMock()
        sys.modules["weasyprint"] = stub

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "dev-test")
os.environ.setdefault("FIRESTORE_PROJECT_ID", "dev-test")

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import BomRun  # noqa: E402


@pytest.fixture
def app():
    app = create_app()
    app.config.update(
        TESTING=True,
        SERVICE_SHARED_SECRET="test-service-secret",
        INTERNAL_DOMAIN="procalcs.net",
        CLIENT_SCOPE_RULES={
            "reliableheating.team": ["reliable-heating-and-cooling"],
        },
    )
    with app.app_context():
        db.create_all()
        reliable = BomRun.record(
            client_id="reliable-heating-and-cooling", job_id="reliable-job",
            output_mode="full", parsed_design_data={}, generated_bom={"items": []},
        )
        other = BomRun.record(
            client_id="other-contractor", job_id="other-job",
            output_mode="full", parsed_design_data={}, generated_bom={"items": []},
        )
        db.session.commit()
        app.config["RELIABLE_RUN_ID"] = reliable.id
        app.config["OTHER_RUN_ID"] = other.id
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _headers(email: str) -> dict[str, str]:
    return {
        "X-Procalcs-Service-Token": "test-service-secret",
        "X-Procalcs-User-Email": email,
    }


def test_reliable_user_lists_only_reliable_runs(app, client):
    response = client.get("/api/v1/bom-runs/", headers=_headers("richard@reliableheating.team"))
    assert response.status_code == 200
    runs = response.get_json()["data"]["runs"]
    assert [run["job_id"] for run in runs] == ["reliable-job"]


def test_reliable_user_cannot_open_other_run(app, client):
    response = client.get(
        f"/api/v1/bom-runs/{app.config['OTHER_RUN_ID']}",
        headers=_headers("richard@reliableheating.team"),
    )
    assert response.status_code == 404


def test_reliable_user_cannot_spoof_client_filter(client):
    response = client.get(
        "/api/v1/bom-runs/?client_id=other-contractor",
        headers=_headers("richard@reliableheating.team"),
    )
    assert response.status_code == 403


def test_unmapped_external_user_has_no_client_access(client):
    response = client.get("/api/v1/bom-runs/", headers=_headers("person@example.com"))
    assert response.status_code == 200
    assert response.get_json()["data"]["runs"] == []


def test_internal_user_can_list_all_runs(client):
    response = client.get("/api/v1/bom-runs/", headers=_headers("gerald@procalcs.net"))
    assert response.status_code == 200
    assert response.get_json()["data"]["total"] == 2


def test_missing_user_identity_has_no_client_access(client):
    response = client.get(
        "/api/v1/bom-runs/",
        headers={"X-Procalcs-Service-Token": "test-service-secret"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["runs"] == []


def test_reliable_user_cannot_generate_for_other_client(client):
    response = client.post(
        "/api/v1/bom/generate",
        headers=_headers("richard@reliableheating.team"),
        json={
            "client_id": "other-contractor",
            "job_id": "spoofed-job",
            "design_data": {"building": {}, "equipment": []},
        },
    )
    assert response.status_code == 403


def test_reliable_user_cannot_read_other_profile(client):
    response = client.get(
        "/api/v1/profiles/other-contractor",
        headers=_headers("richard@reliableheating.team"),
    )
    assert response.status_code == 403


def test_reliable_user_cannot_write_other_overrides(client):
    response = client.post(
        "/api/v1/contractor-overrides",
        headers=_headers("richard@reliableheating.team"),
        json={
            "client_id": "other-contractor",
            "supplier": "GOOD",
            "sku": "X1",
            "unit_price": 10,
        },
    )
    assert response.status_code == 403
