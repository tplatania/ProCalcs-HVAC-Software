"""Tests for _catalog_xref_for_binary added to bom_routes.py."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from unittest.mock import MagicMock
for mod in ("anthropic", "weasyprint"):
    if mod not in sys.modules: sys.modules[mod] = MagicMock()
if "google.cloud.firestore" not in sys.modules:
    g = MagicMock(); g.cloud = MagicMock(); g.cloud.firestore = MagicMock()
    sys.modules.setdefault("google", g); sys.modules.setdefault("google.cloud", g.cloud)
    sys.modules["google.cloud.firestore"] = g.cloud.firestore

from routes.bom_routes import _catalog_xref_for_binary


class TestCatalogXref:
    def test_empty_binary_returns_zero_hits_and_recommends_export(self):
        x = _catalog_xref_for_binary(b"\x00" * 1024)
        assert x["bom_is_in_binary"] is False
        assert x["generic_ids_in_catalog"] > 1000  # 3014 today
        assert x["generic_ids_found"] == 0
        # Recommendation steers toward the deterministic pipeline
        assert "from-wrightsoft" in x["recommendation"] or \
               "Bill of Materials" in x["recommendation"]

    def test_synthetic_binary_with_known_generic_id_finds_it(self):
        data = "PEX0750".encode("utf-16-le") + b"\x00" * 100
        x = _catalog_xref_for_binary(data)
        assert x["generic_ids_found"] >= 1
        assert "PEX0750" in x["found_sample"]

    def test_below_25_percent_threshold_stays_false(self):
        """Even with a couple of catalog hits, BOM-in-binary stays
        False until we cross the threshold. Wrightsoft files we've
        seen never come close."""
        data = ("PEX0750 BPERT1000 ".encode("utf-16-le")) * 5
        x = _catalog_xref_for_binary(data)
        assert x["bom_is_in_binary"] is False

    def test_found_sample_capped_at_10(self):
        ids = "PEX0750 PEX0500 BPERT1000 BPERT0750 BPERT0500 ".encode("utf-16-le")
        data = ids * 10  # many hits but bounded distinct count
        x = _catalog_xref_for_binary(data)
        assert len(x["found_sample"]) <= 10
