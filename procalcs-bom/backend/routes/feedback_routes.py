"""
feedback_routes.py — in-app feedback / ask threads.

Testers and the team converse inside the app (with screenshots), so
nothing round-trips through email/Slack. See models/feedback.py for the
data model and the anti-exhaustion guarantee.

Blueprint mounted at /api/v1/feedback (behind the service-token gate +
user-identity middleware, like every other v1 blueprint).

Endpoints:
    POST   /threads                 create a thread (multipart: fields + files)
    GET    /threads                 list thread summaries (filters: status,kind,mine)
    GET    /threads/<id>            thread detail (messages + attachment meta)
    POST   /threads/<id>/messages   append a message (multipart: body + files)
    POST   /threads/<id>/resolve    set status (answered | resolved | open)
    GET    /attachments/<id>        serve one attachment's bytes
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, Response, g, jsonify, request

from extensions import db
from models.feedback import (
    THREAD_KINDS, THREAD_STATUSES, FeedbackThread, FeedbackMessage,
    FeedbackAttachment,
)

logger = logging.getLogger(__name__)

feedback_bp = Blueprint("feedback", __name__)

# Per-file guardrails. The global MAX_CONTENT_LENGTH (25 MB) backstops
# the whole request; this bounds a single feedback attachment.
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_FILES = 5

# The agent's ONLY nudge — offered at most once per thread (the counter
# in the model enforces this). A capture prompt, never a conversation.
_NUDGE = (
    "Thanks — this is logged for the team. If it's something visual, a "
    "screenshot helps them see exactly what you saw. You can add one in a "
    "reply, or leave it as is — either way it's captured."
)
_CONFIRM_REPORT = (
    "Thanks — logged with your screenshot. The team will follow up right here."
)
_CONFIRM_REPORT_NOFILE = (
    "Thanks — this is logged for the team. They'll follow up right here."
)
_CONFIRM_QUESTION = (
    "Logged for the team. Anyone can answer, and the reply shows up in this "
    "thread — no need to chase it over email."
)


def _ok(data, status=200):
    return jsonify({"success": True, "data": data, "error": None}), status


def _err(message, status=400):
    return jsonify({"success": False, "data": None, "error": message}), status


def _reviewer_email():
    user = getattr(g, "current_user", None)
    return getattr(user, "email", None) if user is not None else None


def _save_attachments(thread_id: int, message_id=None) -> int:
    """Persist uploaded files (request.files['attachments']) as bytes.
    Returns the count saved. Skips oversize files rather than failing the
    whole submission (the text is the important part)."""
    saved = 0
    files = request.files.getlist("attachments")[:_MAX_FILES]
    for f in files:
        if not f or not f.filename:
            continue
        data = f.read()
        if not data or len(data) > _MAX_FILE_BYTES:
            logger.warning("feedback: skipped attachment %r (%d bytes)",
                           f.filename, len(data or b""))
            continue
        FeedbackAttachment.record(
            thread_id=thread_id, message_id=message_id, filename=f.filename[:300],
            content_type=(f.mimetype or "application/octet-stream")[:120],
            data=data, commit=False,
        )
        saved += 1
    return saved


@feedback_bp.route("/threads", methods=["POST"])
def create_thread():
    try:
        # multipart form (files) or JSON — support both.
        form = request.form if request.form else (request.get_json(silent=True) or {})
        kind = (form.get("kind") or "report").strip().lower()
        if kind not in THREAD_KINDS:
            return _err(f"kind must be one of {THREAD_KINDS}")
        title = (form.get("title") or "").strip()
        body = (form.get("body") or "").strip()
        if not title and not body:
            return _err("a title or body is required")
        if not title:
            title = (body[:117] + "…") if len(body) > 118 else body

        run_id = form.get("run_id")
        try:
            run_id = int(run_id) if run_id not in (None, "", "null") else None
        except (TypeError, ValueError):
            run_id = None

        email = _reviewer_email()
        thread = FeedbackThread.record(
            kind=kind, title=title,
            page_context=(form.get("page_context") or None),
            run_id=run_id, client_id=(form.get("client_id") or None),
            created_by_email=email, commit=False,
        )

        # First message = the tester's own words.
        msg = FeedbackMessage.record(
            thread_id=thread.id, role="tester", body=body or title,
            author_email=email, commit=False,
        )
        n_files = _save_attachments(thread.id, message_id=msg.id)

        # ── Bounded triage (deterministic; can never loop) ──────────
        # A visual report with no screenshot gets ONE nudge; everything
        # else gets a plain confirmation. The nudge burns the single
        # clarification the model allows.
        if kind == "report" and n_files == 0 and thread.agent_clarifications_used == 0:
            FeedbackMessage.record(thread_id=thread.id, role="agent",
                                   body=_NUDGE, commit=False)
            thread.agent_clarifications_used = 1
        else:
            if kind == "question":
                confirm = _CONFIRM_QUESTION
            elif n_files > 0:
                confirm = _CONFIRM_REPORT
            else:
                confirm = _CONFIRM_REPORT_NOFILE
            FeedbackMessage.record(thread_id=thread.id, role="agent",
                                   body=confirm, commit=False)

        db.session.commit()
        return _ok(thread.to_detail(), status=201)
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.exception("feedback create_thread failed")
        return _err(f"could not create thread: {exc}", status=500)


@feedback_bp.route("/threads", methods=["GET"])
def list_threads():
    try:
        status = request.args.get("status") or None
        kind = request.args.get("kind") or None
        mine = request.args.get("mine") in ("1", "true", "yes")
        email = _reviewer_email() if mine else None
        if status and status not in THREAD_STATUSES:
            return _err(f"status must be one of {THREAD_STATUSES}")
        rows = FeedbackThread.recent(status=status, kind=kind,
                                     created_by_email=email, limit=200)
        # Light open-count roll-up for the nav badge.
        open_count = (db.session.query(FeedbackThread)
                      .filter(FeedbackThread.status != "resolved").count())
        return _ok({"threads": [t.to_summary() for t in rows],
                    "open_count": open_count})
    except Exception as exc:  # noqa: BLE001
        logger.exception("feedback list_threads failed")
        return _err(f"could not list threads: {exc}", status=500)


@feedback_bp.route("/threads/<int:thread_id>", methods=["GET"])
def get_thread(thread_id: int):
    thread = db.session.get(FeedbackThread, thread_id)
    if thread is None:
        return _err("thread not found", status=404)
    return _ok(thread.to_detail())


@feedback_bp.route("/threads/<int:thread_id>/messages", methods=["POST"])
def add_message(thread_id: int):
    try:
        thread = db.session.get(FeedbackThread, thread_id)
        if thread is None:
            return _err("thread not found", status=404)
        form = request.form if request.form else (request.get_json(silent=True) or {})
        body = (form.get("body") or "").strip()

        email = _reviewer_email()
        # Role is decided server-side: the thread's author is the tester,
        # anyone else answering is the team. Never trust a client role.
        role = "tester" if (email and email == thread.created_by_email) else "team"

        msg = FeedbackMessage.record(thread_id=thread.id, role=role, body=body or None,
                                     author_email=email, commit=False)
        n_files = _save_attachments(thread.id, message_id=msg.id)
        if not body and n_files == 0:
            db.session.rollback()
            return _err("a message body or attachment is required")

        # A team reply on a question moves it to 'answered' (still open to
        # more). The agent stays silent after the first turn — no loop.
        if role == "team" and thread.kind == "question" and thread.status == "open":
            thread.status = "answered"
        # Appending child rows doesn't mark the thread dirty, so bump the
        # sort timestamp explicitly (keeps recent-activity ordering right).
        thread.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        return _ok(thread.to_detail(), status=201)
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.exception("feedback add_message failed")
        return _err(f"could not add message: {exc}", status=500)


@feedback_bp.route("/threads/<int:thread_id>/resolve", methods=["POST"])
def resolve_thread(thread_id: int):
    try:
        thread = db.session.get(FeedbackThread, thread_id)
        if thread is None:
            return _err("thread not found", status=404)
        body = request.get_json(silent=True) or request.form or {}
        status = (body.get("status") or "resolved").strip().lower()
        if status not in THREAD_STATUSES:
            return _err(f"status must be one of {THREAD_STATUSES}")
        thread.status = status
        db.session.commit()
        return _ok(thread.to_summary())
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.exception("feedback resolve_thread failed")
        return _err(f"could not update thread: {exc}", status=500)


@feedback_bp.route("/attachments/<int:att_id>", methods=["GET"])
def get_attachment(att_id: int):
    att = db.session.get(FeedbackAttachment, att_id)
    if att is None:
        return _err("attachment not found", status=404)
    # Inline for images/PDF (so they render in the thread); download
    # otherwise. nosniff hardens against content-type confusion.
    ct = att.content_type or "application/octet-stream"
    inline = ct.lower().startswith("image/") or ct.lower() == "application/pdf"
    disp = "inline" if inline else "attachment"
    resp = Response(att.data, mimetype=ct)
    resp.headers["Content-Disposition"] = f'{disp}; filename="{att.filename}"'
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp
