"""test_chat_messages.py — Day-27 persistent chat (save/resume)."""
import sys, os
from unittest.mock import MagicMock
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
if "weasyprint" not in sys.modules:
    try: import weasyprint  # noqa
    except Exception:
        _w=MagicMock(); _w.HTML=MagicMock(); _w.CSS=MagicMock(); sys.modules["weasyprint"]=_w
os.environ.setdefault('DATABASE_URL','sqlite:///:memory:')
os.environ.setdefault('ANTHROPIC_API_KEY','dev-test')
os.environ.setdefault('FIRESTORE_PROJECT_ID','dev-test')
os.environ.setdefault('SERVICE_SHARED_SECRET','')
from app import create_app
from extensions import db
from models import BomRun, ChatMessage

@pytest.fixture
def app():
    a=create_app(); a.config['TESTING']=True
    with a.app_context():
        db.create_all(); yield a; db.session.remove(); db.drop_all()

@pytest.fixture
def client(app): return app.test_client()

@pytest.fixture
def run_id(app):
    with app.app_context():
        r=BomRun.record(client_id="c1",job_id="j1",output_mode="full",
                        parsed_design_data={},generated_bom={"line_items":[]})
        db.session.commit(); return r.id

def test_append_then_get_roundtrip(client, run_id):
    r=client.post(f"/api/v1/bom-runs/{run_id}/chat", json={"turns":[
        {"role":"user","content":"why is the 3-in duct $0?","attachments":[{"name":"px.xls","kind":"file"}]},
        {"role":"assistant","content":"No Wrightsoft price — enter yours.","actions":[{"kind":"propose_line_update","sku":"10-00-190"}]},
    ]}, headers={"X-Procalcs-User-Email":"richard@reliableheating.team"})
    assert r.status_code==200 and r.get_json()["data"]["saved"]==2
    got=client.get(f"/api/v1/bom-runs/{run_id}/chat").get_json()["data"]["messages"]
    assert [m["role"] for m in got]==["user","assistant"]
    assert got[0]["author_email"]=="richard@reliableheating.team"
    assert got[0]["attachments"]==[{"name":"px.xls","kind":"file"}]
    assert got[1]["actions"][0]["sku"]=="10-00-190"
    assert got[1]["author_email"] is None  # assistant turns carry no author

def test_appends_accumulate(client, run_id):
    for i in range(3):
        client.post(f"/api/v1/bom-runs/{run_id}/chat", json={"turns":[{"role":"user","content":f"m{i}"}]})
    assert len(client.get(f"/api/v1/bom-runs/{run_id}/chat").get_json()["data"]["messages"])==3

def test_author_from_header_not_body(client, run_id):
    client.post(f"/api/v1/bom-runs/{run_id}/chat", json={"turns":[
        {"role":"user","content":"x","author_email":"spoofed@evil.com"}]},
        headers={"X-Procalcs-User-Email":"real@reliableheating.team"})
    got=client.get(f"/api/v1/bom-runs/{run_id}/chat").get_json()["data"]["messages"]
    assert got[0]["author_email"]=="real@reliableheating.team"

def test_validation_and_404(client, run_id):
    assert client.post(f"/api/v1/bom-runs/{run_id}/chat", json={"turns":[]}).status_code==400
    assert client.post("/api/v1/bom-runs/99999/chat", json={"turns":[{"role":"user","content":"x"}]}).status_code==404
    assert client.get("/api/v1/bom-runs/99999/chat").status_code==404

def test_bad_roles_skipped(client, run_id):
    r=client.post(f"/api/v1/bom-runs/{run_id}/chat", json={"turns":[
        {"role":"system","content":"nope"},{"role":"user","content":"ok"}]})
    assert r.get_json()["data"]["saved"]==1
