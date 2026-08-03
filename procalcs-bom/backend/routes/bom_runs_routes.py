"""
bom_runs_routes.py — Run-history API for the testing harness.

Mounted at /api/v1/bom-runs in app.py:
    GET  /api/v1/bom-runs/                  — paginated list (filters: client_id, reviewer_status, tag, q, limit, offset)
    GET  /api/v1/bom-runs/<int:run_id>      — full record (parsed_design_data + generated_bom included)
    POST /api/v1/bom-runs/<int:run_id>/review       — set reviewer_status / notes
    POST /api/v1/bom-runs/<int:run_id>/regenerate   — re-run bom_service.generate against the stored design_data
    POST /api/v1/bom-runs/<int:run_id>/compare      — XLS / JSON comparator (Phase 7)
    POST /api/v1/bom-runs/<int:run_id>/tags         — add / remove tags on a run  (Phase 9)
    GET  /api/v1/bom-runs/tags                      — distinct tags + counts      (Phase 9)
    POST /api/v1/bom-runs/regression-suites/<tag>/run
        — re-run every member of a tagged suite, link via regenerated_from_id     (Phase 9)

Phase 4 / 7 / 9 of the testing-harness rollout (May 2026). Built on top
of the bom_runs persistence layer landed in Phase 3 (see services/bom_service.py
and models/bom_run.py).

All routes require the SERVICE_SHARED_SECRET (verified by app-level
middleware before they ever reach this blueprint). Reviewer email is
pulled from g.current_user when available — that's the OAuth-verified
designer email forwarded by designer-desktop's BFF.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, g, jsonify, request
from sqlalchemy import or_

from extensions import db
from models import BomRun, BomComparison
from models.bom_run import REVIEWER_STATUSES
from services import bom_service
from services.bom_comparator import compare_bom
from services.bom_diff import diff_summary, is_regression
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
        tag             = (request.args.get("tag") or "").strip()

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

        # Tag filter — applied in Python after the SQL fetch. JSONB
        # membership filters differ between Postgres + SQLite, and the
        # bom_runs table is small (staging-scale): this keeps the route
        # cross-DB without extra dialect plumbing. If/when the table
        # grows we'll add a Postgres-specific `tags @> [tag]` predicate.
        if tag:
            all_matching = (
                query.order_by(BomRun.created_at.desc()).all()
            )
            filtered = [r for r in all_matching if tag in (r.tags or [])]
            total = len(filtered)
            rows = filtered[offset : offset + limit]
        else:
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
    """Full record including parsed_design_data + generated_bom.

    Day-30 (Tim): when the run carries patch ops, the derived
    summaries (quick order, duct cuts) are rebuilt from the PATCHED
    line items so every surface agrees with the corrections. Stored
    data stays raw; the SPA still replays ops over line items."""
    run = BomRun.query.get(run_id)
    if run is None:
        return _err(f"Run {run_id} not found", 404)
    d = run.to_dict()
    if run.patch_ops:
        from services.bom_patches import bom_with_patched_summaries
        d["generated_bom"] = bom_with_patched_summaries(run)
    return _ok(d)


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

    # Day-26 — dispatch on the run's source pipeline. Wrightsoft v2
    # runs store their generic-part listing as wrightsoft_lines; the
    # AI/bom_service path CANNOT rebuild those (it produced 9 junk
    # lines when tried). Re-run them through the wrightsoft builder,
    # which also re-applies contractor overrides — so corrections
    # entered since the parent run fold into the fresh BOM.
    ws_lines = design_data.get("wrightsoft_lines") if isinstance(design_data, dict) else None
    if ws_lines:
        from models.client_profile import ClientProfile
        from services.bom_from_wrightsoft import build_bom_from_wrightsoft_lines
        from services.profile_service import get_profile_by_id

        profile_data = get_profile_by_id(parent.client_id)
        if not profile_data:
            return _err(f"No profile found for client_id '{parent.client_id}'", 404)
        try:
            bom = build_bom_from_wrightsoft_lines(
                lines=ws_lines,
                profile=ClientProfile.from_dict(profile_data),
                job_id=new_job_id,
                output_mode=output_mode or "full",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("wrightsoft regenerate failed parent=%s: %s",
                         run_id, exc, exc_info=True)
            return _err("BOM regeneration failed. Please try again.", 500)
        # Day-31 — carry the parent's structural extras (duct tables,
        # annotations, register pre-flight). They come from the .rup
        # bytes at upload time; the wrightsoft builder strips unknown
        # keys, so without this every regenerated run silently lost
        # its Duct Cuts tables and hint cards.
        from services.bom_patches import carry_structural_extras
        carry_structural_extras(bom, parent.generated_bom)
        try:
            run = BomRun.record(
                client_id=parent.client_id,
                job_id=new_job_id,
                output_mode=output_mode,
                parsed_design_data=parent.parsed_design_data,
                generated_bom=bom,
                created_by_email=_reviewer_email_from_request(),
                regenerated_from_id=parent.id,
            )
            # Day-29 (Tim, Randolph Cabin): CARRY the parent's applied
            # corrections into the regenerated run. Tim built a 26-op
            # grille reconciliation, regenerated, and lost it all —
            # twice. Regenerate = fresh engine build + the expert's
            # corrections replayed on top (idempotent ops: removes of
            # absent lines and updates of missing SKUs no-op).
            if parent.patch_ops:
                run.patch_ops = list(parent.patch_ops)
            db.session.commit()
            bom["run_id"] = run.id
            bom["patch_ops"] = list(parent.patch_ops or [])
            # Day-30 (Tim): summaries must reflect the carried
            # corrections — his 10→2 fix showed 2 in lines, 10 in the
            # Quick Order Summary after regeneration.
            from services.bom_patches import rebuild_summaries
            rebuild_summaries(bom, bom["patch_ops"])
        except Exception as exc:  # noqa: BLE001 — persistence is best-effort
            logger.warning("wrightsoft regenerate persistence failed: %s", exc)
            db.session.rollback()
        return _ok(bom)

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


@bom_runs_bp.route("/<int:run_id>/patches", methods=["POST"])
def add_patch(run_id: int):
    """Append one surgical correction to this run's patch list.

    Body:
        op          — "update_line" | "remove_line" | "add_line"
        sku         — line key (generic_id / part number)
        fields      — for update/add: {quantity?, unit_price?, description?, source?}
        reason      — one-line justification (required; shown in review)
        snipe_ref   — optional chat snipe ref this correction came from
        rule_candidate — bool; true when the user phrased it as a
                      standing rule ("always", "every plan") — recorded
                      for ledger review, NOT auto-promoted.

    Patches fix THIS run only. Prices should go through contractor
    overrides instead (they're remembered forever); the SPA enforces
    that split. Returns the full updated ops list.
    """
    run = BomRun.query.get(run_id)
    if run is None:
        return _err(f"Run {run_id} not found", 404)

    body = request.get_json(silent=True) or {}
    op_kind = str(body.get("op") or "").strip()
    if op_kind not in ("update_line", "remove_line", "add_line"):
        return _err("op must be update_line | remove_line | add_line", 400)
    sku = str(body.get("sku") or "").strip()
    reason = str(body.get("reason") or "").strip()
    if not sku or not reason:
        return _err("sku and reason are required", 400)
    fields = body.get("fields") if isinstance(body.get("fields"), dict) else {}
    if op_kind in ("update_line", "add_line") and not fields:
        return _err(f"{op_kind} requires a non-empty fields object", 400)

    entry = {
        "op": op_kind,
        "sku": sku,
        "fields": fields,
        "reason": reason,
        "snipe_ref": body.get("snipe_ref") or None,
        "author": _reviewer_email_from_request(),
        "at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
    }
    ops = list(run.patch_ops or [])
    ops.append(entry)
    run.patch_ops = ops
    db.session.commit()

    # Day-25 telemetry — patches are loop input too.
    try:
        from models.usage_event import UsageEvent
        UsageEvent.record(
            event="patch_applied",
            actor_email=entry["author"],
            client_id=run.client_id,
            job_id=run.job_id,
            run_id=run.id,
            detail={"op": op_kind, "sku": sku, "snipe_ref": entry["snipe_ref"]},
            commit=False,
        )
        if body.get("rule_candidate"):
            UsageEvent.record(
                event="rule_candidate",
                actor_email=entry["author"],
                client_id=run.client_id,
                job_id=run.job_id,
                run_id=run.id,
                detail={"op": op_kind, "sku": sku, "reason": reason},
                commit=False,
            )
        db.session.commit()
    except Exception:  # noqa: BLE001 — telemetry never blocks the patch
        logger.warning("patch telemetry failed", exc_info=True)
        db.session.rollback()

    # Day-30 (Tim): hand back summaries rebuilt from the patched
    # lines so the Quick Order / Duct Cuts cards sync immediately.
    from services.bom_patches import rebuild_summaries
    import copy as _copy
    _bom = _copy.deepcopy(run.generated_bom or {})
    rebuild_summaries(_bom, ops)
    return _ok({"run_id": run.id, "patch_ops": ops,
                "quick_order_summary": _bom.get("quick_order_summary"),
                "duct_cuts_summary": _bom.get("duct_cuts_summary")})


@bom_runs_bp.route("/<int:run_id>/chat", methods=["GET"])
def get_chat(run_id: int):
    """Return the persisted conversation for a run — INCLUDING its
    regeneration ancestors — oldest first, so the SPA rehydrates the
    full thread.

    Day-29 (Tim, Randolph): chat is keyed per run, but regenerating
    moves the canvas to a CHILD run while the conversation so far
    lives on the parent. A refresh on the child hydrated an empty
    thread — "after the page refresh it no longer carried forward the
    established correction context." Walk regenerated_from_id up the
    chain (bounded) and merge chronologically; new turns keep writing
    to the current run, so storage stays canonical with no copying."""
    from models import ChatMessage, BomRun
    run = BomRun.query.get(run_id)
    if run is None:
        return _err(f"Run {run_id} not found", 404)
    chain = [run.id]
    node = run
    for _ in range(10):  # bounded ancestor walk
        pid = node.regenerated_from_id
        if not pid:
            break
        node = BomRun.query.get(pid)
        if node is None:
            break
        chain.append(node.id)
    msgs: list = []
    for rid in chain:
        msgs.extend(ChatMessage.for_run(rid))
    msgs.sort(key=lambda m: (m.created_at, m.id))
    return _ok({"run_id": run_id, "lineage": chain,
                "messages": [m.to_dict() for m in msgs]})


@bom_runs_bp.route("/<int:run_id>/chat", methods=["POST"])
def append_chat(run_id: int):
    """Append one or more turns to a run's conversation. Called
    server-side by the designer BFF after each chat exchange.

    Body: {turns: [{role, content?, actions?, attachments?}, ...]}
    author_email is taken from the forwarded identity header, not the
    body, so it can't be spoofed."""
    from models import ChatMessage, BomRun
    if BomRun.query.get(run_id) is None:
        return _err(f"Run {run_id} not found", 404)
    body = request.get_json(silent=True) or {}
    turns = body.get("turns")
    if not isinstance(turns, list) or not turns:
        return _err("turns (non-empty array) is required", 400)
    author = _reviewer_email_from_request()
    saved = []
    for tn in turns[:20]:
        role = str(tn.get("role") or "").strip()
        if role not in ("user", "assistant"):
            continue
        saved.append(ChatMessage.record(
            run_id=run_id, role=role,
            content=(tn.get("content") or None),
            actions=tn.get("actions") or None,
            attachments=tn.get("attachments") or None,
            author_email=author if role == "user" else None,
            commit=False,
        ))
    db.session.commit()
    return _ok({"run_id": run_id, "saved": len(saved)})


@bom_runs_bp.route("/<int:run_id>/chat", methods=["DELETE"])
def clear_chat(run_id: int):
    """Delete a run's conversation (clear chat / cleanup)."""
    from models import ChatMessage, BomRun
    if BomRun.query.get(run_id) is None:
        return _err(f"Run {run_id} not found", 404)
    n = db.session.query(ChatMessage).filter_by(run_id=run_id).delete()
    db.session.commit()
    return _ok({"run_id": run_id, "deleted": n})


@bom_runs_bp.route("/<int:run_id>", methods=["DELETE"])
def delete_run(run_id: int):
    """Delete a BOM run and its dependent chat/rows (BREAD Delete).
    ChatMessage cascades via FK; patch_ops live on the row itself.
    Contractor overrides are intentionally NOT deleted — they are
    contractor-wide learning, not owned by one run."""
    from models import BomRun, ChatMessage
    run = BomRun.query.get(run_id)
    if run is None:
        return _err(f"Run {run_id} not found", 404)
    db.session.query(ChatMessage).filter_by(run_id=run_id).delete()
    db.session.delete(run)
    db.session.commit()
    return _ok({"deleted": run_id})


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

    # Day-2 — persist the comparison as an audit row. Best-effort:
    # the comparison computed fine, the user should still get their
    # report even if the DB write fails.
    try:
        comp = BomComparison.record(
            bom_run_id      = run.id,
            sample_filename = source_filename or "(pasted)",
            report_dict     = payload,
            created_by_email= _reviewer_email_from_request(),
        )
        db.session.commit()
        payload["comparison_id"] = comp.id
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning(
            "BomComparison persistence failed run_id=%s: %s — comparison still returned",
            run_id, exc,
        )
    payload["sample_filename"] = source_filename
    payload["sample_lines"] = sample_lines  # echoed for SPA preview
    return _ok(payload)


# ─── Tags + regression suites (Phase 9) ─────────────────────────────

# Tag string sanity — keep them short, lower-kebab-case so they sort
# nicely in the SPA chip lists. Reject anything wild so two testers
# can't accidentally create "regression-v1" + " Regression-V1 ".
_TAG_MAX_LEN = 40
_TAG_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789-_.")


def _normalize_tag(raw: str) -> str:
    """Lowercase + strip + reject illegal chars. Returns the cleaned
    tag, or raises ValueError. Used by both /<id>/tags and the
    regression-suite endpoint so the same canonicalization wins."""
    t = (raw or "").strip().lower()
    if not t:
        raise ValueError("tag must not be empty")
    if len(t) > _TAG_MAX_LEN:
        raise ValueError(f"tag exceeds {_TAG_MAX_LEN} chars")
    bad = [c for c in t if c not in _TAG_ALLOWED]
    if bad:
        raise ValueError(
            f"tag contains illegal characters {sorted(set(bad))} — "
            "use a-z 0-9 - _ ."
        )
    return t


@bom_runs_bp.route("/tags", methods=["GET"])
def list_tags():
    """Return distinct tags + counts across all bom_runs.

    Done in Python after a single full-table fetch. Same rationale as
    the tag-filter on list_runs: cross-DB JSONB membership is awkward,
    and bom_runs is staging-scale. The SPA only calls this when the
    user opens the regression-suites page, so the cost is bounded.
    """
    try:
        all_runs = BomRun.query.with_entities(BomRun.tags).all()
        counts: dict[str, int] = {}
        for (tags,) in all_runs:
            for t in (tags or []):
                if not isinstance(t, str):
                    continue
                counts[t] = counts.get(t, 0) + 1
        # Sort alphabetically; ties broken by count desc — UI displays
        # popular suites first within the same prefix.
        items = [
            {"tag": t, "count": c}
            for t, c in sorted(counts.items(), key=lambda kv: (kv[0], -kv[1]))
        ]
        return _ok({"tags": items, "total": len(items)})
    except Exception as exc:  # noqa: BLE001
        logger.error("list_tags failed: %s", exc, exc_info=True)
        return _err("Failed to list tags", 500)


@bom_runs_bp.route("/<int:run_id>/tags", methods=["POST"])
def update_tags(run_id: int):
    """Add and / or remove tags on a single run.

    Body: {"add": ["t1", "t2"], "remove": ["t3"]} — both arrays
    optional, empty body is a no-op (returns the current state).

    Returns the updated summary so the SPA can re-render its chip
    list without a follow-up GET. Idempotent — adding a tag the run
    already has is a no-op rather than an error.
    """
    run = BomRun.query.get(run_id)
    if run is None:
        return _err(f"Run {run_id} not found", 404)

    body = request.get_json(silent=True) or {}
    add_raw = body.get("add") or []
    remove_raw = body.get("remove") or []
    if not isinstance(add_raw, list) or not isinstance(remove_raw, list):
        return _err("add and remove must be arrays of strings", 400)

    try:
        to_add = [_normalize_tag(t) for t in add_raw if t]
        to_remove = [_normalize_tag(t) for t in remove_raw if t]
    except ValueError as exc:
        return _err(str(exc), 400)

    current = list(run.tags or [])
    # Drop removals first, then add (so add wins on a contradictory body)
    current = [t for t in current if t not in to_remove]
    for t in to_add:
        if t not in current:
            current.append(t)

    # SQLAlchemy needs a new list assignment to flag the JSON column
    # as dirty — in-place .append() doesn't trigger an UPDATE.
    run.tags = current
    try:
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.error("update_tags failed run_id=%s: %s", run_id, exc, exc_info=True)
        return _err("Failed to save tags", 500)

    return _ok(run.to_summary())


@bom_runs_bp.route("/regression-suites/<path:tag>/run", methods=["POST"])
def run_regression_suite(tag: str):
    """Re-run every bom_run carrying ``tag`` against bom_service.generate,
    using the parent's stored design_data + client_id, link the new
    rows via regenerated_from_id, and tag them with the same suite tag
    so the suite stays self-curating across runs.

    Returns a per-member report:
        {"tag": "...", "members": [{"parent_id":..., "child_id":...,
                                    "status":"ok"|"error", "error":...}]}

    Generation latency is 10-20s per RUP; on suites of 5+ this can be
    minutes total. We keep it sync-blocking — the SPA shows a single
    spinner and the DB has the canonical state when it returns.
    Background-jobs is a Phase 11 stretch.
    """
    try:
        suite_tag = _normalize_tag(tag)
    except ValueError as exc:
        return _err(str(exc), 400)

    parents = (
        BomRun.query.order_by(BomRun.created_at.asc()).all()
    )
    parents = [p for p in parents if suite_tag in (p.tags or [])]
    if not parents:
        return _err(f"No runs tagged '{suite_tag}'", 404)

    body = request.get_json(silent=True) or {}
    new_job_suffix = (body.get("new_job_suffix") or "suite-rerun").strip() or "suite-rerun"

    members = []
    for parent in parents:
        member: dict[str, Any] = {
            "parent_id":               parent.id,
            "parent_job":              parent.job_id,
            "parent_created_by_email": parent.created_by_email,
            "child_id":                None,
            "status":                  "ok",
            "error":                   None,
            "item_count":              None,
        }
        if not parent.parsed_design_data:
            member.update({
                "status": "error",
                "error":  "parent has no parsed_design_data — skipped",
            })
            members.append(member)
            continue

        new_job_id = f"{parent.job_id}-{new_job_suffix}-{parent.id}"
        try:
            bom = bom_service.generate(
                client_id=parent.client_id,
                job_id=new_job_id,
                design_data=parent.parsed_design_data,
                output_mode=parent.output_mode,
                regenerated_from_id=parent.id,
            )
            child_id = bom.get("run_id")
            member["child_id"] = child_id
            member["item_count"] = bom.get("item_count")

            # Phase 11 — auto-detect drift. Compare parent.generated_bom
            # vs the just-generated child. Surface diff metrics + a
            # boolean so the SPA can label this row as "regression"
            # without an extra round trip.
            try:
                summary = diff_summary(parent.generated_bom, bom)
                member["diff"] = summary
                member["regression_detected"] = is_regression(summary)
            except Exception as exc:  # noqa: BLE001
                # Diff is best-effort — failure must not poison the
                # suite-run report. Log and continue.
                logger.warning("diff_summary failed parent=%s child=%s: %s",
                               parent.id, child_id, exc)

            # Carry the suite tag forward so the next regression-suite
            # invocation picks up the freshly-generated child as a
            # member too. Without this the suite would calcify to its
            # original membership.
            if child_id:
                child_run = BomRun.query.get(child_id)
                if child_run is not None:
                    tags = list(child_run.tags or [])
                    if suite_tag not in tags:
                        tags.append(suite_tag)
                        child_run.tags = tags
                        db.session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("regression-suite member failed parent=%s: %s",
                           parent.id, exc)
            member.update({"status": "error", "error": str(exc)})
        members.append(member)

    summary = {
        "ok":          sum(1 for m in members if m["status"] == "ok"),
        "errors":      sum(1 for m in members if m["status"] == "error"),
        "regressions": sum(1 for m in members if m.get("regression_detected")),
        "total":       len(members),
    }
    return _ok({"tag": suite_tag, "summary": summary, "members": members})


# ─── Missing-SKU backlog (Day-2 polish) ─────────────────────────────

@bom_runs_bp.route("/missing-sku-backlog", methods=["GET"])
def missing_sku_backlog():
    """Aggregate every missing-SKU across all stored bom_comparisons,
    grouped by SKU, sorted by demand (frequency × total qty).

    Powers the SPA's "encode these next" backlog page. Lets Richard's
    team prioritize catalog encoding by what's actually missing in
    contractor sample BOMs — not by guesswork.

    Response shape:
        {
          "total_comparisons": N,
          "total_missing_skus_unique": M,
          "items": [
            {
              "sku":              "drfg1712mi",
              "sku_display":      "DRFg1712MI",
              "description":      "Rectangular fiberglass duct, 17x12",
              "occurrence_count": 12,     // showed up missing in 12 comparisons
              "total_qty":        45.0,   // sum of sample_qty across those
              "first_seen":       "2026-05-15T...",
              "last_seen":        "2026-05-18T...",
              "run_ids":          [1, 5, 12, ...]  // up to first 20
            },
            ...
          ]
        }

    Filters: ?client_id=foo restricts to comparisons whose underlying
    bom_run was for that contractor.
    """
    try:
        client_id = (request.args.get("client_id") or "").strip()

        # Pull all comparisons; tiny join to BomRun for client_id filter
        # is fine at staging-scale (hundreds, not millions).
        q = BomComparison.query
        if client_id:
            q = q.join(BomRun, BomRun.id == BomComparison.bom_run_id)\
                 .filter(BomRun.client_id == client_id)
        comparisons = q.order_by(BomComparison.created_at.asc()).all()

        # Group missing SKUs across all rows
        grouped: dict[str, dict[str, Any]] = {}
        for comp in comparisons:
            for m in (comp.missing_skus or []):
                key = m.get("sku") or f"_nosku::{(m.get('description') or '').lower()}"
                if not key.strip():
                    continue
                if key not in grouped:
                    grouped[key] = {
                        "sku":              m.get("sku"),
                        "sku_display":      m.get("sku_display"),
                        "description":      m.get("description"),
                        "occurrence_count": 0,
                        "total_qty":        0.0,
                        "first_seen":       comp.created_at.isoformat() if comp.created_at else None,
                        "last_seen":        comp.created_at.isoformat() if comp.created_at else None,
                        "run_ids":          [],
                        # Day-5: track who's been flagging this SKU as
                        # missing — useful for prioritization ("3 testers
                        # all hit this" vs "one tester hit this 3 times").
                        "contributors":     [],
                    }
                g = grouped[key]
                g["occurrence_count"] += 1
                try:
                    g["total_qty"] += float(m.get("qty") or 0)
                except (TypeError, ValueError):
                    pass
                if comp.bom_run_id not in g["run_ids"] and len(g["run_ids"]) < 20:
                    g["run_ids"].append(comp.bom_run_id)
                if comp.created_by_email and comp.created_by_email not in g["contributors"]:
                    g["contributors"].append(comp.created_by_email)
                if comp.created_at:
                    iso = comp.created_at.isoformat()
                    g["last_seen"] = iso  # comparisons ordered asc, last wins
                # Prefer the longest description we've seen so the SPA
                # has the best-quality label.
                d = m.get("description") or ""
                if d and len(d) > len(g.get("description") or ""):
                    g["description"] = d
                # Same for sku_display — prefer the cased form
                if (not g.get("sku_display")) and m.get("sku_display"):
                    g["sku_display"] = m.get("sku_display")

        # Sort: occurrence_count desc, then total_qty desc (high-demand
        # items first). Ties broken alphabetically for stable ordering.
        items = sorted(
            grouped.values(),
            key=lambda g: (-g["occurrence_count"], -g["total_qty"], g.get("sku") or ""),
        )

        return _ok({
            "total_comparisons":         len(comparisons),
            "total_missing_skus_unique": len(items),
            "items":                     items,
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("missing_sku_backlog failed: %s", exc, exc_info=True)
        return _err("Failed to build backlog", 500)


@bom_runs_bp.route("/<int:run_id>/comparisons", methods=["GET"])
def list_run_comparisons(run_id: int):
    """List all persisted comparisons for a single run, newest first.
    Useful for "show me every sample I've uploaded against run #5"."""
    run = BomRun.query.get(run_id)
    if run is None:
        return _err(f"Run {run_id} not found", 404)
    rows = (
        BomComparison.query
        .filter(BomComparison.bom_run_id == run_id)
        .order_by(BomComparison.created_at.desc())
        .all()
    )
    return _ok({
        "run_id":      run_id,
        "comparisons": [r.to_summary() for r in rows],
    })
