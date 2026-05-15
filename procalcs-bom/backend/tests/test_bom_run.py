"""
Phase 3 (May 2026) — tests for the bom_runs persistence layer.

Covers:
  - BomRun.record creates a row with full payload
  - BomRun.review sets status + notes + reviewer email + reviewed_at
  - REVIEWER_STATUSES enforcement (raises on unknown status)
  - to_summary drops heavy JSONB columns; to_dict keeps them
  - bom_service.generate persists every run (storage hook)
  - DB failure inside _record_bom_run does NOT fail BOM generation
  - generate populates parsed_design_data + generated_bom + client_id

Tests use the in-memory SQLite path with create_all() rather than
Alembic migrations — same pattern as test_billing.py — so they run
without needing a Postgres or even a file on disk.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Force in-memory SQLite + dummy required env BEFORE importing the app.
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('ANTHROPIC_API_KEY', 'dev-test')
os.environ.setdefault('FIRESTORE_PROJECT_ID', 'dev-test')
os.environ.setdefault('SERVICE_SHARED_SECRET', '')

from app import create_app
from extensions import db
from models import BomRun
from models.bom_run import REVIEWER_STATUSES
from services import bom_service, sku_catalog
from models.client_profile import ClientProfile


# ─── Fixtures ───────────────────────────────────────────────────────

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
def profile_dict():
    return {
        "client_id": "test-contractor", "client_name": "Test", "is_active": True,
        "supplier": {"supplier_name": "S"},
        "markup": {"equipment_pct": 15, "materials_pct": 25,
                   "consumables_pct": 30, "labor_pct": 0},
        "markup_tiers": [], "brands": {}, "part_name_overrides": [],
        "default_output_mode": "full", "include_labor": False, "notes": "",
    }


@pytest.fixture
def design_data():
    return {
        "project":  {"name": "Test ADU"},
        "building": {"type": "single_level", "duct_location": "attic"},
        "equipment": [{"name": "AHU-1", "type": "air_handler", "tonnage": 2.0}],
        "rooms": [], "duct_runs": [], "fittings": [], "registers": [],
        "raw_rup_context": "",
    }


# ─── BomRun.record ──────────────────────────────────────────────────

class TestBomRunRecord:
    def test_creates_row_with_required_fields(self, app):
        run = BomRun.record(
            client_id="test-contractor",
            job_id="job-1",
            output_mode="full",
            parsed_design_data={"equipment": []},
            generated_bom={"item_count": 0},
        )
        db.session.commit()
        assert run.id is not None
        assert run.client_id == "test-contractor"
        assert run.job_id == "job-1"
        assert run.output_mode == "full"
        assert run.reviewer_status == "unset"
        assert run.tags == []

    def test_persists_full_payload_jsonb(self, app):
        full_design = {"equipment": [{"name": "A", "type": "air_handler"}]}
        full_bom = {"item_count": 5, "totals": {"total_cost": 100, "total_price": 120}}
        run = BomRun.record(
            client_id="x", job_id="y", output_mode="full",
            parsed_design_data=full_design,
            generated_bom=full_bom,
            created_by_email="tester@procalcs.net",
            anthropic_duration_ms=12345,
            anthropic_input_tokens=1000,
            anthropic_output_tokens=500,
            bom_service_revision="abc1234",
        )
        db.session.commit()
        # Round-trip through DB
        fresh = BomRun.query.get(run.id)
        assert fresh.parsed_design_data == full_design
        assert fresh.generated_bom == full_bom
        assert fresh.created_by_email == "tester@procalcs.net"
        assert fresh.anthropic_duration_ms == 12345
        assert fresh.bom_service_revision == "abc1234"

    def test_record_flushes_so_id_is_available_pre_commit(self, app):
        """Phase 4 endpoints will return the run_id in the response.
        record() must populate id before the route layer commits."""
        run = BomRun.record(
            client_id="x", job_id="y", output_mode="full",
            parsed_design_data={}, generated_bom={},
        )
        # No commit yet
        assert run.id is not None


# ─── BomRun.review ──────────────────────────────────────────────────

class TestBomRunReview:
    def _new_run(self):
        return BomRun.record(
            client_id="x", job_id="y", output_mode="full",
            parsed_design_data={}, generated_bom={},
        )

    def test_sets_status_notes_email_and_timestamp(self, app):
        run = self._new_run()
        before = datetime.utcnow()
        run.review(status="good", notes="Looks right", email="richard@procalcs.net")
        db.session.commit()
        assert run.reviewer_status == "good"
        assert run.reviewer_notes == "Looks right"
        assert run.reviewer_email == "richard@procalcs.net"
        assert run.reviewed_at is not None
        assert run.reviewed_at >= before

    def test_rejects_unknown_status(self, app):
        run = self._new_run()
        with pytest.raises(ValueError) as exc_info:
            run.review(status="mystery")
        assert "must be one of" in str(exc_info.value)

    def test_each_canonical_status_accepted(self, app):
        for status in REVIEWER_STATUSES:
            run = self._new_run()
            run.review(status=status)
            assert run.reviewer_status == status

    def test_review_can_re_set_status(self, app):
        """Designer changes mind: marks needs_fix, then later good."""
        run = self._new_run()
        run.review(status="needs_fix", notes="hangers wrong")
        db.session.commit()
        run.review(status="good", notes="hangers fixed")
        db.session.commit()
        assert run.reviewer_status == "good"
        assert run.reviewer_notes == "hangers fixed"

    def test_review_with_only_status_does_not_clear_notes(self, app):
        """Re-flipping status without passing notes should preserve them."""
        run = self._new_run()
        run.review(status="needs_fix", notes="hangers wrong")
        db.session.commit()
        run.review(status="blocked")  # no notes arg
        db.session.commit()
        assert run.reviewer_notes == "hangers wrong"


# ─── Serialization shape ────────────────────────────────────────────

class TestBomRunSerialization:
    def test_summary_drops_heavy_jsonb(self, app):
        run = BomRun.record(
            client_id="x", job_id="y", output_mode="full",
            parsed_design_data={"big": "x" * 1000},
            generated_bom={"big": "y" * 1000, "item_count": 5,
                           "totals": {"total_price": 99.5}},
        )
        db.session.commit()
        s = run.to_summary()
        assert "parsed_design_data" not in s
        assert "generated_bom" not in s
        assert s["item_count"] == 5
        assert s["total_price"] == 99.5
        assert s["reviewer_status"] == "unset"

    def test_to_dict_includes_jsonb(self, app):
        run = BomRun.record(
            client_id="x", job_id="y", output_mode="full",
            parsed_design_data={"a": 1},
            generated_bom={"b": 2},
        )
        db.session.commit()
        d = run.to_dict()
        assert d["parsed_design_data"] == {"a": 1}
        assert d["generated_bom"] == {"b": 2}


# ─── bom_service storage hook ────────────────────────────────────────

class TestBomServicePersistence:
    def _patches(self, profile_dict):
        return [
            patch("services.bom_service.get_profile_by_id", return_value=profile_dict),
            patch("services.bom_service._call_ai_for_quantities",
                  return_value={"drawn_items": [], "consumables": []}),
            patch.object(sku_catalog, "all_items", return_value=[]),
        ]

    def test_generate_persists_run(self, app, profile_dict, design_data):
        for p in self._patches(profile_dict):
            p.start()
        try:
            bom_service.generate("test-contractor", "test-job", design_data)
        finally:
            for p in self._patches(profile_dict):
                try: p.stop()
                except Exception: pass
            patch.stopall()

        runs = BomRun.query.all()
        assert len(runs) == 1
        r = runs[0]
        assert r.client_id == "test-contractor"
        assert r.job_id == "test-job"
        assert r.output_mode == "full"
        assert r.parsed_design_data is not None
        assert r.generated_bom is not None

    def test_generate_persists_each_call(self, app, profile_dict, design_data):
        """Three generates → three rows. Sanity check the hook isn't
        accidentally idempotent (it should ALWAYS append, never upsert)."""
        with patch("services.bom_service.get_profile_by_id", return_value=profile_dict), \
             patch("services.bom_service._call_ai_for_quantities",
                   return_value={"drawn_items": [], "consumables": []}), \
             patch.object(sku_catalog, "all_items", return_value=[]):
            bom_service.generate("x", "j1", design_data)
            bom_service.generate("x", "j2", design_data)
            bom_service.generate("x", "j3", design_data)
        assert BomRun.query.count() == 3

    def test_db_failure_does_not_fail_bom_generation(self, app, profile_dict, design_data):
        """DB hiccup must NOT take down a successful BOM generation —
        that's what the user is paying to wait 15 seconds for. The
        hook wraps in try/except and logs."""
        with patch("services.bom_service.get_profile_by_id", return_value=profile_dict), \
             patch("services.bom_service._call_ai_for_quantities",
                   return_value={"drawn_items": [], "consumables": []}), \
             patch.object(sku_catalog, "all_items", return_value=[]), \
             patch("services.bom_service._record_bom_run",
                   side_effect=RuntimeError("DB exploded")):
            # Should NOT raise
            bom = bom_service.generate("x", "j1", design_data)
        assert bom is not None
        assert "item_count" in bom
        # No row persisted because the hook failed
        assert BomRun.query.count() == 0
