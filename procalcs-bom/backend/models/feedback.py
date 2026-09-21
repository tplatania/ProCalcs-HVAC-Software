"""
feedback.py — in-app feedback / ask threads.

Testers (e.g. Dana) and the team hold short, attachment-bearing
conversations INSIDE the app instead of over email/Slack, so no file
transfer round-trips through Gerald. Two thread kinds share one store:

    report    a tester flags something they saw (bug, wrong line, UX)
    question  an item that needs a human answer (e.g. an M-sheet
              accessory question) — routed to the whole team; anyone
              can answer on the domain expert's behalf.

Design guardrail — the intake agent is a CAPTURE assistant, not a chat
partner. `agent_clarifications_used` is hard-capped at 1 per thread
(enforced in the routes), so the agent can post at most ONE nudge and
then only ever logs. It cannot loop or exhaust the tester.

Attachments (screenshots, the M-sheet PDF) are stored as bytes in the
row for durability — the BOM-chat attachment path expires on a 7-day
GCS lifecycle, which is wrong for feedback the team reads later. Volume
is low (a pilot) and files are small (an 8 MB/file cap in the route).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_JSONType = JSON().with_variant(JSONB(), "postgresql")

# Stored as plain strings (not enums) so new kinds/statuses need no
# migration — same convention as BomRun.REVIEWER_STATUSES.
THREAD_KINDS = ("report", "question")
THREAD_STATUSES = ("open", "answered", "resolved")
MESSAGE_ROLES = ("tester", "team", "agent")


class FeedbackThread(db.Model):
    __tablename__ = "feedback_threads"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(16), nullable=False)          # report | question
    status = db.Column(db.String(16), nullable=False, default="open", index=True)
    title = db.Column(db.String(300), nullable=False)
    page_context = db.Column(db.String(120), nullable=True)  # e.g. wrightsoft-bom-v2
    # Link to the BOM the thread is about, when there is one. SET NULL
    # (not CASCADE) — deleting a run must never delete a tester's report.
    run_id = db.Column(
        db.Integer,
        db.ForeignKey("bom_runs.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    client_id = db.Column(db.String(120), nullable=True)
    target = db.Column(db.String(32), nullable=False, default="team")
    created_by_email = db.Column(db.String(255), nullable=True, index=True)
    # Hard cap on agent nudges — 0 or 1. The route refuses to add a
    # second, which is the structural anti-exhaustion guarantee.
    agent_clarifications_used = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    messages = db.relationship(
        "FeedbackMessage", backref="thread", cascade="all, delete-orphan",
        order_by="FeedbackMessage.created_at.asc(), FeedbackMessage.id.asc()",
    )
    attachments = db.relationship(
        "FeedbackAttachment", backref="thread", cascade="all, delete-orphan",
        order_by="FeedbackAttachment.id.asc()",
    )

    @classmethod
    def record(
        cls, *, kind: str, title: str, page_context: Optional[str] = None,
        run_id: Optional[int] = None, client_id: Optional[str] = None,
        created_by_email: Optional[str] = None, commit: bool = True,
    ) -> "FeedbackThread":
        row = cls(
            kind=kind, title=title, page_context=page_context, run_id=run_id,
            client_id=client_id, created_by_email=created_by_email, status="open",
        )
        db.session.add(row)
        if commit:
            db.session.commit()
        else:
            db.session.flush()   # populate id for the caller
        return row

    @classmethod
    def recent(cls, *, status: Optional[str] = None, kind: Optional[str] = None,
               created_by_email: Optional[str] = None, limit: int = 100
               ) -> list["FeedbackThread"]:
        q = db.session.query(cls)
        if status:
            q = q.filter_by(status=status)
        if kind:
            q = q.filter_by(kind=kind)
        if created_by_email:
            q = q.filter_by(created_by_email=created_by_email)
        return q.order_by(cls.updated_at.desc(), cls.id.desc()).limit(limit).all()

    def to_summary(self) -> dict:
        msgs = self.messages or []
        last = msgs[-1] if msgs else None
        return {
            "id":            self.id,
            "kind":          self.kind,
            "status":        self.status,
            "title":         self.title,
            "page_context":  self.page_context,
            "run_id":        self.run_id,
            "client_id":     self.client_id,
            "created_by_email": self.created_by_email,
            "message_count": len(msgs),
            "attachment_count": len(self.attachments or []),
            "last_message_at": (last.created_at.isoformat() + "Z") if last and last.created_at else None,
            "last_message_role": last.role if last else None,
            "created_at":    (self.created_at.isoformat() + "Z") if self.created_at else None,
            "updated_at":    (self.updated_at.isoformat() + "Z") if self.updated_at else None,
        }

    def to_detail(self) -> dict:
        d = self.to_summary()
        d["messages"] = [m.to_dict() for m in (self.messages or [])]
        d["attachments"] = [a.to_meta() for a in (self.attachments or [])]
        return d


class FeedbackMessage(db.Model):
    __tablename__ = "feedback_messages"

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(
        db.Integer,
        db.ForeignKey("feedback_threads.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)
    role = db.Column(db.String(16), nullable=False)          # tester | team | agent
    author_email = db.Column(db.String(255), nullable=True)  # null for agent
    body = db.Column(db.Text, nullable=True)

    @classmethod
    def record(cls, *, thread_id: int, role: str, body: Optional[str] = None,
               author_email: Optional[str] = None, commit: bool = True
               ) -> "FeedbackMessage":
        row = cls(thread_id=thread_id, role=role, body=body, author_email=author_email)
        db.session.add(row)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return row

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "thread_id":    self.thread_id,
            "created_at":   (self.created_at.isoformat() + "Z") if self.created_at else None,
            "role":         self.role,
            "author_email": self.author_email,
            "body":         self.body,
        }


class FeedbackAttachment(db.Model):
    __tablename__ = "feedback_attachments"

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(
        db.Integer,
        db.ForeignKey("feedback_threads.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    message_id = db.Column(
        db.Integer,
        db.ForeignKey("feedback_messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    filename = db.Column(db.String(300), nullable=False)
    content_type = db.Column(db.String(120), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    data = db.Column(db.LargeBinary, nullable=False)          # raw bytes (bytea on PG)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    @classmethod
    def record(cls, *, thread_id: int, filename: str, content_type: str,
               data: bytes, message_id: Optional[int] = None, commit: bool = False
               ) -> "FeedbackAttachment":
        row = cls(
            thread_id=thread_id, message_id=message_id, filename=filename,
            content_type=content_type or "application/octet-stream",
            size_bytes=len(data or b""), data=data,
        )
        db.session.add(row)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return row

    def is_image(self) -> bool:
        return (self.content_type or "").lower().startswith("image/")

    def to_meta(self) -> dict:
        """Metadata only — never the bytes (served via GET /attachments/<id>)."""
        return {
            "id":           self.id,
            "thread_id":    self.thread_id,
            "message_id":   self.message_id,
            "filename":     self.filename,
            "content_type": self.content_type,
            "size_bytes":   self.size_bytes,
            "is_image":     self.is_image(),
        }
