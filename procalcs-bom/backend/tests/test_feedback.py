"""
Tests for in-app feedback / ask threads (models.feedback +
routes.feedback_routes).

Locks in:
  - create report (no screenshot) → ONE agent nudge, counter burned
  - create report (with screenshot) → confirm (no nudge), bytes stored
    + served via GET /attachments/<id>
  - create question → team-routed confirm
  - role decided server-side (author=tester, others=team); a team reply
    on a question flips it to 'answered'
  - the agent never posts a second message (anti-exhaustion cap)
  - resolve sets status; standard {success,data,error} envelope
"""

import io
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        _w = MagicMock(); _w.HTML = MagicMock(); _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w

for _k, _v in (
    ('DATABASE_URL',         'sqlite:///:memory:'),
    ('ANTHROPIC_API_KEY',    'dev-test'),
    ('FIRESTORE_PROJECT_ID', 'dev-test'),
):
    os.environ.setdefault(_k, _v)
os.environ['SERVICE_SHARED_SECRET'] = ''

DANA = {"X-Procalcs-User-Email": "dana@procalcs.net"}
TEAMMATE = {"X-Procalcs-User-Email": "gerald@procalcs.net"}


@pytest.fixture
def app():
    from app import create_app
    from extensions import db
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


def _agent_msgs(detail):
    return [m for m in detail["messages"] if m["role"] == "agent"]


def test_report_without_screenshot_gets_one_nudge(client):
    r = client.post("/api/v1/feedback/threads",
                    data={"kind": "report", "body": "The heat strip is missing again"},
                    headers=DANA)
    assert r.status_code == 201
    env = r.get_json()
    assert env["success"] is True and env["error"] is None
    d = env["data"]
    assert d["kind"] == "report" and d["status"] == "open"
    assert d["created_by_email"] == "dana@procalcs.net"
    # tester's own words + exactly one agent nudge
    assert [m["role"] for m in d["messages"]] == ["tester", "agent"]
    assert "screenshot" in _agent_msgs(d)[0]["body"].lower()


def test_report_with_screenshot_confirms_and_stores_bytes(client):
    png = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"
    r = client.post(
        "/api/v1/feedback/threads",
        data={"kind": "report", "title": "Grille size wrong",
              "body": "see attached",
              "attachments": (io.BytesIO(png), "shot.png")},
        content_type="multipart/form-data", headers=DANA,
    )
    assert r.status_code == 201
    d = r.get_json()["data"]
    assert d["attachment_count"] == 1
    att = d["attachments"][0]
    assert att["is_image"] is True and att["size_bytes"] == len(png)
    # confirm, NOT nudge (a screenshot was provided)
    assert "screenshot" not in _agent_msgs(d)[0]["body"].lower() or \
           "follow up" in _agent_msgs(d)[0]["body"].lower()
    # bytes are served back verbatim
    got = client.get(f"/api/v1/feedback/attachments/{att['id']}", headers=DANA)
    assert got.status_code == 200
    assert got.data == png
    assert got.headers["Content-Type"].startswith("image/")
    assert got.headers["X-Content-Type-Options"] == "nosniff"


def test_question_is_team_routed(client):
    r = client.post("/api/v1/feedback/threads",
                    data={"kind": "question",
                          "body": "Does the M-sheet list an ERV for this job?"},
                    headers=DANA)
    d = r.get_json()["data"]
    assert d["kind"] == "question"
    assert "team" in _agent_msgs(d)[0]["body"].lower()


def test_team_reply_flips_question_to_answered_and_role(client):
    r = client.post("/api/v1/feedback/threads",
                    data={"kind": "question", "body": "Which strip model?"},
                    headers=DANA)
    tid = r.get_json()["data"]["id"]
    # A teammate (not the author) answers.
    r2 = client.post(f"/api/v1/feedback/threads/{tid}/messages",
                     data={"body": "KFFEH2601C10 — confirmed on the M-sheet"},
                     headers=TEAMMATE)
    assert r2.status_code == 201
    d = r2.get_json()["data"]
    assert d["status"] == "answered"
    roles = [(m["role"], m["author_email"]) for m in d["messages"]]
    assert ("team", "gerald@procalcs.net") in roles
    assert ("tester", "dana@procalcs.net") in roles


def test_agent_never_posts_a_second_message(client):
    # Report with no screenshot → one nudge (counter burned).
    r = client.post("/api/v1/feedback/threads",
                    data={"kind": "report", "body": "duct count looks off"},
                    headers=DANA)
    tid = r.get_json()["data"]["id"]
    assert len(_agent_msgs(r.get_json()["data"])) == 1
    # Tester replies to the nudge — the agent must stay silent.
    r2 = client.post(f"/api/v1/feedback/threads/{tid}/messages",
                     data={"body": "here is more detail, no screenshot though"},
                     headers=DANA)
    d = r2.get_json()["data"]
    assert len(_agent_msgs(d)) == 1  # still exactly one — no loop


def test_list_and_resolve(client):
    client.post("/api/v1/feedback/threads",
                data={"kind": "report", "body": "a"}, headers=DANA)
    r = client.get("/api/v1/feedback/threads", headers=DANA)
    env = r.get_json()
    assert env["success"] is True
    assert env["data"]["open_count"] >= 1
    tid = env["data"]["threads"][0]["id"]
    rr = client.post(f"/api/v1/feedback/threads/{tid}/resolve",
                     json={"status": "resolved"}, headers=TEAMMATE)
    assert rr.status_code == 200
    assert rr.get_json()["data"]["status"] == "resolved"


def test_empty_submission_rejected(client):
    r = client.post("/api/v1/feedback/threads", data={"kind": "report"},
                    headers=DANA)
    assert r.status_code == 400
    assert r.get_json()["success"] is False
