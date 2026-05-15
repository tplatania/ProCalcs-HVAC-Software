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


# ---------------------------------------------------------------------------
# Phase 3.5 schema bump (May 2026) — additive fields
# ---------------------------------------------------------------------------
#
# Five new optional fields added to SKUItem so the catalog can carry the
# data needed for catalog-augmented BOM generation: wrightsoft_codes
# (bridge into Wrightsoft generic_parts.csv), capacity_btu and
# capacity_min/max_btu (equipment sizing tolerance band), manufacturer
# (display name separate from 4-char supplier code), contractor_id
# (per-contractor scoping).
#
# Goal of these tests: prove the bump is fully additive — every existing
# payload shape still validates, every old-shape SKU still loads, and
# the new fields default to sensible empty values.


class TestSchemaBumpRoundTrip:
    """Existing 21 starter SKUs and old-shape payloads must still work."""

    def test_old_shape_payload_validates_clean(self):
        """A payload missing every Phase-3.5 field must still pass
        validation and return defaulted values for the new keys."""
        old = {
            "sku":                "OLD-SHAPE",
            "supplier":           "WSF",
            "section":            "Equipment",
            "phase":              None,
            "description":        "Pre-3.5 SKU",
            "trigger":            "always",
            "quantity":           {"mode": "fixed", "value": 1},
            "default_unit_price": 0,
        }
        clean = sku_catalog.validate_item(old)
        assert clean["wrightsoft_codes"] == []
        assert clean["capacity_btu"] is None
        assert clean["capacity_min_btu"] is None
        assert clean["capacity_max_btu"] is None
        assert clean["manufacturer"] is None
        assert clean["contractor_id"] is None

    def test_old_shape_round_trips_through_dataclass(self):
        old = {
            "sku":                "OLD-SHAPE-2",
            "supplier":           "WSF",
            "section":            "Equipment",
            "phase":              None,
            "description":        "Pre-3.5 SKU 2",
            "trigger":            "always",
            "quantity":           {"mode": "fixed", "value": 1},
            "default_unit_price": 0,
        }
        clean = sku_catalog.validate_item(old)
        item = sku_catalog.SKUItem.from_dict(clean)
        assert item.wrightsoft_codes == ()  # tuple, not list, because dataclass is frozen+hashable
        assert item.capacity_btu is None
        # Round-trip back to dict and confirm shape
        out = item.to_dict()
        assert out["wrightsoft_codes"] == []
        assert out["capacity_btu"] is None


