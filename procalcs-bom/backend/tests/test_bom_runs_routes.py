"""
Phase 4 — tests for the bom_runs API endpoints (list / detail / review /
regenerate).

Same in-memory SQLite + create_all pattern as test_bom_run.py, plus a
Flask test_client so we exercise the HTTP layer end-to-end.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# create_app() registers routes/bom_routes.py which imports
# services/pdf_service.py → weasyprint at module-load time. Stub it
# locally for this test file only — global stubbing in conftest would
# break test_pdf_service.py's `pytest.importorskip("weasyprint")`.
if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:  # noqa: BLE001
        _w = MagicMock()
        _w.HTML = MagicMock()
        _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w

# Force in-memory SQLite + dummy required env BEFORE importing the app.
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('ANTHROPIC_API_KEY', 'dev-test')
os.environ.setdefault('FIRESTORE_PROJECT_ID', 'dev-test')
# Empty SERVICE_SHARED_SECRET — auth middleware fails open in dev so the
# test_client doesn't need to pass the token on every call.
os.environ.setdefault('SERVICE_SHARED_SECRET', '')

from app import create_app
from extensions import db
from models import BomRun
from services import bom_service, sku_catalog


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
def client(app):
    return app.test_client()


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


def _seed_run(client_id="test-contractor", job_id="seed-job",
              status="unset", email=None, design=None, bom=None) -> BomRun:
    run = BomRun.record(
        client_id=client_id,
        job_id=job_id,
        output_mode="full",
        parsed_design_data=design or {"equipment": []},
        generated_bom=bom or {"item_count": 3,
                              "totals": {"total_price": 99.5}},
        created_by_email=email,
    )
    if status != "unset":
        run.review(status=status)
    db.session.commit()
    return run


# ─── GET / (list) ───────────────────────────────────────────────────

class TestListRuns:
    def test_returns_empty_list_when_no_rows(self, app, client):
        resp = client.get("/api/v1/bom-runs/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["runs"] == []
        assert body["data"]["total"] == 0

    def test_returns_summary_shape_not_full(self, app, client):
        _seed_run(bom={"item_count": 7, "totals": {"total_price": 12.34},
                       "huge": "x" * 5000})
        resp = client.get("/api/v1/bom-runs/")
        runs = resp.get_json()["data"]["runs"]
        assert len(runs) == 1
        # Summary drops the heavy JSONB
        assert "parsed_design_data" not in runs[0]
        assert "generated_bom" not in runs[0]
        # But carries the cheap projected fields the list view needs
        assert runs[0]["item_count"] == 7
        assert runs[0]["total_price"] == 12.34

    def test_filter_by_client_id(self, app, client):
        _seed_run(client_id="contractor-a", job_id="ja")
        _seed_run(client_id="contractor-b", job_id="jb")
        resp = client.get("/api/v1/bom-runs/?client_id=contractor-b")
        runs = resp.get_json()["data"]["runs"]
        assert len(runs) == 1 and runs[0]["client_id"] == "contractor-b"

    def test_filter_by_reviewer_status(self, app, client):
        _seed_run(job_id="j1", status="good")
        _seed_run(job_id="j2", status="needs_fix")
        _seed_run(job_id="j3")  # unset
        resp = client.get("/api/v1/bom-runs/?reviewer_status=good")
        runs = resp.get_json()["data"]["runs"]
        assert len(runs) == 1 and runs[0]["job_id"] == "j1"

    def test_q_matches_job_id_or_email(self, app, client):
        _seed_run(job_id="alpha-house", email="tom@procalcs.net")
        _seed_run(job_id="beta-house",  email="richard@procalcs.net")
        # Substring against job_id
        runs = client.get("/api/v1/bom-runs/?q=alpha").get_json()["data"]["runs"]
        assert len(runs) == 1 and runs[0]["job_id"] == "alpha-house"
        # Substring against created_by_email
        runs = client.get("/api/v1/bom-runs/?q=richard").get_json()["data"]["runs"]
        assert len(runs) == 1 and runs[0]["created_by_email"] == "richard@procalcs.net"

    def test_orders_newest_first(self, app, client):
        _seed_run(job_id="oldest")
        _seed_run(job_id="middle")
        _seed_run(job_id="newest")
        runs = client.get("/api/v1/bom-runs/").get_json()["data"]["runs"]
        assert [r["job_id"] for r in runs] == ["newest", "middle", "oldest"]

    def test_pagination_limit_offset(self, app, client):
        for i in range(5):
            _seed_run(job_id=f"j{i}")
        resp = client.get("/api/v1/bom-runs/?limit=2&offset=1")
        body = resp.get_json()["data"]
        assert body["total"] == 5
        assert body["limit"] == 2 and body["offset"] == 1
        assert len(body["runs"]) == 2

    def test_rejects_unknown_status(self, app, client):
        resp = client.get("/api/v1/bom-runs/?reviewer_status=mystery")
        assert resp.status_code == 400
        assert "must be one of" in resp.get_json()["error"]

    def test_clamps_huge_limit(self, app, client):
        for i in range(3):
            _seed_run(job_id=f"j{i}")
        resp = client.get("/api/v1/bom-runs/?limit=100000")
        # Clamped to MAX_LIMIT (200), not echoed verbatim
        assert resp.get_json()["data"]["limit"] == 200


# ─── GET /<id> (detail) ─────────────────────────────────────────────

class TestGetRun:
    def test_returns_full_dict_with_jsonb(self, app, client):
        run = _seed_run(
            design={"equipment": [{"name": "AHU-1"}]},
            bom={"item_count": 1, "line_items": [{"sku": "A"}]},
        )
        resp = client.get(f"/api/v1/bom-runs/{run.id}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["id"] == run.id
        assert data["parsed_design_data"] == {"equipment": [{"name": "AHU-1"}]}
        assert data["generated_bom"]["line_items"] == [{"sku": "A"}]

    def test_404_for_missing_id(self, app, client):
        resp = client.get("/api/v1/bom-runs/9999")
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"]


# ─── POST /<id>/review ──────────────────────────────────────────────

class TestReviewRun:
    def test_sets_status_and_notes(self, app, client):
        run = _seed_run()
        resp = client.post(
            f"/api/v1/bom-runs/{run.id}/review",
            json={"status": "good", "notes": "looks right"},
        )
        assert resp.status_code == 200
        body = resp.get_json()["data"]
        assert body["reviewer_status"] == "good"
        # Re-read to confirm persistence
        fresh = BomRun.query.get(run.id)
        assert fresh.reviewer_status == "good"
        assert fresh.reviewer_notes == "looks right"

    def test_rejects_missing_status(self, app, client):
        run = _seed_run()
        resp = client.post(f"/api/v1/bom-runs/{run.id}/review", json={})
        assert resp.status_code == 400
        assert "status is required" in resp.get_json()["error"]

    def test_rejects_unknown_status(self, app, client):
        run = _seed_run()
        resp = client.post(
            f"/api/v1/bom-runs/{run.id}/review",
            json={"status": "mystery"},
        )
        assert resp.status_code == 400
        assert "must be one of" in resp.get_json()["error"]

    def test_404_for_missing_id(self, app, client):
        resp = client.post("/api/v1/bom-runs/9999/review", json={"status": "good"})
        assert resp.status_code == 404

    def test_re_review_preserves_notes_when_omitted(self, app, client):
        """Same contract as the model-level test in test_bom_run.py —
        flipping status without passing notes shouldn't blank them."""
        run = _seed_run()
        client.post(f"/api/v1/bom-runs/{run.id}/review",
                    json={"status": "needs_fix", "notes": "hangers wrong"})
        client.post(f"/api/v1/bom-runs/{run.id}/review",
                    json={"status": "blocked"})
        fresh = BomRun.query.get(run.id)
        assert fresh.reviewer_status == "blocked"
        assert fresh.reviewer_notes == "hangers wrong"


