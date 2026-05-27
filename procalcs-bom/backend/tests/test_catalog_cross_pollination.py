"""
Tests for the Day-12 catalog cross-pollination pass in bom_service —
the verifier that retags AI-emitted lines whose SKUs we can confirm
against Tom's bundled Wrightsoft catalog (DFUnit.csv +
mapped_parts.csv).

Why this exists: Gerald ran a .rup through the BOM Engine and every
single line was tagged 'AI', even though most of the AI-emitted SKUs
exist in the bundled mapping. The verifier closes that gap without
rewriting the prompt or the AI pipeline — it's a post-processing
step over priced_items.
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
        _w = MagicMock(); _w.HTML = MagicMock(); _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w

from services.bom_service import _verify_against_wrightsoft_catalog
from services import wrightsoft_catalog as wsc


# ─── Fixtures ──────────────────────────────────────────────────────

def _known_mapped_sku():
    """Pick a real (sku, generic_item, supplier) triple from
    mapped_parts.csv so tests stay valid as the catalog evolves."""
    rows = wsc.load_mapped_parts()
    for r in rows:
        sku = (r.get("manufacturer_partnum") or "").strip()
        if sku:
            return sku, r["generic_item"], r["preferred_source"]
    pytest.fail("mapped_parts.csv must contain at least one SKU for tests")


def _known_dfunit_model():
    rows = wsc.load_dfunit()
    for r in rows:
        model = (r.get("Model") or "").strip()
        if model:
            return model, r.get("Manufacturer")
    pytest.fail("DFUnit.csv must contain at least one model for tests")


# ─── DFUnit verification ───────────────────────────────────────────

def test_dfunit_sku_promotes_ai_to_catalog_verified_dfunit():
    sku, manufacturer = _known_dfunit_model()
    lines = [{
        "sku":         sku,
        "description": "Some AI guess",
        "quantity":    1,
        "source":      "ai_with_catalog_sku",
    }]
    promoted = _verify_against_wrightsoft_catalog(lines)
    assert promoted == 1
    assert lines[0]["source"] == "catalog_verified_dfunit"
    # DFUnit spec attached for the SPA + PDF to consume
    assert "dfunit_spec" in lines[0]
    # Manufacturer filled in from spec when blank
    assert lines[0]["manufacturer"] == manufacturer


def test_dfunit_promotion_does_not_overwrite_existing_manufacturer():
    sku, _ = _known_dfunit_model()
    lines = [{
        "sku":           sku,
        "manufacturer":  "EXISTING",
        "source":        "ai_inferred",
        "quantity":      1,
    }]
    _verify_against_wrightsoft_catalog(lines)
    assert lines[0]["manufacturer"] == "EXISTING"


# ─── mapped_parts verification ─────────────────────────────────────

def test_mapped_sku_promotes_ai_to_catalog_verified_mapped():
    sku, generic, supplier = _known_mapped_sku()
    lines = [{
        "sku":         sku,
        "description": "AI guess",
        "quantity":    5,
        "source":      "ai_inferred",
    }]
    promoted = _verify_against_wrightsoft_catalog(lines)
    assert promoted == 1
    assert lines[0]["source"] == "catalog_verified_mapped"
    assert lines[0]["generic_id"] == generic
    assert lines[0]["manufacturer"] == supplier


def test_lookup_mapping_by_sku_returns_none_for_unknown():
    assert wsc.lookup_mapping_by_sku("DEFINITELY_NOT_A_REAL_SKU_XYZ") is None
    assert wsc.lookup_mapping_by_sku("") is None
    assert wsc.lookup_mapping_by_sku(None) is None


# ─── Source-preservation contract ──────────────────────────────────

def test_verifier_skips_lines_with_no_sku():
    lines = [{"description": "no sku here", "source": "ai_inferred", "quantity": 1}]
    promoted = _verify_against_wrightsoft_catalog(lines)
    assert promoted == 0
    assert lines[0]["source"] == "ai_inferred"


def test_verifier_does_not_clobber_already_verified_sources():
    """catalog_match / rules_engine / wrightsoft_* lines already have
    a trustworthy provenance — the verifier must leave them alone."""
    sku, _, _ = _known_mapped_sku()
    lines = [
        {"sku": sku, "source": "catalog_match",   "quantity": 1},
        {"sku": sku, "source": "rules_engine",    "quantity": 1},
        {"sku": sku, "source": "wrightsoft_mapped","quantity": 1},
        {"sku": sku, "source": "wrightsoft_dfunit","quantity": 1},
        {"sku": sku, "source": "wrightsoft_passthrough","quantity": 1},
    ]
    promoted = _verify_against_wrightsoft_catalog(lines)
    assert promoted == 0
    assert lines[0]["source"] == "catalog_match"
    assert lines[1]["source"] == "rules_engine"
    assert lines[2]["source"] == "wrightsoft_mapped"


def test_verifier_skips_ai_lines_with_unknown_skus():
    lines = [{
        "sku":         "PROBABLY_AI_HALLUCINATED_SKU",
        "source":      "ai_inferred",
        "quantity":    1,
    }]
    promoted = _verify_against_wrightsoft_catalog(lines)
    assert promoted == 0
    assert lines[0]["source"] == "ai_inferred"


def test_verifier_mixed_batch_promotes_only_matches():
    mapped_sku, _, _ = _known_mapped_sku()
    dfunit_sku, _ = _known_dfunit_model()
    lines = [
        {"sku": mapped_sku,  "source": "ai_inferred",        "quantity": 1},
        {"sku": dfunit_sku,  "source": "ai_with_catalog_sku","quantity": 1},
        {"sku": "fake_sku",  "source": "ai_inferred",        "quantity": 1},
        {"sku": "",          "source": "ai_inferred",        "quantity": 1},
        {"description": "no sku", "source": "ai_inferred",   "quantity": 1},
    ]
    promoted = _verify_against_wrightsoft_catalog(lines)
    assert promoted == 2
    sources = [l["source"] for l in lines]
    assert sources == [
        "catalog_verified_mapped",
        "catalog_verified_dfunit",
        "ai_inferred",
        "ai_inferred",
        "ai_inferred",
    ]
