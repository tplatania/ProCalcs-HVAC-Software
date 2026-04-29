"""
Tests for services.sku_catalog and routes.sku_catalog_routes.

Service tests patch ``sku_catalog._get_db`` to return a fake Firestore
client and assert the read/write helpers do the right thing.

Route tests spin up a minimal Flask app with just the SKU blueprint
mounted (skipping the production middleware) so we can exercise the
HTTP surface without needing real config/secrets.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from services import sku_catalog
from services.sku_catalog import CatalogError
from routes.sku_catalog_routes import sku_catalog_bp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _doc_mock(exists: bool, data: dict | None = None):
    """Build a fake Firestore DocumentSnapshot."""
    snap = MagicMock()
    snap.exists = exists
    snap.to_dict.return_value = data
    return snap


@pytest.fixture
def fake_db():
    """A MagicMock standing in for firestore.Client(). Tests configure
    behavior per-call via .collection().document() / .stream() chains."""
    db = MagicMock()
    return db


@pytest.fixture
def reset_catalog_state():
    """Drop the in-memory cache before and after each test."""
    sku_catalog.reload()
    yield
    sku_catalog.reload()


@pytest.fixture
def app():
    """Minimal Flask app with the SKU blueprint mounted under
    /api/v1/sku-catalog. No auth middleware — the production app
    layers that on separately and we test it elsewhere."""
    app = Flask(__name__)
    app.register_blueprint(sku_catalog_bp, url_prefix='/api/v1/sku-catalog')
    app.testing = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# A valid-looking item we can clone in many tests.
def sample_item(**overrides):
    base = {
        "sku": "TEST-1",
        "supplier": "GOODMAN",
        "section": "Equipment",
        "phase": None,
        "description": "Test equipment",
        "trigger": "ahu_present",
        "quantity": {"mode": "per_unit", "source": "equipment.ahu"},
        "default_unit_price": 100.0,
        "notes": "",
        "disabled": False,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# validate_item
# ---------------------------------------------------------------------------

class TestValidateItem:
    def test_minimal_valid(self):
        out = sku_catalog.validate_item(sample_item())
        assert out["sku"] == "TEST-1"
        assert out["disabled"] is False

    def test_missing_sku_when_required(self):
        with pytest.raises(CatalogError) as ei:
            sku_catalog.validate_item(sample_item(sku=""))
        assert ei.value.status_code == 400
        assert "sku" in str(ei.value)

    def test_invalid_section(self):
        with pytest.raises(CatalogError) as ei:
            sku_catalog.validate_item(sample_item(section="Bogus Section"))
        assert "section" in str(ei.value)

    def test_invalid_trigger(self):
        with pytest.raises(CatalogError):
            sku_catalog.validate_item(sample_item(trigger="not_a_trigger"))

    def test_invalid_quantity_mode(self):
        with pytest.raises(CatalogError):
            sku_catalog.validate_item(
                sample_item(quantity={"mode": "made_up"})
            )

    def test_quantity_must_be_dict(self):
        with pytest.raises(CatalogError):
            sku_catalog.validate_item(sample_item(quantity=None))

    def test_invalid_phase(self):
        with pytest.raises(CatalogError):
            sku_catalog.validate_item(sample_item(phase="Mid"))

    def test_phase_none_is_ok(self):
        sku_catalog.validate_item(sample_item(phase=None))

    def test_default_unit_price_coerces(self):
        out = sku_catalog.validate_item(sample_item(default_unit_price="42.5"))
        assert out["default_unit_price"] == 42.5

    def test_default_unit_price_rejects_non_numeric(self):
        with pytest.raises(CatalogError):
            sku_catalog.validate_item(sample_item(default_unit_price="not-a-number"))


# ---------------------------------------------------------------------------
# Service layer — create / update / delete / disable
# ---------------------------------------------------------------------------

class TestServiceCreate:
    def test_happy_path(self, fake_db, reset_catalog_state):
        # doc doesn't exist yet → set + log
        fake_db.collection.return_value.document.return_value.get.return_value = _doc_mock(False)
        with patch.object(sku_catalog, "_get_db", return_value=fake_db):
            out = sku_catalog.create_item(sample_item(), actor_email="richard@procalcs.net")
        assert out["sku"] == "TEST-1"
        fake_db.collection.return_value.document.return_value.set.assert_called_once()
        # Persisted record carries audit metadata
        record = fake_db.collection.return_value.document.return_value.set.call_args[0][0]
        assert record["created_by"] == "richard@procalcs.net"
        assert record["updated_by"] == "richard@procalcs.net"

    def test_conflict_when_exists(self, fake_db, reset_catalog_state):
        fake_db.collection.return_value.document.return_value.get.return_value = _doc_mock(
            True, sample_item()
        )
        with patch.object(sku_catalog, "_get_db", return_value=fake_db):
            with pytest.raises(CatalogError) as ei:
                sku_catalog.create_item(sample_item())
        assert ei.value.status_code == 409

    def test_validates_payload(self, fake_db, reset_catalog_state):
        with patch.object(sku_catalog, "_get_db", return_value=fake_db):
            with pytest.raises(CatalogError) as ei:
                sku_catalog.create_item(sample_item(section="Bogus"))
        assert ei.value.status_code == 400

    def test_db_unavailable_raises_503(self, reset_catalog_state):
        with patch.object(sku_catalog, "_get_db", return_value=None):
            with pytest.raises(CatalogError) as ei:
                sku_catalog.create_item(sample_item())
        assert ei.value.status_code == 503


class TestServiceUpdate:
    def test_partial_update_merges_existing(self, fake_db, reset_catalog_state):
        existing = sample_item(notes="old", default_unit_price=10.0)
        fake_db.collection.return_value.document.return_value.get.return_value = _doc_mock(
            True, existing
        )
        with patch.object(sku_catalog, "_get_db", return_value=fake_db):
            out = sku_catalog.update_item("TEST-1", {"notes": "fresh"}, actor_email="rich@x")
        assert out["notes"] == "fresh"
        # Other fields from existing are preserved
        assert out["default_unit_price"] == 10.0
        record = fake_db.collection.return_value.document.return_value.set.call_args[0][0]
        assert record["updated_by"] == "rich@x"

    def test_404_when_missing(self, fake_db, reset_catalog_state):
        fake_db.collection.return_value.document.return_value.get.return_value = _doc_mock(False)
        with patch.object(sku_catalog, "_get_db", return_value=fake_db):
            with pytest.raises(CatalogError) as ei:
                sku_catalog.update_item("MISSING", {"notes": "x"})
        assert ei.value.status_code == 404


class TestServiceDelete:
    def test_happy_path(self, fake_db, reset_catalog_state):
        fake_db.collection.return_value.document.return_value.get.return_value = _doc_mock(
            True, sample_item()
        )
        with patch.object(sku_catalog, "_get_db", return_value=fake_db):
            sku_catalog.delete_item("TEST-1")
        fake_db.collection.return_value.document.return_value.delete.assert_called_once()

    def test_404(self, fake_db, reset_catalog_state):
        fake_db.collection.return_value.document.return_value.get.return_value = _doc_mock(False)
        with patch.object(sku_catalog, "_get_db", return_value=fake_db):
            with pytest.raises(CatalogError) as ei:
                sku_catalog.delete_item("MISSING")
        assert ei.value.status_code == 404


class TestServiceDisable:
    def test_toggle(self, fake_db, reset_catalog_state):
        existing = sample_item()
        # First .get() in set_disabled checks existence
        # Second .get() at the end re-reads to return fresh state
        fake_db.collection.return_value.document.return_value.get.side_effect = [
            _doc_mock(True, existing),
            _doc_mock(True, {**existing, "disabled": True}),
        ]
        with patch.object(sku_catalog, "_get_db", return_value=fake_db):
            out = sku_catalog.set_disabled("TEST-1", True, actor_email="rich@x")
        assert out["disabled"] is True
        fake_db.collection.return_value.document.return_value.update.assert_called_once()
        update_payload = fake_db.collection.return_value.document.return_value.update.call_args[0][0]
        assert update_payload["disabled"] is True
        assert update_payload["updated_by"] == "rich@x"


# ---------------------------------------------------------------------------
# Route surface
# ---------------------------------------------------------------------------

class TestListRoute:
    def test_list_returns_envelope(self, client):
        items = [sku_catalog.SKUItem.from_dict(sample_item(sku="A")),
                 sku_catalog.SKUItem.from_dict(sample_item(sku="B", supplier="PGM",
                                                            section="Duct System Equipment",
                                                            trigger="rectangular_duct",
                                                            quantity={"mode": "per_lf", "source": "duct_runs.rectangular"}))]
        with patch.object(sku_catalog, "all_items", return_value=items), \
             patch.object(sku_catalog, "source", return_value="firestore"):
            resp = client.get("/api/v1/sku-catalog/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert len(body["data"]) == 2
        assert body["meta"]["count"] == 2
        assert body["meta"]["source"] == "firestore"

    def test_filter_by_section(self, client):
        items = [
            sku_catalog.SKUItem.from_dict(sample_item(sku="A", section="Equipment")),
            sku_catalog.SKUItem.from_dict(sample_item(sku="B", section="Duct System Equipment",
                                                       trigger="rectangular_duct",
                                                       quantity={"mode": "per_lf", "source": "duct_runs.rectangular"})),
        ]
        with patch.object(sku_catalog, "all_items", return_value=items), \
             patch.object(sku_catalog, "source", return_value="firestore"):
            resp = client.get("/api/v1/sku-catalog/?section=Equipment")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["data"]) == 1
        assert body["data"][0]["sku"] == "A"


class TestGetRoute:
    def test_found(self, client):
        item = sku_catalog.SKUItem.from_dict(sample_item())
        with patch.object(sku_catalog, "get", return_value=item):
            resp = client.get("/api/v1/sku-catalog/TEST-1")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["sku"] == "TEST-1"

    def test_not_found(self, client):
        with patch.object(sku_catalog, "get", return_value=None):
            resp = client.get("/api/v1/sku-catalog/NOPE")
        assert resp.status_code == 404


class TestMetaRoute:
    def test_meta_returns_enums(self, client):
        with patch.object(sku_catalog, "all_items", return_value=[]):
            resp = client.get("/api/v1/sku-catalog/_meta")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "Equipment" in data["sections"]
        assert "rheia_in_scope" in data["triggers"]
        assert "rheia_per_endpoint" in data["quantity_modes"]


class TestCreateRoute:
    def test_201_on_success(self, client):
        with patch.object(sku_catalog, "create_item", return_value=sample_item()) as mc:
            resp = client.post("/api/v1/sku-catalog/", json=sample_item(),
                               headers={"X-Actor-Email": "richard@procalcs.net"})
        assert resp.status_code == 201
        # Actor email forwarded
        assert mc.call_args.kwargs["actor_email"] == "richard@procalcs.net"

    def test_409_on_conflict(self, client):
        with patch.object(sku_catalog, "create_item",
                           side_effect=CatalogError("already exists", status_code=409)):
            resp = client.post("/api/v1/sku-catalog/", json=sample_item())
        assert resp.status_code == 409

    def test_400_on_validation(self, client):
        with patch.object(sku_catalog, "create_item",
                           side_effect=CatalogError("bad section", status_code=400)):
            resp = client.post("/api/v1/sku-catalog/", json=sample_item())
        assert resp.status_code == 400


class TestUpdateRoute:
    def test_200_on_success(self, client):
        with patch.object(sku_catalog, "update_item", return_value=sample_item(notes="x")):
            resp = client.put("/api/v1/sku-catalog/TEST-1",
                              json={"notes": "x"})
        assert resp.status_code == 200

    def test_404(self, client):
        with patch.object(sku_catalog, "update_item",
                           side_effect=CatalogError("missing", status_code=404)):
            resp = client.put("/api/v1/sku-catalog/NOPE", json={})
        assert resp.status_code == 404


class TestDisableEnableRoutes:
    def test_disable(self, client):
        with patch.object(sku_catalog, "set_disabled",
                           return_value=sample_item(disabled=True)) as mc:
            resp = client.post("/api/v1/sku-catalog/TEST-1/disable")
        assert resp.status_code == 200
        assert mc.call_args.args[1] is True

    def test_enable(self, client):
        with patch.object(sku_catalog, "set_disabled",
                           return_value=sample_item(disabled=False)) as mc:
            resp = client.post("/api/v1/sku-catalog/TEST-1/enable")
        assert resp.status_code == 200
        assert mc.call_args.args[1] is False


class TestDeleteRoute:
    def test_204_on_success(self, client):
        with patch.object(sku_catalog, "delete_item"):
            resp = client.delete("/api/v1/sku-catalog/TEST-1")
        assert resp.status_code == 204

    def test_404(self, client):
        with patch.object(sku_catalog, "delete_item",
                           side_effect=CatalogError("missing", status_code=404)):
            resp = client.delete("/api/v1/sku-catalog/NOPE")
        assert resp.status_code == 404
