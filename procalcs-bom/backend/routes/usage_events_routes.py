"""
usage_events_routes.py — adoption + learning-loop telemetry surface.

Mounted under /api/v1/usage-events. Three endpoints:

    POST /api/v1/usage-events
        Record one event. Body: {event, client_id?, job_id?, run_id?,
        detail?}. Actor comes from the identity headers, provenance is
        derived server-side (never trusted from the client).

    GET  /api/v1/usage-events/summary?days=30&include_test=0
        Counts by event + per-day timeline + distinct real actors.
        Answers "is Richard's team actively using it?"

    GET  /api/v1/usage-events/impact?client_id=...&include_test=0
        The learning-loop scoreboard. Walks bom_runs.generated_bom
        (which carries override_id audit marks per line) and counts,
        for every contractor override, how many LATER runs it
        auto-applied to. Works retroactively — no events needed for
        history that predates this table. Answers "is the app
        actually learning?" and feeds the transparency panel.

Provenance discipline: rows/overrides/runs attributable to test
actors (TEST_ACTOR_EMAILS — Gerald/dev, non-experts) are excluded
from every metric unless include_test=1. Runs with NO actor email
are also excluded from impact by default — historically those are
shared-secret smoke-suite calls, not contractor work.

Envelope: {success, data, error} like the rest of the BOM API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from extensions import db
from models.usage_event import UsageEvent, provenance_for, test_actor_emails

logger = logging.getLogger("procalcs_bom")
usage_events_bp = Blueprint("usage_events", __name__)

_ALLOWED_EVENTS = {
    "bom_generated",
    "chat_message",
    "attachment_uploaded",
    "override_saved",
    "proposal_applied",
    "patch_applied",
    "rule_candidate",
    "question_answered",
}


def _actor() -> str | None:
    return (
        request.headers.get("X-Procalcs-User-Email")
        or request.headers.get("X-Actor-Email")
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─── POST — record one event ───────────────────────────────────────

@usage_events_bp.route("", methods=["POST"])
def record_event():
    body = request.get_json(silent=True) or {}
    event = str(body.get("event") or "").strip()
    if event not in _ALLOWED_EVENTS:
        return jsonify({
            "success": False, "data": None,
            "error": f"unknown event '{event}' — allowed: {sorted(_ALLOWED_EVENTS)}",
        }), 400
    detail = body.get("detail")
    if detail is not None and not isinstance(detail, dict):
        return jsonify({
            "success": False, "data": None,
            "error": "detail must be an object",
        }), 400
    try:
        row = UsageEvent.record(
            event=event,
            actor_email=_actor(),
            client_id=(body.get("client_id") or None),
            job_id=(body.get("job_id") or None),
            run_id=(body.get("run_id") or None),
            detail=detail,
        )
    except Exception:  # telemetry must never 500 the caller's flow
        logger.exception("usage-event insert failed")
        db.session.rollback()
        return jsonify({"success": False, "data": None,
                        "error": "insert failed"}), 500
    return jsonify({"success": True, "data": row.to_dict(), "error": None}), 201


# ─── GET /summary — adoption at a glance ───────────────────────────

@usage_events_bp.route("/summary", methods=["GET"])
def summary():
    days = min(max(int(request.args.get("days", 30)), 1), 365)
    include_test = request.args.get("include_test") == "1"
    since = _utcnow() - timedelta(days=days)

    q = db.session.query(UsageEvent).filter(UsageEvent.created_at >= since)
    if not include_test:
        q = q.filter(UsageEvent.provenance == "real")
    rows = q.order_by(UsageEvent.created_at.asc()).all()

    by_event: dict[str, int] = {}
    by_day: dict[str, int] = {}
    actors: dict[str, int] = {}
    for r in rows:
        by_event[r.event] = by_event.get(r.event, 0) + 1
        day = r.created_at.date().isoformat()
        by_day[day] = by_day.get(day, 0) + 1
        if r.actor_email:
            actors[r.actor_email] = actors.get(r.actor_email, 0) + 1

    return jsonify({
        "success": True,
        "data": {
            "days": days,
            "include_test": include_test,
            "total_events": len(rows),
            "by_event": by_event,
            "by_day": by_day,
            "actors": [
                {"email": e, "events": n}
                for e, n in sorted(actors.items(), key=lambda kv: -kv[1])
            ],
            "test_actors": sorted(test_actor_emails()),
        },
        "error": None,
    })


# ─── GET /impact — the learning-loop scoreboard ────────────────────

@usage_events_bp.route("/impact", methods=["GET"])
def impact():
    from models import BomRun, ContractorOverride

    client_id = (request.args.get("client_id") or "").strip() or None
    include_test = request.args.get("include_test") == "1"
    tests = test_actor_emails()

    ov_q = db.session.query(ContractorOverride)
    if client_id:
        ov_q = ov_q.filter(ContractorOverride.contractor_id == client_id)
    overrides = ov_q.all()
    if not include_test:
        overrides = [
            o for o in overrides
            if not (o.updated_by and o.updated_by.strip().lower() in tests)
        ]

    run_q = db.session.query(BomRun).filter(BomRun.generated_bom.isnot(None))
    if client_id:
        run_q = run_q.filter(BomRun.client_id == client_id)
    runs = run_q.order_by(BomRun.created_at.asc()).all()
    runs_scanned = 0

    # override_id → [(run_id, run_created_at)]
    hits: dict[int, list[tuple[int, datetime]]] = {}
    for run in runs:
        email = (run.created_by_email or "").strip().lower()
        if not include_test and (not email or email in tests):
            continue  # no-actor runs are historically smoke-suite calls
        runs_scanned += 1
        items = (run.generated_bom or {}).get("line_items") or []
        seen: set[int] = set()
        for li in items:
            ov_id = li.get("override_id") if isinstance(li, dict) else None
            if isinstance(ov_id, int):
                seen.add(ov_id)
        for ov_id in seen:
            hits.setdefault(ov_id, []).append((run.id, run.created_at))

    per_override = []
    authors: dict[str, dict[str, int]] = {}
    total_reapplications = 0
    for o in overrides:
        # A hit strictly after the override was created is a
        # re-application — the loop closing. The run where the
        # correction was first entered doesn't count.
        later = [
            (rid, at) for rid, at in hits.get(o.id, [])
            if o.created_at and at and at > o.created_at
        ]
        total_reapplications += len(later)
        author = o.updated_by or "unknown"
        a = authors.setdefault(author, {"overrides": 0, "reapplications": 0})
        a["overrides"] += 1
        a["reapplications"] += len(later)
        per_override.append({
            "override_id": o.id,
            "client_id":   o.contractor_id,
            "supplier":    o.supplier,
            "sku":         o.sku,
            "unit_price":  o.unit_price,
            "author":      o.updated_by,
            "created_at":  o.created_at.isoformat() + "Z" if o.created_at else None,
            "reapplied_runs": len(later),
            "last_reapplied_at":
                max(at for _, at in later).isoformat() + "Z" if later else None,
        })
    per_override.sort(key=lambda d: -d["reapplied_runs"])

    return jsonify({
        "success": True,
        "data": {
            "client_id": client_id,
            "include_test": include_test,
            "totals": {
                "overrides": len(overrides),
                "overrides_reapplied": sum(
                    1 for d in per_override if d["reapplied_runs"] > 0),
                "total_reapplications": total_reapplications,
                "runs_scanned": runs_scanned,
            },
            "authors": [
                {"author": k, **v}
                for k, v in sorted(authors.items(),
                                   key=lambda kv: -kv[1]["reapplications"])
            ],
            "top": per_override[:25],
        },
        "error": None,
    })
