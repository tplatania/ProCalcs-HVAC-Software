"""
Tests for the Wrightsoft bundle v1 schema — the interop contract
between Path A (structural .rup parser) and Path B (Windows COM
agent). See procalcs-catalog/docs/wrightsoft-bundle-schema-v1.md.

Fixture strategy: four canonical bundles under
tests/fixtures/wrightsoft_bundles/ exercise each valid
bundle_source. Validators run against them without touching the
network — pure JSON validation + adapter dispatch.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:  # noqa: BLE001
        _w = MagicMock(); _w.HTML = MagicMock(); _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "wrightsoft_bundles"

BUNDLE_FILES = [
    "sample_com_79th_ct_v1.json",
    "sample_com_ally_v1.json",
    "sample_rup_structural_79th_ct_v1.json",
    "sample_manual_minimal_v1.json",
]


def _load(name: str) -> dict:
    with (FIXTURE_DIR / name).open() as f:
        return json.load(f)


# ─── Schema-shape checks (producer-agnostic) ───────────────────────

@pytest.mark.parametrize("filename", BUNDLE_FILES)
def test_all_fixtures_are_valid_json(filename: str):
    """Every fixture parses as JSON."""
    bundle = _load(filename)
    assert isinstance(bundle, dict)


@pytest.mark.parametrize("filename", BUNDLE_FILES)
def test_all_fixtures_declare_v1(filename: str):
    """Version-tag is 'v1' on every fixture, verbatim."""
    bundle = _load(filename)
    assert bundle["bundle_schema_version"] == "v1"


@pytest.mark.parametrize("filename", BUNDLE_FILES)
def test_all_fixtures_have_required_top_level_keys(filename: str):
    """Required top-level keys per schema §2."""
    bundle = _load(filename)
    for key in ("bundle_source", "bundle_schema_version",
                "producer_metadata", "project",
                "line_items", "zones"):
        assert key in bundle, f"missing {key!r}"


@pytest.mark.parametrize("filename,expected_source", [
    ("sample_com_79th_ct_v1.json",              "com_extraction_station"),
    ("sample_com_ally_v1.json",                 "com_extraction_station"),
    ("sample_rup_structural_79th_ct_v1.json",   "rup_structural"),
    ("sample_manual_minimal_v1.json",           "manual_upload"),
])
def test_bundle_source_matches_expected(filename: str, expected_source: str):
    """Each fixture declares the bundle_source it's supposed to represent."""
    assert _load(filename)["bundle_source"] == expected_source


# ─── Line-item invariants ──────────────────────────────────────────

@pytest.mark.parametrize("filename", BUNDLE_FILES)
def test_line_items_have_required_fields(filename: str):
    """Each line item has part_no + quantity (required per §3)."""
    for li in _load(filename)["line_items"]:
        assert li.get("part_no"), f"missing part_no: {li!r}"
        assert "quantity" in li, f"missing quantity: {li!r}"
        assert isinstance(li["quantity"], (int, float))


def test_com_bundle_line_items_are_priced():
    """§5 producer contract: COM bundles carry authoritative unit_price."""
    for name in ("sample_com_79th_ct_v1.json", "sample_com_ally_v1.json"):
        for li in _load(name)["line_items"]:
            # Zero prices are allowed (catalog gaps) but the field must be present
            assert "unit_price" in li, (
                f"{name}: COM bundles must include unit_price per §5")


def test_rup_structural_bundle_line_items_are_unpriced():
    """§5 producer contract: rup_structural bundles emit prices=null so
    consumer knows to fill from the hosted catalog."""
    for li in _load("sample_rup_structural_79th_ct_v1.json")["line_items"]:
        assert li.get("unit_price") is None, (
            "rup_structural line_items must not carry unit_price — "
            "the consumer fills prices via /api/v1/catalog/wrightsoft/"
            "pricing-for-part")


# ─── Zone invariants ───────────────────────────────────────────────

@pytest.mark.parametrize("filename", BUNDLE_FILES)
def test_zones_have_zone_name(filename: str):
    """Zone identifier is required."""
    for zone in _load(filename)["zones"]:
        assert zone.get("zone_name"), f"missing zone_name: {zone!r}"


def test_ally_backup_heat_captured_verbatim():
    """Ally has two zones with backup heat — model strings must include
    the literal punctuation from Wrightsoft (no normalization)."""
    bundle = _load("sample_com_ally_v1.json")
    backup_models = {z["backup_heat"]["model"]
                     for z in bundle["zones"] if z.get("backup_heat")}
    assert "BAYEA(13/AC)08++1" in backup_models
    assert "BAYEA(13/AC)10++1" in backup_models


def test_mitsubishi_masking_preserved():
    """§4 preserves the *** masking Wrightsoft uses on Mitsubishi model
    numbers verbatim — no unicode substitution, no normalization."""
    bundle = _load("sample_com_79th_ct_v1.json")
    mitsu_zone = next(z for z in bundle["zones"]
                      if z["zone_name"] == "AHU - 5")
    assert mitsu_zone["cooling"]["condenser_model"].endswith("***")
    assert mitsu_zone["cooling"]["coil_model"].endswith("***")


# ─── Producer-metadata / provenance ────────────────────────────────

@pytest.mark.parametrize("filename", BUNDLE_FILES)
def test_producer_metadata_has_expected_keys(filename: str):
    """§2 requires producer_metadata dict with these keys present (may
    be null but must exist)."""
    md = _load(filename)["producer_metadata"]
    for key in ("wrightsoft_version", "catalog_version", "catalog_schemas",
                "producer_hostname", "producer_id", "extracted_at"):
        assert key in md, f"producer_metadata missing {key!r}"


def test_com_bundle_metadata_populated():
    """COM bundles should have real producer_metadata (they came from a
    live extraction). Rup_structural + manual can leave null fields."""
    for name in ("sample_com_79th_ct_v1.json", "sample_com_ally_v1.json"):
        md = _load(name)["producer_metadata"]
        assert md["wrightsoft_version"] is not None
        assert md["catalog_version"] is not None
        assert md["producer_hostname"] is not None
