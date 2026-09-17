"""
Service-auth fail-closed tests (security hardening).

Previously an empty SERVICE_SHARED_SECRET let every request through.
Now an unconfigured secret DENIES by default (503); local dev opts out
with ALLOW_INSECURE_NO_AUTH=1.

The middleware reads app.config['SERVICE_SHARED_SECRET'] and
ALLOW_INSECURE_NO_AUTH at REQUEST time, so we build ONE app and just
vary those per test — no module reload (which would pollute other
tests' app/db state).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "dev-test")
os.environ.setdefault("FIRESTORE_PROJECT_ID", "dev-test")
os.environ.setdefault("INTERNAL_DOMAIN", "procalcs.net")
os.environ.setdefault("SERVICE_SHARED_SECRET", "")

if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:  # noqa: BLE001
        _w = MagicMock(); _w.HTML = MagicMock(); _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w

from app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def _clean_env():
    # Start each test with fail-closed as the default (opt-out removed),
    # then RESTORE the prior value so we don't disturb other test
    # modules (conftest sets ALLOW_INSECURE_NO_AUTH=1 suite-wide).
    prev = os.environ.get("ALLOW_INSECURE_NO_AUTH")
    os.environ.pop("ALLOW_INSECURE_NO_AUTH", None)
    yield
    if prev is None:
        os.environ.pop("ALLOW_INSECURE_NO_AUTH", None)
    else:
        os.environ["ALLOW_INSECURE_NO_AUTH"] = prev


def _set_secret(client, secret: str):
    # test_client → app config is shared via the app; set on the app.
    client.application.config["SERVICE_SHARED_SECRET"] = secret


def test_empty_secret_fails_closed(client):
    _set_secret(client, "")
    r = client.get("/api/v1/profiles/")
    assert r.status_code == 503, r.data


def test_empty_secret_dev_optout_allows(client):
    _set_secret(client, "")
    os.environ["ALLOW_INSECURE_NO_AUTH"] = "1"
    r = client.get("/api/v1/profiles/")
    assert r.status_code != 503, r.data


def test_wrong_token_denied(client):
    _set_secret(client, "realsecret")
    r = client.get("/api/v1/profiles/", headers={"X-Procalcs-Service-Token": "nope"})
    assert r.status_code == 401, r.data


def test_correct_token_passes_gate(client):
    _set_secret(client, "realsecret")
    r = client.get("/api/v1/profiles/",
                   headers={"X-Procalcs-Service-Token": "realsecret"})
    assert r.status_code != 401, r.data


def teardown_module(_m):
    os.environ["SERVICE_SHARED_SECRET"] = ""