class TestNewShapeValidation:
    """Phase-3.5 payloads carry the new fields and validate correctly."""

    def _goodman_ahu(self, **overrides):
        base = {
            "sku":                "GOOD-AHU-24K",
            "supplier":           "GOOD",
            "section":            "Equipment",
            "phase":              None,
            "description":        "Goodman AHU AHVE24BP1300A",
            "trigger":            "ahu_present",
            "quantity":           {"mode": "per_unit"},
            "default_unit_price": 1850.0,
            "wrightsoft_codes":   ["AHVE24BP1300A"],
            "capacity_btu":       24000,
            "capacity_min_btu":   22000,
            "capacity_max_btu":   26000,
            "manufacturer":       "Goodman",
            "contractor_id":      None,
        }
        base.update(overrides)
        return base

    def test_full_new_shape_validates_and_round_trips(self):
        clean = sku_catalog.validate_item(self._goodman_ahu())
        item = sku_catalog.SKUItem.from_dict(clean)
        assert item.wrightsoft_codes == ("AHVE24BP1300A",)
        assert item.capacity_btu == 24000
        assert item.capacity_min_btu == 22000
        assert item.capacity_max_btu == 26000
        assert item.manufacturer == "Goodman"

    def test_string_wrightsoft_code_coerced_to_list(self):
        """Form inputs and CSV cells often deliver a single string, not a
        list. The validator should tolerate that and wrap it."""
        clean = sku_catalog.validate_item(
            self._goodman_ahu(wrightsoft_codes="AHVE24BP1300A")
        )
        assert clean["wrightsoft_codes"] == ["AHVE24BP1300A"]

    def test_blank_strings_in_codes_dropped(self):
        clean = sku_catalog.validate_item(
            self._goodman_ahu(wrightsoft_codes=["A", "", "B", " "])
        )
        assert clean["wrightsoft_codes"] == ["A", "B"]

    def test_capacity_min_without_max_rejected(self):
        with pytest.raises(CatalogError) as exc_info:
            sku_catalog.validate_item(
                self._goodman_ahu(capacity_min_btu=22000, capacity_max_btu=None)
            )
        assert "must be set together" in str(exc_info.value)

    def test_capacity_max_without_min_rejected(self):
        with pytest.raises(CatalogError) as exc_info:
            sku_catalog.validate_item(
                self._goodman_ahu(capacity_min_btu=None, capacity_max_btu=26000)
            )
        assert "must be set together" in str(exc_info.value)

    def test_capacity_min_greater_than_max_rejected(self):
        with pytest.raises(CatalogError) as exc_info:
            sku_catalog.validate_item(
                self._goodman_ahu(capacity_min_btu=30000, capacity_max_btu=25000)
            )
        assert "must be <=" in str(exc_info.value)

    def test_capacity_btu_outside_band_rejected(self):
        with pytest.raises(CatalogError) as exc_info:
            sku_catalog.validate_item(
                self._goodman_ahu(capacity_btu=30000, capacity_min_btu=22000, capacity_max_btu=25000)
            )
        assert "must lie within" in str(exc_info.value)

    def test_capacity_string_input_coerced_to_int(self):
        """JSON forms sometimes deliver numbers as strings."""
        clean = sku_catalog.validate_item(
            self._goodman_ahu(capacity_btu="24000", capacity_min_btu="22000", capacity_max_btu="26000.0")
        )
        assert clean["capacity_btu"] == 24000
        assert clean["capacity_min_btu"] == 22000
        assert clean["capacity_max_btu"] == 26000

    def test_manufacturer_and_contractor_id_blank_normalized_to_none(self):
        clean = sku_catalog.validate_item(
            self._goodman_ahu(manufacturer="  ", contractor_id="")
        )
        assert clean["manufacturer"] is None
        assert clean["contractor_id"] is None


# ---------------------------------------------------------------------------
# Phase 3.6 bulk-import endpoint (May 2026)
# ---------------------------------------------------------------------------
#
# POST /api/v1/sku-catalog/bulk-import accepts {"items": [...]} and
# does idempotent upsert. Per-row failures isolated; whole batch
# reported in summary.

class TestBulkUpsertService:
    """Unit tests for sku_catalog.bulk_upsert (no Flask)."""

    def _payload(self, sku_id: str, **overrides):
        base = {
            "sku":                sku_id,
            "supplier":           "WSF",
            "section":            "Equipment",
            "phase":              None,
            "description":        f"Test SKU {sku_id}",
            "trigger":            "always",
            "quantity":           {"mode": "fixed", "value": 1},
            "default_unit_price": 0,
        }
        base.update(overrides)
        return base

    def test_creates_when_no_existing(self, fake_db):
        # Every doc.get() returns "not exists" so all rows are creates.
        snap = MagicMock(); snap.exists = False
        fake_db.collection.return_value.document.return_value.get.return_value = snap

        with patch.object(sku_catalog, "_get_db", return_value=fake_db), \
             patch.object(sku_catalog, "reload"):
            summary = sku_catalog.bulk_upsert(
                [self._payload("A"), self._payload("B"), self._payload("C")],
                actor_email="tester@example.com",
            )
        assert summary["created"] == 3
        assert summary["updated"] == 0
        assert summary["skipped"] == 0
        assert summary["errors"] == []

    def test_updates_when_existing(self, fake_db):
        # Every doc.get() returns "exists" so all rows are updates.
        snap = _doc_mock(exists=True, data={"sku": "X", "created_at": "old"})
        fake_db.collection.return_value.document.return_value.get.return_value = snap

        with patch.object(sku_catalog, "_get_db", return_value=fake_db), \
             patch.object(sku_catalog, "reload"):
            summary = sku_catalog.bulk_upsert(
                [self._payload("X")],
                actor_email="tester@example.com",
            )
        assert summary["created"] == 0
        assert summary["updated"] == 1

    def test_isolates_per_row_failure(self, fake_db):
        snap = MagicMock(); snap.exists = False
        fake_db.collection.return_value.document.return_value.get.return_value = snap

        rows = [
            self._payload("GOOD-1"),
            {"sku": "BAD", "supplier": ""},   # missing required fields
            self._payload("GOOD-2"),
            "not even a dict",                 # totally invalid
            self._payload("GOOD-3"),
        ]
        with patch.object(sku_catalog, "_get_db", return_value=fake_db), \
             patch.object(sku_catalog, "reload"):
            summary = sku_catalog.bulk_upsert(rows, actor_email="tester@example.com")
        assert summary["created"] == 3
        assert summary["skipped"] == 2
        assert {e["index"] for e in summary["errors"]} == {1, 3}

    def test_non_list_payload_raises(self):
        with pytest.raises(CatalogError) as exc_info:
            sku_catalog.bulk_upsert({"items": "not a list"})
        assert exc_info.value.status_code == 400


