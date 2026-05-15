"""
bom_runs_routes.py — Run-history API for the testing harness.

Mounted at /api/v1/bom-runs in app.py:
    GET  /api/v1/bom-runs/                  — paginated list (filters: client_id, reviewer_status, q, limit, offset)
    GET  /api/v1/bom-runs/<int:run_id>      — full record (parsed_design_data + generated_bom included)
    POST /api/v1/bom-runs/<int:run_id>/review     — set reviewer_status / notes
    POST /api/v1/bom-runs/<int:run_id>/regenerate — re-run bom_service.generate against the stored design_data,
                                                    linking the new row via regenerated_from_id

Phase 4 of the testing-harness rollout (May 2026). Built on top of
the bom_runs persistence layer landed in Phase 3 (see services/bom_service.py
and models/bom_run.py).

All routes require the SERVICE_SHARED_SECRET (verified by app-level
middleware before they ever reach this blueprint). Reviewer email is
pulled from g.current_user when available — that's the OAuth-verified
designer email forwarded by designer-desktop's BFF.
"""

from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, g, jsonify, request
from sqlalchemy import or_

from extensions import db
from models import BomRun
from models.bom_run import REVIEWER_STATUSES
from services import bom_service
from services.bom_comparator import compare_bom
from services.sample_bom import parse_sample_bom_bytes

logger = logging.getLogger("procalcs_bom.bom_runs")

bom_runs_bp = Blueprint("bom_runs", __name__)


# ─── Helpers ────────────────────────────────────────────────────────

def _ok(data: Any, status: int = 200):
    return jsonify({"success": True, "data": data, "error": None}), status


def _err(message: str, status: int = 400):
    return jsonify({"success": False, "data": None, "error": message}), status


def _reviewer_email_from_request() -> str | None:
    """Prefer g.current_user (set by user middleware from
    X-Procalcs-User-Email). Falls back to the body-provided email so
    automated harness scripts can still attribute reviews."""
    user = getattr(g, "current_user", None)
    if user is not None:
        return getattr(user, "email", None)
    return None


# ─── List ───────────────────────────────────────────────────────────

# Cap list size — list-view payloads use to_summary() (no JSONB columns)
# so 200 rows is ~50KB. Cap keeps a runaway query polite to the DB and
# the SPA. Set high enough that Richard's daily review doesn't paginate.
_MAX_LIMIT = 200
_DEFAULT_LIMIT = 50


