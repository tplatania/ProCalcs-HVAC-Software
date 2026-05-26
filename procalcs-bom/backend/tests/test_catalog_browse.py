"""
Tests for /api/v1/bom/dfunit and /api/v1/bom/mappings — the catalog-
browser endpoints that back the SPA's DFUnit Explorer and Wrightsoft
Mapping Browser pages (Day-12).

These are read-only views over Tom's bundled catalog files. The tests
exercise the filter/facet contract against the real bundled data so
we catch any regression in the column-name plumbing.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        _w = MagicMock()
        _w.HTML = MagicMock()
        _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w

for _k, _v in (
    ('DATABASE_URL',         'sqlite:///:memory:'),
    ('ANTHROPIC_API_KEY',    'dev-test'),
    ('FIRESTORE_PROJECT_ID', 'dev-test'),
):
    if not os.environ.get(_k):
        os.environ[_k] = _v
os.environ['SERVICE_SHARED_SECRET'] = ''


@pytest.fixture
def client():
    from app import create_app
    from extensions import db
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


# ─── /dfunit ───────────────────────────────────────────────────────

def test_dfunit_returns_items_and_facets(client):
    r = client.get('/api/v1/bom/dfunit?limit=5')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success']
    data = body['data']
    assert data['returned'] == len(data['items']) == 5
    assert data['total'] > 100  # full DFUnit catalog has ~963 rows
    # Shape check on first item
    item = data['items'][0]
    for k in ('manufacturer', 'model', 'sys_type', 'unit_type',
              'cooling_btu', 'heating_btu', 'series'):
        assert k in item, f"missing key {k}"
    # Facets present and non-empty
    assert {'manufacturers', 'unit_types', 'sys_types'} <= set(data['facets'])
    assert 'CARR' in data['facets']['manufacturers']
    assert 'OS' in data['facets']['unit_types']


def test_dfunit_filter_by_manufacturer(client):
    r = client.get('/api/v1/bom/dfunit?manufacturer=CARR&limit=1000')
    body = r.get_json()['data']
    assert body['total'] > 0
    assert all(it['manufacturer'] == 'CARR' for it in body['items'])


def test_dfunit_capacity_range_filter(client):
    # Cooling capacity between 18,000 and 24,000 BTU — common residential.
    r = client.get('/api/v1/bom/dfunit?min_clg_btu=18000&max_clg_btu=24000&limit=1000')
    body = r.get_json()['data']
    assert body['total'] > 0
    for it in body['items']:
        assert it['cooling_btu'] is not None
        assert 18000 <= it['cooling_btu'] <= 24000


def test_dfunit_freetext_q_matches_model(client):
    # Carrier 38MARB series — known DFUnit prefix in Tom's catalog
    r = client.get('/api/v1/bom/dfunit?q=38MARB&limit=20')
    body = r.get_json()['data']
    assert body['total'] > 0
    assert all('38MARB' in (it['model'] or '').upper() for it in body['items'])


def test_dfunit_limit_clamped(client):
    r = client.get('/api/v1/bom/dfunit?limit=99999')
    body = r.get_json()['data']
    # 1000 ceiling — total may exceed but returned shouldn't
    assert body['returned'] <= 1000


# ─── /mappings ─────────────────────────────────────────────────────

def test_mappings_returns_items_and_facets(client):
    r = client.get('/api/v1/bom/mappings?limit=10')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success']
    data = body['data']
    assert data['returned'] == 10
    assert data['total'] > 1000  # full mapped_parts.csv ~4100 rows
    item = data['items'][0]
    for k in ('generic_id', 'description', 'category', 'supplier',
              'manufacturer_partnum', 'quantity_variant'):
        assert k in item
    assert 'WSF' in data['facets']['suppliers']


def test_mappings_filter_by_supplier(client):
    r = client.get('/api/v1/bom/mappings?supplier=WSF&limit=2000')
    body = r.get_json()['data']
    assert body['total'] > 0
    assert all(it['supplier'] == 'WSF' for it in body['items'])


def test_mappings_filter_by_generic_id_exact(client):
    # Use an arbitrary mapped generic — fetch one from facets first
    seed = client.get('/api/v1/bom/mappings?limit=1').get_json()['data']['items'][0]
    gid = seed['generic_id']
    r = client.get(f'/api/v1/bom/mappings?generic_id={gid}&limit=100')
    body = r.get_json()['data']
    assert body['total'] >= 1
    assert all(it['generic_id'].upper() == gid.upper() for it in body['items'])


def test_mappings_freetext_q_substring(client):
    r = client.get('/api/v1/bom/mappings?q=PEX&limit=500')
    body = r.get_json()['data']
    assert body['total'] > 0
    for it in body['items']:
        hay = ' '.join([
            it.get('generic_id') or '',
            it.get('manufacturer_partnum') or '',
            it.get('description') or '',
        ]).lower()
        assert 'pex' in hay
