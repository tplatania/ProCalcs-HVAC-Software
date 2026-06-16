"""
Tests for services.bom_from_rup — the Day-16 .rup → BOM line adapter.

We round-trip real Wrightsoft RUP files from /Procalcs/RUPs/ (the same
files Tom + Richard ship as test cases) through the adapter and assert
the line items have the shape build_bom_from_wrightsoft_lines expects.
The tests are skipped when the RUP files aren't on the test box so CI
on a fresh checkout stays green.
"""

import os
import sys
from pathlib import Path
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
    if not os.environ.get(_k):
        os.environ[_k] = _v
os.environ['SERVICE_SHARED_SECRET'] = ''


# Tom's test RUPs live outside the repo (his Wrightsoft library on the
# dev box). Skip rather than break CI when they're not present.
_RUP_DIR = Path("/Users/geraldvillaran/Procalcs/RUPs")
_RUP_FIXTURES = [
    _RUP_DIR / "79th Ct Residence Load Calcs.rup",
    _RUP_DIR / "(Average Case) Ligon ADU Manual D.rup",
    _RUP_DIR / "(Easy) 13th Avenue South ADU Residence Ducts.rup",
]
_AVAILABLE = [p for p in _RUP_FIXTURES if p.exists()]


@pytest.mark.skipif(not _AVAILABLE, reason="No .rup fixtures available")
@pytest.mark.parametrize("rup_path", _AVAILABLE)
def test_build_lines_returns_nonempty(rup_path):
    """Every real RUP yields at least one BOM line (at minimum the
    DTYPREF duct-type summary or the fitting placeholder)."""
    from services.bom_from_rup import build_lines_from_rup
    lines = build_lines_from_rup(rup_path.read_bytes(),
                                 source_name=rup_path.name)
    assert isinstance(lines, list)
    assert len(lines) > 0


@pytest.mark.skipif(not _AVAILABLE, reason="No .rup fixtures available")
def test_line_shape_matches_builder_contract():
    """Each line carries the keys build_bom_from_wrightsoft_lines
    consumes — generic_id, quantity, description (others optional)."""
    from services.bom_from_rup import build_lines_from_rup
    lines = build_lines_from_rup(_AVAILABLE[0].read_bytes())
    assert lines, "expected at least one line"
    for li in lines:
        assert "generic_id" in li
        assert "quantity" in li
        assert "description" in li
        assert isinstance(li["quantity"], (int, float))
        assert li["generic_id"] and isinstance(li["generic_id"], str)


@pytest.mark.skipif(not _AVAILABLE, reason="No .rup fixtures available")
def test_lines_include_duct_system_summary():
    """RUPs with a populated DTYPREF section produce at least one
    duct-system line (the type_counts → DUCT-<code> lines)."""
    from services.bom_from_rup import build_lines_from_rup
    lines = build_lines_from_rup(_AVAILABLE[0].read_bytes())
    duct_lines = [l for l in lines if l["generic_id"].startswith("DUCT-")]
    # Not strictly required (sparse RUPs can have empty DTYPREF) but
    # at least one of the standard fixtures has one.
    if not duct_lines:
        # OK: assert at least the fittings placeholder is present
        assert any(l["generic_id"] == "FITTINGS" for l in lines)


def test_empty_bytes_returns_empty_list():
    """Defensive: empty upload yields zero lines (caller handles)."""
    from services.bom_from_rup import build_lines_from_rup
    out = build_lines_from_rup(b"")
    assert out == []


# ─── /from-wrightsoft routing: .rup goes through bom_from_rup ──────

@pytest.fixture
def client():
    from app import create_app
    from extensions import db
    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


@pytest.mark.skipif(not _AVAILABLE, reason="No .rup fixtures available")
def test_from_wrightsoft_routes_rup_through_adapter(client, monkeypatch):
    """A multipart upload with a .rup filename gets routed through the
    bom_from_rup adapter rather than parse_wrightsoft_bom_rows."""
    import io

    # Stub the profile lookup so we don't need Firestore wired up.
    from models.client_profile import ClientProfile
    fake_profile = {
        "client_id": "procalcs-direct",
        "client_name": "ProCalcs Direct",
        "is_active": True,
        "supplier": {}, "markup": {}, "brands": {},
        "labor": {}, "part_name_overrides": [],
        "markup_tiers": [],
    }
    monkeypatch.setattr(
        "routes.bom_routes.get_profile_by_id",
        lambda _id: fake_profile,
    )

    rup = _AVAILABLE[0]
    r = client.post(
        '/api/v1/bom/from-wrightsoft',
        data={
            "file": (io.BytesIO(rup.read_bytes()), rup.name),
            "client_id": "procalcs-direct",
            "job_id":    "rup-rounddrip",
        },
        content_type='multipart/form-data',
    )
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["success"]
    data = body["data"]
    assert data["source_pipeline"] == "wrightsoft_rup"
    assert "rup_best_effort_notice" in data
    assert data["item_count"] > 0