# ─── POST /<id>/regenerate ──────────────────────────────────────────

class TestRegenerateRun:
    def _patches(self, profile_dict):
        # Same pattern as test_bom_run.py — bypass Firestore + Anthropic.
        return [
            patch("services.bom_service.get_profile_by_id", return_value=profile_dict),
            patch("services.bom_service._call_ai_for_quantities",
                  return_value={"drawn_items": [], "consumables": []}),
            patch.object(sku_catalog, "all_items", return_value=[]),
        ]

    def test_regenerate_creates_new_row_linked_to_parent(
        self, app, client, profile_dict, design_data,
    ):
        # Seed a parent run via the real bom_service so the design_data
        # round-trip matches what production does.
        for p in self._patches(profile_dict):
            p.start()
        try:
            bom_service.generate("test-contractor", "parent-job", design_data)
            parent = BomRun.query.first()
            assert parent is not None and parent.regenerated_from_id is None

            resp = client.post(f"/api/v1/bom-runs/{parent.id}/regenerate", json={})
            assert resp.status_code == 200, resp.get_json()
            new_bom = resp.get_json()["data"]
            assert "run_id" in new_bom
            assert new_bom["run_id"] != parent.id

            # The new row is linked back via FK
            child = BomRun.query.get(new_bom["run_id"])
            assert child.regenerated_from_id == parent.id
            # Default new_job_id format
            assert child.job_id == f"{parent.job_id}-rerun-{parent.id}"
            # Same client_id carries through
            assert child.client_id == parent.client_id
        finally:
            for p in self._patches(profile_dict):
                try: p.stop()
                except Exception: pass

    def test_regenerate_accepts_overrides(
        self, app, client, profile_dict, design_data,
    ):
        for p in self._patches(profile_dict):
            p.start()
        try:
            bom_service.generate("test-contractor", "p", design_data)
            parent = BomRun.query.first()
            resp = client.post(
                f"/api/v1/bom-runs/{parent.id}/regenerate",
                json={"new_job_id": "custom-rerun", "output_mode": "summary"},
            )
            assert resp.status_code == 200
            child = BomRun.query.get(resp.get_json()["data"]["run_id"])
            assert child.job_id == "custom-rerun"
            assert child.output_mode == "summary"
        finally:
            for p in self._patches(profile_dict):
                try: p.stop()
                except Exception: pass

    def test_regenerate_with_design_data_override_uses_it(
        self, app, client, profile_dict, design_data,
    ):
        for p in self._patches(profile_dict):
            p.start()
        try:
            bom_service.generate("test-contractor", "p", design_data)
            parent = BomRun.query.first()
            tweaked = {**design_data, "_marker": "tweaked"}
            client.post(
                f"/api/v1/bom-runs/{parent.id}/regenerate",
                json={"design_data": tweaked},
            )
            child = (
                BomRun.query.filter(BomRun.regenerated_from_id == parent.id)
                            .first()
            )
            assert child.parsed_design_data.get("_marker") == "tweaked"
        finally:
            for p in self._patches(profile_dict):
                try: p.stop()
                except Exception: pass

    def test_404_for_missing_parent(self, app, client):
        resp = client.post("/api/v1/bom-runs/9999/regenerate", json={})
        assert resp.status_code == 404

    def test_422_when_parent_has_no_design_data(self, app, client):
        # Pre-Phase-3 row simulation — design_data is None.
        run = BomRun.record(
            client_id="x", job_id="y", output_mode="full",
            parsed_design_data=None, generated_bom={"item_count": 0},
        )
        db.session.commit()
        resp = client.post(f"/api/v1/bom-runs/{run.id}/regenerate", json={})
        assert resp.status_code == 422
        assert "cannot regenerate" in resp.get_json()["error"]

