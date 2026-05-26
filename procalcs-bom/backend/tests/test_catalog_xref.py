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


# ─── /parse-rup now bundles the xref (Day-10 follow-up) ─────────────

class TestParseRupBundlesXref:
    """The BOM Engine SPA depends on parse-rup returning catalog_xref
    so it can route to the deterministic pipeline before kicking off
    AI estimation. Lock the contract here."""

    def _make_minimal_rup(self) -> bytes:
        """Synthetic blob that satisfies the .WSrsu.WSF magic + has
        enough zero-bytes padding that parse_rup_bytes doesn't blow
        up on a too-short buffer."""
        magic = ".WSrsu.WSF.0004.APP=Test".encode("utf-16-le")
        return magic + b"\x00" * 4096

    def test_parse_rup_response_includes_catalog_xref(self):
        import io
        from app import create_app
        app = create_app()
        client = app.test_client()

        resp = client.post(
            "/api/v1/bom/parse-rup",
            data={"file": (io.BytesIO(self._make_minimal_rup()), "smoke.rup")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()["data"]
        assert "catalog_xref" in data
        xref = data["catalog_xref"]
        assert xref["bom_is_in_binary"] is False
        assert xref["generic_ids_found"] == 0
        assert ("from-wrightsoft" in xref["recommendation"]
                or "Bill of Materials" in xref["recommendation"])
