"""
chat_message.py — persistent BOM Review Assistant conversation.

Day-27. Richard asked to save a conversation and resume it later, and
so Gerald can read his findings without re-posting them in Slack.
Until now the chat lived only in the SPA's React state and evaporated
on reload.

One row per turn, keyed to the bom_run the conversation is about:

    role         "user" | "assistant"
    content      the message text
    actions      assistant proposals (price/patch/regenerate) as JSON
    attachments  lightweight metadata only ({name, kind}) — never the
                 raw file bytes or extracted contents (privacy + size)
    author_email who sent it (user turns); null for assistant

Persistence is server-side (the designer BFF writes after each turn),
so the record is authoritative and can't be spoofed by the client.
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


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(
        db.Integer,
        db.ForeignKey("bom_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)
    role = db.Column(db.String(16), nullable=False)         # user | assistant
    content = db.Column(db.Text, nullable=True)
    actions = db.Column(_JSONType, nullable=True)
    attachments = db.Column(_JSONType, nullable=True)
    author_email = db.Column(db.String(255), nullable=True)

    @classmethod
    def record(
        cls,
        *,
        run_id: int,
        role: str,
        content: Optional[str] = None,
        actions: Optional[Any] = None,
        attachments: Optional[Any] = None,
        author_email: Optional[str] = None,
        commit: bool = True,
    ) -> "ChatMessage":
        row = cls(
            run_id=run_id, role=role, content=content,
            actions=actions, attachments=attachments, author_email=author_email,
        )
        db.session.add(row)
        if commit:
            db.session.commit()
        return row

    @classmethod
    def for_run(cls, run_id: int) -> list["ChatMessage"]:
        return (
            db.session.query(cls)
            .filter_by(run_id=run_id)
            .order_by(cls.created_at.asc(), cls.id.asc())
            .all()
        )

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "run_id":       self.run_id,
            "created_at":   self.created_at.isoformat() + "Z" if self.created_at else None,
            "role":         self.role,
            "content":      self.content,
            "actions":      self.actions or [],
            "attachments":  self.attachments or [],
            "author_email": self.author_email,
        }