# ─── POST /<id>/compare ─────────────────────────────────────────────

class TestCompareRun:
    def _seed_run_with_bom(self, line_items: list[dict]):
        run = BomRun.record(
            client_id="x", job_id="cmp-job", output_mode="full",
            parsed_design_data={},
            generated_bom={
                "line_items": line_items,
                "item_count": len(line_items),
                "totals": {"total_cost": 0, "total_price": 0},
            },
        )
        db.session.commit()
        return run

    def test_compare_with_json_sample_lines_payload(self, app, client):
        run = self._seed_run_with_bom([
            {"sku": "A", "description": "AHU", "quantity": 1},
            {"sku": "B", "description": "Cond", "quantity": 1},
        ])
        resp = client.post(
            f"/api/v1/bom-runs/{run.id}/compare",
            json={"sample_lines": [
                {"sku": "A", "description": "AHU", "quantity": 1},
                {"sku": "C", "description": "Missing", "quantity": 1},
            ]},
        )
        assert resp.status_code == 200, resp.get_json()
        d = resp.get_json()["data"]
        assert d["run_id"] == run.id
        m = d["metrics"]
        assert m["matched"] == 1
        assert m["missing"] == 1
        assert m["extra"] == 1  # B was in run but not in sample
        assert m["sku_match_rate"] == 0.5

    def test_compare_with_xlsx_upload(self, app, client):
        from io import BytesIO
        from openpyxl import Workbook
        run = self._seed_run_with_bom([
            {"sku": "AHU-24K", "description": "Air handler", "quantity": 1},
        ])
        wb = Workbook()
        ws = wb.active
        ws.append(["Src", "Name", "Description", "Qty"])
        ws.append(["GOOD", "AHU-24K", "Air handler", 1])
        buf = BytesIO()
        wb.save(buf)

        resp = client.post(
            f"/api/v1/bom-runs/{run.id}/compare",
            data={"file": (BytesIO(buf.getvalue()), "sample.xlsx")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200, resp.get_json()
        d = resp.get_json()["data"]
        assert d["sample_filename"] == "sample.xlsx"
        assert d["metrics"]["matched"] == 1

    def test_404_for_missing_run(self, app, client):
        resp = client.post("/api/v1/bom-runs/9999/compare", json={"sample_lines": []})
        assert resp.status_code == 404

    def test_422_when_run_has_no_generated_bom(self, app, client):
        run = BomRun.record(
            client_id="x", job_id="cmp-job", output_mode="full",
            parsed_design_data={}, generated_bom=None,
        )
        db.session.commit()
        resp = client.post(f"/api/v1/bom-runs/{run.id}/compare", json={"sample_lines": []})
        assert resp.status_code == 422
        assert "nothing to compare" in resp.get_json()["error"].lower()

    def test_400_when_neither_file_nor_sample_lines_provided(self, app, client):
        run = self._seed_run_with_bom([{"sku": "A", "description": "x", "quantity": 1}])
        resp = client.post(f"/api/v1/bom-runs/{run.id}/compare", json={})
        assert resp.status_code == 400


# ─── Tags + regression suites (Phase 9) ─────────────────────────────

class TestTagsAndSuites:
    def _seed(self, *, tags=None, design=None):
        run = BomRun.record(
            client_id="x", job_id=f"job-{datetime.utcnow().timestamp()}",
            output_mode="full",
            parsed_design_data=design or {"equipment": []},
            generated_bom={"item_count": 1, "totals": {"total_price": 10}},
            tags=tags or [],
        )
        db.session.commit()
        return run

    # /<id>/tags ——————————————————————————————————————————————————

    def test_add_tags_idempotent(self, app, client):
        run = self._seed()
        # First add
        resp = client.post(f"/api/v1/bom-runs/{run.id}/tags",
                           json={"add": ["regression-v1", "easy"]})
        assert resp.status_code == 200
        assert sorted(resp.get_json()["data"]["tags"]) == ["easy", "regression-v1"]
        # Re-adding same tag is a no-op
        resp = client.post(f"/api/v1/bom-runs/{run.id}/tags",
                           json={"add": ["regression-v1"]})
        assert sorted(resp.get_json()["data"]["tags"]) == ["easy", "regression-v1"]

    def test_remove_tags(self, app, client):
        run = self._seed(tags=["a", "b", "c"])
        resp = client.post(f"/api/v1/bom-runs/{run.id}/tags",
                           json={"remove": ["b"]})
        assert sorted(resp.get_json()["data"]["tags"]) == ["a", "c"]

    def test_normalizes_tag_to_lowercase(self, app, client):
        run = self._seed()
        resp = client.post(f"/api/v1/bom-runs/{run.id}/tags",
                           json={"add": ["  Regression-V1  "]})
        assert resp.get_json()["data"]["tags"] == ["regression-v1"]

    def test_rejects_illegal_chars(self, app, client):
        run = self._seed()
        resp = client.post(f"/api/v1/bom-runs/{run.id}/tags",
                           json={"add": ["hi world!"]})
        assert resp.status_code == 400
        assert "illegal characters" in resp.get_json()["error"]

    def test_404_for_missing_run(self, app, client):
        resp = client.post("/api/v1/bom-runs/9999/tags", json={"add": ["x"]})
        assert resp.status_code == 404

    # GET /tags ——————————————————————————————————————————————————

    def test_list_tags_distinct_with_counts(self, app, client):
        self._seed(tags=["regression-v1"])
        self._seed(tags=["regression-v1", "easy"])
        self._seed(tags=["edge"])
        resp = client.get("/api/v1/bom-runs/tags")
        d = resp.get_json()["data"]
        # Sorted alphabetically
        assert [t["tag"] for t in d["tags"]] == ["easy", "edge", "regression-v1"]
        counts = {t["tag"]: t["count"] for t in d["tags"]}
        assert counts == {"easy": 1, "edge": 1, "regression-v1": 2}

    def test_list_tags_empty_when_no_runs(self, app, client):
        resp = client.get("/api/v1/bom-runs/tags")
        assert resp.get_json()["data"]["tags"] == []

    # List filter ——————————————————————————————————————————————————

    def test_list_filter_by_tag(self, app, client):
        a = self._seed(tags=["regression-v1"])
        b = self._seed(tags=["edge"])
        c = self._seed(tags=["regression-v1", "easy"])
        resp = client.get("/api/v1/bom-runs/?tag=regression-v1")
        runs = resp.get_json()["data"]["runs"]
        ids = {r["id"] for r in runs}
        assert ids == {a.id, c.id}
        assert b.id not in ids

    # /regression-suites/<tag>/run ——————————————————————————————

    def _patches(self, profile_dict):
        return [
            patch("services.bom_service.get_profile_by_id", return_value=profile_dict),
            patch("services.bom_service._call_ai_for_quantities",
                  return_value={"drawn_items": [], "consumables": []}),
            patch.object(sku_catalog, "all_items", return_value=[]),
        ]

    def test_run_suite_regenerates_each_member(self, app, client, profile_dict, design_data):
        # Seed two runs with the same tag, real design_data so generate works
        for p in self._patches(profile_dict): p.start()
        try:
            bom_service.generate("test-contractor", "parent-1", design_data)
            bom_service.generate("test-contractor", "parent-2", design_data)
            for r in BomRun.query.all():
                r.tags = ["regression-v1"]
            db.session.commit()
            assert BomRun.query.count() == 2

            resp = client.post("/api/v1/bom-runs/regression-suites/regression-v1/run", json={})
            assert resp.status_code == 200, resp.get_json()
            d = resp.get_json()["data"]
            assert d["tag"] == "regression-v1"
            assert d["summary"]["ok"] == 2
            assert d["summary"]["errors"] == 0
            # Each member produced a child
            for m in d["members"]:
                assert m["status"] == "ok"
                assert m["child_id"] is not None
            # Children inherit the suite tag (so the next suite-run picks them up too)
            children = (
                BomRun.query.filter(BomRun.regenerated_from_id.isnot(None)).all()
            )
            assert len(children) == 2
            for c in children:
                assert "regression-v1" in (c.tags or [])
        finally:
            for p in self._patches(profile_dict):
                try: p.stop()
                except Exception: pass

    def test_run_suite_404_when_no_members(self, app, client):
        resp = client.post("/api/v1/bom-runs/regression-suites/no-such-tag/run", json={})
        assert resp.status_code == 404

    def test_run_suite_member_without_design_data_marked_error(self, app, client):
        # Seed a row with no design_data — suite still completes, this
        # member reports error.
        run = BomRun.record(
            client_id="x", job_id="orphan", output_mode="full",
            parsed_design_data=None, generated_bom={"item_count": 0},
            tags=["regression-v1"],
        )
        db.session.commit()
        resp = client.post("/api/v1/bom-runs/regression-suites/regression-v1/run", json={})
        assert resp.status_code == 200
        d = resp.get_json()["data"]
        assert d["summary"]["errors"] == 1
        assert d["summary"]["ok"] == 0
        assert "no parsed_design_data" in d["members"][0]["error"]
        # Pre-Phase-3 row simulation — design_data is None.
        run = BomRun.record(
            client_id="x", job_id="y", output_mode="full",
            parsed_design_data=None, generated_bom={"item_count": 0},
        )
        db.session.commit()
        resp = client.post(f"/api/v1/bom-runs/{run.id}/regenerate", json={})
        assert resp.status_code == 422
        assert "cannot regenerate" in resp.get_json()["error"]