class TestBulkImportRoute:
    """HTTP-level tests for POST /api/v1/sku-catalog/bulk-import."""

    @pytest.fixture
    def client(self):
        app = Flask(__name__)
        app.register_blueprint(sku_catalog_bp, url_prefix='/api/v1/sku-catalog')
        return app.test_client()

    def test_200_on_success(self, client, fake_db):
        snap = MagicMock(); snap.exists = False
        fake_db.collection.return_value.document.return_value.get.return_value = snap

        body = {
            "items": [
                {
                    "sku":                "BULK-1",
                    "supplier":           "WSF",
                    "section":            "Equipment",
                    "phase":              None,
                    "description":        "Bulk row 1",
                    "trigger":            "always",
                    "quantity":           {"mode": "fixed", "value": 1},
                    "default_unit_price": 0,
                },
            ],
        }
        with patch.object(sku_catalog, "_get_db", return_value=fake_db), \
             patch.object(sku_catalog, "reload"):
            resp = client.post(
                "/api/v1/sku-catalog/bulk-import",
                json=body,
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["created"] == 1
        assert data["data"]["updated"] == 0
        assert data["data"]["skipped"] == 0

    def test_400_on_non_list_items(self, client):
        resp = client.post("/api/v1/sku-catalog/bulk-import", json={"items": "not-a-list"})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_400_on_missing_items_key(self, client):
        resp = client.post("/api/v1/sku-catalog/bulk-import", json={})
        assert resp.status_code == 400

    def test_idempotency_re_import_yields_zero_created(self, client, fake_db):
        """First call: doc not exists → created.
        Second call (same SKU): doc exists → updated."""
        snap_missing = MagicMock(); snap_missing.exists = False
        snap_exists  = _doc_mock(exists=True, data={"sku": "IDEM", "created_at": "first"})

        # First import — creates
        fake_db.collection.return_value.document.return_value.get.return_value = snap_missing
        body = {
            "items": [{
                "sku":                "IDEM",
                "supplier":           "WSF",
                "section":            "Equipment",
                "phase":              None,
                "description":        "Idempotent SKU",
                "trigger":            "always",
                "quantity":           {"mode": "fixed", "value": 1},
                "default_unit_price": 0,
            }],
        }
        with patch.object(sku_catalog, "_get_db", return_value=fake_db), \
             patch.object(sku_catalog, "reload"):
            r1 = client.post("/api/v1/sku-catalog/bulk-import", json=body)
        assert r1.get_json()["data"]["created"] == 1

        # Second import — updates
        fake_db.collection.return_value.document.return_value.get.return_value = snap_exists
        with patch.object(sku_catalog, "_get_db", return_value=fake_db), \
             patch.object(sku_catalog, "reload"):
            r2 = client.post("/api/v1/sku-catalog/bulk-import", json=body)
        d2 = r2.get_json()["data"]
        assert d2["created"] == 0
        assert d2["updated"] == 1