@bom_runs_bp.route("/", methods=["GET"])
def list_runs():
    """Paginated list of BOM runs, newest first.

    Query params:
        client_id        — exact match
        reviewer_status  — exact match (one of REVIEWER_STATUSES)
        q                — case-insensitive substring against job_id OR
                           created_by_email (handy for "what did Tom run yesterday")
        limit            — default 50, max 200
        offset           — default 0
    """
    try:
        client_id       = (request.args.get("client_id") or "").strip()
        reviewer_status = (request.args.get("reviewer_status") or "").strip()
        q               = (request.args.get("q") or "").strip()

        try:
            limit = int(request.args.get("limit", _DEFAULT_LIMIT))
        except (TypeError, ValueError):
            return _err("limit must be an integer", 400)
        try:
            offset = int(request.args.get("offset", 0))
        except (TypeError, ValueError):
            return _err("offset must be an integer", 400)

        # Clamp instead of erroring — keeps pagination forgiving for
        # naive callers but still bounded.
        limit  = max(1, min(limit, _MAX_LIMIT))
        offset = max(0, offset)

        if reviewer_status and reviewer_status not in REVIEWER_STATUSES:
            return _err(
                f"reviewer_status must be one of {list(REVIEWER_STATUSES)}",
                400,
            )

        query = BomRun.query
        if client_id:
            query = query.filter(BomRun.client_id == client_id)
        if reviewer_status:
            query = query.filter(BomRun.reviewer_status == reviewer_status)
        if q:
            like = f"%{q}%"
            query = query.filter(or_(
                BomRun.job_id.ilike(like),
                BomRun.created_by_email.ilike(like),
            ))

        total = query.count()
        rows = (
            query.order_by(BomRun.created_at.desc())
                 .limit(limit)
                 .offset(offset)
                 .all()
        )
        return _ok({
            "runs":   [r.to_summary() for r in rows],
            "total":  total,
            "limit":  limit,
            "offset": offset,
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("list_runs failed: %s", exc, exc_info=True)
        return _err("Failed to list runs", 500)


# ─── Detail ─────────────────────────────────────────────────────────

@bom_runs_bp.route("/<int:run_id>", methods=["GET"])
def get_run(run_id: int):
    """Full record including parsed_design_data + generated_bom."""
    run = BomRun.query.get(run_id)
    if run is None:
        return _err(f"Run {run_id} not found", 404)
    return _ok(run.to_dict())


# ─── Review ─────────────────────────────────────────────────────────

@bom_runs_bp.route("/<int:run_id>/review", methods=["POST"])
def review_run(run_id: int):
    """Set reviewer status + optional notes. Idempotent — same payload
    twice produces the same final state."""
    run = BomRun.query.get(run_id)
    if run is None:
        return _err(f"Run {run_id} not found", 404)

    body = request.get_json(silent=True) or {}
    status = (body.get("status") or "").strip()
    if not status:
        return _err("status is required", 400)
    if status not in REVIEWER_STATUSES:
        return _err(
            f"status must be one of {list(REVIEWER_STATUSES)}", 400,
        )

    # `notes` is optional. Pass `None` (rather than empty string) when
    # absent so BomRun.review preserves any existing note — see the
    # test_review_with_only_status_does_not_clear_notes contract.
    notes = body.get("notes")
    email = _reviewer_email_from_request() or body.get("email")

    try:
        run.review(status=status, notes=notes, email=email)
        db.session.commit()
    except ValueError as exc:
        return _err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.error("review_run failed for id=%s: %s", run_id, exc, exc_info=True)
        return _err("Failed to save review", 500)

    return _ok(run.to_summary())


# ─── Regenerate ─────────────────────────────────────────────────────

@bom_runs_bp.route("/<int:run_id>/regenerate", methods=["POST"])
def regenerate_run(run_id: int):
    """Re-run bom_service.generate against the parent run's stored
    design_data, link the new row via regenerated_from_id, return the
    fresh BOM (with the new run_id baked in).

    Body (all optional):
        new_job_id      — defaults to "<parent.job_id>-rerun-<parent.id>"
        output_mode     — defaults to parent's output_mode
        design_data     — overrides parent's design_data (lets the SPA
                          tweak-and-regenerate without re-uploading the RUP)
    """
    parent = BomRun.query.get(run_id)
    if parent is None:
        return _err(f"Run {run_id} not found", 404)

    body = request.get_json(silent=True) or {}

    design_data = body.get("design_data") if isinstance(body.get("design_data"), dict) else None
    if design_data is None:
        design_data = parent.parsed_design_data or {}

    if not design_data:
        # Defensive — if the parent row pre-dates the persistence layer
        # or had its design_data stripped, we can't regenerate.
        return _err(
            "Parent run has no parsed_design_data — cannot regenerate. "
            "Run /api/v1/bom/generate manually with a fresh design_data.",
            422,
        )

    new_job_id  = (body.get("new_job_id") or f"{parent.job_id}-rerun-{parent.id}").strip()
    output_mode = body.get("output_mode") or parent.output_mode

    try:
        bom = bom_service.generate(
            client_id=parent.client_id,
            job_id=new_job_id,
            design_data=design_data,
            output_mode=output_mode,
            regenerated_from_id=parent.id,
        )
    except ValueError as exc:
        return _err(str(exc), 404)
    except RuntimeError as exc:
        logger.error("regenerate runtime error parent=%s: %s", run_id, exc)
        return _err("BOM regeneration failed. Please try again.", 500)
    except Exception as exc:  # noqa: BLE001
        logger.error("regenerate unexpected error parent=%s: %s", run_id, exc, exc_info=True)
        return _err("Something went wrong during regeneration.", 500)

    return _ok(bom)


# ─── Compare with sample BOM ────────────────────────────────────────

# Cap upload size — Tom's reference BOMs are 30-100 rows; even with
# heavy formatting they're under 1 MB. Cap at 5 MB so a malformed
# upload can't OOM the worker.
_MAX_SAMPLE_BYTES = 5 * 1024 * 1024


@bom_runs_bp.route("/<int:run_id>/compare", methods=["POST"])
def compare_run(run_id: int):
    """Compare a saved BOM run against a contractor's reference sample.

    Two intake modes:

      a) multipart upload of a Wrightsoft .xls / .xlsx — parsed via
         services.sample_bom into the canonical line-item shape.
      b) JSON body `{"sample_lines": [{"sku":..., "quantity":...}, ...]}`
         — for callers that already extracted the rows (e.g. the SPA's
         paste-CSV path, or an automated harness loading a fixture).

    Returns the report from services.bom_comparator unchanged: a
    metrics roll-up + per-line outcomes (matched / qty_mismatch /
    missing / extra). Does NOT persist the report — Phase 8/9 will
    layer on storage when we wire the regression suite.
    """
    run = BomRun.query.get(run_id)
    if run is None:
        return _err(f"Run {run_id} not found", 404)
    if not run.generated_bom:
        return _err(
            "Run has no generated_bom — nothing to compare against.", 422,
        )

    sample_lines: list[dict] = []
    source_filename: str | None = None

    # Multipart-file branch
    if "file" in request.files:
        upload = request.files["file"]
        source_filename = upload.filename or "sample.xls"
        file_bytes = upload.read()
        if not file_bytes:
            return _err("Uploaded sample file is empty", 400)
        if len(file_bytes) > _MAX_SAMPLE_BYTES:
            return _err(
                f"Sample file exceeds {_MAX_SAMPLE_BYTES // 1024 // 1024} MB limit",
                413,
            )
        try:
            sample_lines = parse_sample_bom_bytes(file_bytes, filename=source_filename)
        except ValueError as exc:
            return _err(str(exc), 400)
        except Exception as exc:  # noqa: BLE001
            logger.error("compare_run parse failed run_id=%s: %s", run_id, exc, exc_info=True)
            return _err("Failed to parse sample BOM", 500)
    else:
        body = request.get_json(silent=True) or {}
        sl = body.get("sample_lines")
        if not isinstance(sl, list):
            return _err(
                "Send either a multipart 'file' upload or {\"sample_lines\": [...]}.",
                400,
            )
        sample_lines = sl

    try:
        report = compare_bom(sample_lines, run.generated_bom)
    except Exception as exc:  # noqa: BLE001
        logger.error("compare_run compute failed run_id=%s: %s", run_id, exc, exc_info=True)
        return _err("Comparison failed", 500)

    payload = report.to_dict()
    payload["run_id"] = run.id
    payload["sample_filename"] = source_filename
    payload["sample_lines"] = sample_lines  # echoed for SPA preview
    return _ok(payload)
