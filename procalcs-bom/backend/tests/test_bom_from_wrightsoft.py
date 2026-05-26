"""
Tests for services.bom_from_wrightsoft — Day-9 ingestion of
Wrightsoft's own generic-parts BOM listing.

These tests use the real Wrightsoft catalog CSVs bundled in
backend/data/wrightsoft_catalog/ so we exercise the actual mapping
table (4,112 mapped parts across 3,014 distinct generics) — not a
mock. Keeps the test surface honest: if Tom updates the mapping, the
tests pick up the new data automatically.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# create_app() (used by the coverage-endpoint test) imports
# pdf_service → weasyprint. Stub locally — global conftest stubbing
# would break test_pdf_service.py's pytest.importorskip("weasyprint").
if "weasyprint" not in sys.modules:
    try:
        import weasyprint  # noqa: F401
    except Exception:  # noqa: BLE001
        _w = MagicMock(); _w.HTML = MagicMock(); _w.CSS = MagicMock()
        sys.modules["weasyprint"] = _w

from models.client_profile import (
    ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences,
)
from services.bom_from_wrightsoft import (
    build_bom_from_wrightsoft_lines,
    parse_wrightsoft_bom_rows,
    _supplier_pref_for,
    _category_to_line_category,
)
from services import wrightsoft_catalog as wsc


@pytest.fixture
def minimal_profile():
    """Bare-bones profile for the ingestion path. The QST supplier
    code matches a real Wrightsoft 4-char source so supplier-pref
    filtering exercises a real lookup."""
    return ClientProfile(
        client_id="test-c",
        client_name="Test Contractor",
        supplier=SupplierInfo(
            supplier_name="QST",
            flex_duct_cost_per_foot=1.10,
        ),
        markup=MarkupTiers(
            equipment_pct=15.0,
            materials_pct=20.0,
            consumables_pct=25.0,
        ),
        brands=BrandPreferences(),
        part_name_overrides=[],
    )


@pytest.fixture
def goodman_profile():
    """Profile whose contractor prefers Goodman — verified to exist in
    the manufacturers.csv (source code GOOD)."""
    return ClientProfile(
        client_id="goodman-c",
        client_name="Goodman Test",
        supplier=SupplierInfo(supplier_name="Goodman"),
        markup=MarkupTiers(equipment_pct=10.0, materials_pct=15.0,
                           consumables_pct=20.0),
        brands=BrandPreferences(ac_brand="Goodman"),
        part_name_overrides=[],
    )


# ─── _supplier_pref_for ─────────────────────────────────────────────

class TestSupplierPref:
    def test_returns_direct_4char_code_when_supplier_name_is_one(self, minimal_profile):
        """When SupplierInfo.supplier_name is already a 4-char Wrightsoft
        source code, return it verbatim (uppercased)."""
        assert _supplier_pref_for(minimal_profile) == "QST"

    def test_returns_code_when_supplier_name_is_full_name(self, goodman_profile):
        """When SupplierInfo.supplier_name is the human brand name
        ('Goodman'), match against the manufacturers.csv Name column
        to recover the 4-char code. Wrightsoft stores "Goodman Mfg."
        (with the suffix) so a startswith match is what's expected."""
        pref = _supplier_pref_for(goodman_profile)
        known = wsc.load_manufacturers()
        assert pref in known
        # The manufacturer name should start with our candidate
        assert known[pref]["Name"].lower().startswith("goodman")

    def test_returns_none_when_no_supplier_match(self):
        from models.client_profile import ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences
        p = ClientProfile(
            client_id="x", client_name="x",
            supplier=SupplierInfo(supplier_name="Acme Supply (unknown)"),
            markup=MarkupTiers(), brands=BrandPreferences(),
            part_name_overrides=[],
        )
        assert _supplier_pref_for(p) is None


# ─── _category_to_line_category ────────────────────────────────────

class TestCategoryMap:
    def test_duct_categories(self):
        assert _category_to_line_category("DSRCT") == "duct"
        assert _category_to_line_category("DSRND") == "duct"
        assert _category_to_line_category("HVDALL") == "duct"

    def test_fitting_categories(self):
        assert _category_to_line_category("DFRELB") == "fitting"
        assert _category_to_line_category("DFRTEE") == "fitting"
        assert _category_to_line_category("DFRTRS") == "fitting"

    def test_register_category(self):
        assert _category_to_line_category("DFRBTR") == "register"

    def test_equipment_categories(self):
        assert _category_to_line_category("EACCESSY") == "equipment"
        assert _category_to_line_category("HVACCTLS") == "equipment"
        assert _category_to_line_category("MSRP") == "equipment"

    def test_unknown_falls_back_to_other(self):
        assert _category_to_line_category("MYSTERY") == "other"
        assert _category_to_line_category(None) == "other"
        assert _category_to_line_category("") == "other"


# ─── build_bom_from_wrightsoft_lines — happy path ──────────────────

class TestBuildBom:
    def test_emits_mapped_lines_with_manufacturer_skus(self, minimal_profile):
        """The headline path: feed in real Wrightsoft generic IDs, get
        back lines with real manufacturer part numbers from
        mapped_parts.csv."""
        bom = build_bom_from_wrightsoft_lines(
            lines=[
                {"generic_id": "PEX0750", "quantity": 100},
                {"generic_id": "BPERT1000", "quantity": 50},
            ],
            profile=minimal_profile,
            job_id="test-job",
        )
        assert bom["item_count"] == 2
        assert bom["source_pipeline"] == "wrightsoft_bom"
        assert bom["wrightsoft_mapped_item_count"] == 2
        assert bom["wrightsoft_unmapped_item_count"] == 0

        # First line — PEX0750 with QST supplier preference active
        pex = bom["line_items"][0]
        assert pex["generic_id"] == "PEX0750"
        assert pex["source"] == "wrightsoft_mapped"
        assert pex["manufacturer"] == "QST"
        # Real PEX0750 → QST mapping is one of: Q4PC100XRED, Q4PC500XRED, Q4PC1000XRED
        assert pex["sku"].startswith("Q4PC")
        assert pex["quantity"] == 100

    def test_unmapped_generic_emits_flag_for_backlog(self, minimal_profile):
        """Generic IDs that aren't in mapped_parts.csv emit as
        'wrightsoft_unmapped' lines — the SKU Backlog page picks
        these up so Richard's team can prioritize what to add to
        the mapping."""
        bom = build_bom_from_wrightsoft_lines(
            lines=[
                {"generic_id": "TOTALLY-FAKE-GENERIC-12345",
                 "quantity": 5, "description": "Mystery part"},
            ],
            profile=minimal_profile,
            job_id="test-job",
        )
        assert bom["wrightsoft_unmapped_item_count"] == 1
        line = bom["line_items"][0]
        assert line["source"] == "wrightsoft_unmapped"
        assert "sku" not in line
        # generic_id is preserved so the backlog page can group it
        assert line["generic_id"] == "TOTALLY-FAKE-GENERIC-12345"
        # Description from the caller is kept since catalog has nothing
        assert line["description"] == "Mystery part"

    def test_description_prefers_catalog_over_caller(self, minimal_profile):
        """Wrightsoft's catalog description is authoritative — it's
        what contractors expect to see on the BOM. Caller-supplied
        description is the fallback."""
        bom = build_bom_from_wrightsoft_lines(
            lines=[{"generic_id": "PEX0750", "quantity": 100,
                    "description": "Wrong description"}],
            profile=minimal_profile,
            job_id="t",
        )
        # The catalog's Description column wins
        assert bom["line_items"][0]["description"] != "Wrong description"
        assert bom["line_items"][0]["description"]  # non-empty

    def test_routes_to_contractor_section(self, minimal_profile):
        """Each line gets a section assigned via the Wrightsoft
        category → contractor section mapping. PEX0750 (RHALL category)
        routes to Equipment per wrightsoft_catalog._CATEGORY_TO_SECTION."""
        bom = build_bom_from_wrightsoft_lines(
            lines=[{"generic_id": "PEX0750", "quantity": 100}],
            profile=minimal_profile,
            job_id="t",
        )
        # Whatever the routed section is, it's one of the canonical four
        assert bom["line_items"][0]["section"] in wsc.all_sections() + [wsc.SECTION_OTHER]

    def test_zero_quantity_lines_dropped(self, minimal_profile):
        """Wrightsoft sometimes emits placeholder zero-qty rows; emitting
        them as $0 BOM lines is noise."""
        bom = build_bom_from_wrightsoft_lines(
            lines=[
                {"generic_id": "PEX0750", "quantity": 100},
                {"generic_id": "PEX0750", "quantity": 0},
                {"generic_id": "PEX0500", "quantity": -1},  # nonsense
            ],
            profile=minimal_profile,
            job_id="t",
        )
        assert bom["item_count"] == 1

    def test_missing_generic_id_skipped(self, minimal_profile):
        """Empty/missing generic_id → row dropped silently. Caller's
        responsibility to validate inputs upstream."""
        bom = build_bom_from_wrightsoft_lines(
            lines=[
                {"generic_id": "", "quantity": 5},
                {"quantity": 10},
                {"generic_id": "PEX0750", "quantity": 100},
            ],
            profile=minimal_profile,
            job_id="t",
        )
        assert bom["item_count"] == 1

    def test_totals_aggregate_across_lines(self, minimal_profile):
        bom = build_bom_from_wrightsoft_lines(
            lines=[
                {"generic_id": "PEX0750", "quantity": 100},
                {"generic_id": "TOTALLY-FAKE-12345", "quantity": 5,
                 "description": "Mystery"},
            ],
            profile=minimal_profile,
            job_id="t",
        )
        manual_cost  = sum(li["total_cost"]  for li in bom["line_items"])
        manual_price = sum(li["total_price"] for li in bom["line_items"])
        assert abs(bom["totals"]["total_cost"]  - manual_cost)  < 0.01
        assert abs(bom["totals"]["total_price"] - manual_price) < 0.01

    def test_response_shape_matches_existing_bom_endpoint(self, minimal_profile):
        """The downstream consumers (PDF, comparator, run-history SPA)
        all expect a specific shape. New ingestion path must produce
        the same top-level keys so they don't need special-casing."""
        bom = build_bom_from_wrightsoft_lines(
            lines=[{"generic_id": "PEX0750", "quantity": 100}],
            profile=minimal_profile,
            job_id="shape-check",
            output_mode="full",
        )
        # Required keys downstream consumers depend on
        for key in ("job_id", "client_id", "client_name", "output_mode",
                    "generated_at", "supplier", "line_items", "totals",
                    "item_count"):
            assert key in bom, f"missing required key: {key}"
        # Provenance keys with same vocabulary as /generate output
        for key in ("catalog_match_item_count", "rules_engine_item_count",
                    "ai_item_count"):
            assert key in bom
        # Day-9 marker
        assert bom["source_pipeline"] == "wrightsoft_bom"

    def test_empty_input_returns_empty_bom_not_crash(self, minimal_profile):
        bom = build_bom_from_wrightsoft_lines(
            lines=[], profile=minimal_profile, job_id="empty",
        )
        assert bom["item_count"] == 0
        assert bom["line_items"] == []
        assert bom["totals"] == {"total_cost": 0, "total_price": 0}


# ─── parse_wrightsoft_bom_rows — CSV ingestion ─────────────────────

class TestParseCsv:
    def test_parses_standard_csv_with_item_qty_columns(self):
        csv = b"Item,Qty,Description\nPEX0750,100,1/2-in PEX Tubing\nBPERT1000,50,1-in Barrier Tubing\n"
        rows = parse_wrightsoft_bom_rows(csv, filename="bom.csv")
        assert len(rows) == 2
        assert rows[0]["generic_id"] == "PEX0750"
        assert rows[0]["quantity"] == 100.0
        assert rows[0]["description"] == "1/2-in PEX Tubing"
        assert rows[1]["generic_id"] == "BPERT1000"
        assert rows[1]["quantity"] == 50.0

    def test_tolerates_alias_column_names(self):
        """generic_id / quantity columns might be named differently
        across Wrightsoft versions. Parser tries common aliases."""
        csv = b"generic_id,quantity,desc\nPEX0500,25,half-inch\n"
        rows = parse_wrightsoft_bom_rows(csv, filename="alt.csv")
        assert len(rows) == 1
        assert rows[0]["generic_id"] == "PEX0500"
        assert rows[0]["quantity"] == 25.0

    def test_skips_header_preamble_rows(self):
        """Wrightsoft sometimes emits a title / project-name banner
        in the first few rows before the column-header row."""
        csv = b"Project: McGinty Residence\nDate: 2026-05-22\n\nItem,Qty,Description\nPEX0750,100,desc\n"
        rows = parse_wrightsoft_bom_rows(csv, filename="bom.csv")
        assert len(rows) == 1
        assert rows[0]["generic_id"] == "PEX0750"

    def test_handles_utf8_bom_in_csv(self):
        """Wrightsoft writes UTF-8 with BOM on its CSV exports — same
        pattern as the bundled mapped_parts.csv."""
        csv = "﻿Item,Qty,Description\nPEX0750,100,desc\n".encode("utf-8")
        rows = parse_wrightsoft_bom_rows(csv, filename="bom.csv")
        assert len(rows) == 1
        assert rows[0]["generic_id"] == "PEX0750"

    def test_drops_rows_with_blank_generic_id(self):
        csv = b"Item,Qty,Description\nPEX0750,100,a\n,50,no-id\nBPERT1000,25,b\n"
        rows = parse_wrightsoft_bom_rows(csv, filename="bom.csv")
        assert len(rows) == 2
        assert [r["generic_id"] for r in rows] == ["PEX0750", "BPERT1000"]

    def test_tolerates_short_rows(self):
        """Some Wrightsoft rows have missing trailing cells. Parser
        treats missing cells as empty rather than IndexError-ing."""
        csv = b"Item,Qty,Description\nPEX0750,100\n"  # description missing
        rows = parse_wrightsoft_bom_rows(csv, filename="bom.csv")
        assert len(rows) == 1
        assert rows[0]["description"] == ""

    def test_raises_valueerror_when_no_header_found(self):
        csv = b"random,nonsense,bytes\nfoo,bar,baz\n"
        with pytest.raises(ValueError, match="header"):
            parse_wrightsoft_bom_rows(csv, filename="bom.csv")

    def test_raises_valueerror_on_empty_input(self):
        with pytest.raises(ValueError, match="Empty"):
            parse_wrightsoft_bom_rows(b"", filename="x.csv")

    def test_raises_valueerror_on_unrecognized_format(self):
        # Binary blob that's neither CSV/XLS/XLSX
        with pytest.raises(ValueError, match="Unrecognized"):
            parse_wrightsoft_bom_rows(b"\xff\xfe\x00\x01garbage", filename="x.bin")

    def test_non_numeric_quantity_becomes_zero(self):
        csv = b"Item,Qty,Description\nPEX0750,not-a-number,a\n"
        rows = parse_wrightsoft_bom_rows(csv, filename="bom.csv")
        assert rows[0]["quantity"] == 0.0


# ─── DFUnit equipment-library integration (Day-11) ──────────────────

class TestDFUnitIntegration:
    """When a Wrightsoft BOM line's generic_id matches a DFUnit
    model number, the deterministic pipeline emits an equipment line
    enriched with full unit specs from DFUnit.csv (capacity,
    dimensions, weight, sys_type, unit_type)."""

    def test_dfunit_match_emits_equipment_line_with_full_spec(self, minimal_profile):
        # 38MARBQ24AA3 = Carrier 24,000 BTU outdoor heat-pump split
        bom = build_bom_from_wrightsoft_lines(
            lines=[{"generic_id": "38MARBQ24AA3", "quantity": 1}],
            profile=minimal_profile,
            job_id="dfunit-direct",
        )
        assert bom["item_count"] == 1
        assert bom["wrightsoft_dfunit_item_count"] == 1
        # DFUnit hits count as mapped too — overall mapped includes DFUnit
        assert bom["wrightsoft_mapped_item_count"] == 1
        line = bom["line_items"][0]
        assert line["source"] == "wrightsoft_dfunit"
        # Authoritative manufacturer + model from DFUnit row
        assert line["manufacturer"] == "CARR"
        assert line["sku"] == "38MARBQ24AA3"
        assert line["category"] == "equipment"
        # Spec dict attached for PDF / SPA display
        spec = line["dfunit_spec"]
        assert spec["cooling_btu"] == 24000.0
        assert spec["heating_btu"] == 24000.0
        assert spec["sys_type"] == "H"
        assert spec["unit_type"] == "OS"
        assert spec["weight_lb"] == 135.0
        # Description should include capacity + unit-type label
        assert "24,000 BTU" in line["description"]
        assert "Heat Pump" in line["description"]
        assert "Outdoor Split" in line["description"]
        assert "Carrier 38MARBQ24AA3" in line["description"]

    def test_dfunit_match_takes_precedence_over_generic_mapping(self, minimal_profile):
        """If a generic_id ALSO has a mapped_parts row (unlikely but
        possible), the DFUnit path wins because it gives authoritative
        equipment data."""
        bom = build_bom_from_wrightsoft_lines(
            lines=[{"generic_id": "38MARBQ24AA3", "quantity": 1}],
            profile=minimal_profile,
            job_id="t",
        )
        # Even if some future mapped_parts row pointed at this model,
        # the source remains wrightsoft_dfunit, not wrightsoft_mapped.
        assert bom["line_items"][0]["source"] == "wrightsoft_dfunit"

    def test_non_dfunit_generic_falls_through_to_mapped_parts(self, minimal_profile):
        """PEX0750 is a parts catalog entry, not a DFUnit equipment.
        Should not get the DFUnit treatment."""
        bom = build_bom_from_wrightsoft_lines(
            lines=[{"generic_id": "PEX0750", "quantity": 100}],
            profile=minimal_profile,
            job_id="t",
        )
        assert bom["line_items"][0]["source"] == "wrightsoft_mapped"
        assert "dfunit_spec" not in bom["line_items"][0]
        assert bom["wrightsoft_dfunit_item_count"] == 0

    def test_dfunit_count_separates_from_total_mapped(self, minimal_profile):
        """Mixed BOM: 1 DFUnit equipment + 2 parts. dfunit_count=1,
        mapped_count=3 (DFUnit hits also count as mapped overall)."""
        bom = build_bom_from_wrightsoft_lines(
            lines=[
                {"generic_id": "38MARBQ24AA3", "quantity": 1},
                {"generic_id": "PEX0750", "quantity": 100},
                {"generic_id": "BPERT1000", "quantity": 50},
            ],
            profile=minimal_profile,
            job_id="t",
        )
        assert bom["wrightsoft_dfunit_item_count"] == 1
        assert bom["wrightsoft_mapped_item_count"] == 3
        assert bom["wrightsoft_unmapped_item_count"] == 0


class TestDFUnitLookupHelpers:
    def test_lookup_dfunit_by_model_exact_match(self):
        from services.wrightsoft_catalog import lookup_dfunit_by_model
        r = lookup_dfunit_by_model("38MARBQ24AA3")
        assert r is not None
        assert r["Manufacturer"] == "CARR"
        assert r["ClgCap"] == "24000"

    def test_lookup_dfunit_by_model_returns_none_for_unknown(self):
        from services.wrightsoft_catalog import lookup_dfunit_by_model
        assert lookup_dfunit_by_model("TOTALLY-FAKE-MODEL") is None
        assert lookup_dfunit_by_model("") is None
        assert lookup_dfunit_by_model(None) is None  # type: ignore

    def test_lookup_dfunit_by_capacity_with_filters(self):
        from services.wrightsoft_catalog import lookup_dfunit_by_capacity
        hits = lookup_dfunit_by_capacity(
            cooling_btu=24000,
            manufacturer="MITS",
            sys_type="H",
            unit_type="OS",
        )
        assert len(hits) >= 1
        for h in hits:
            assert h["Manufacturer"] == "MITS"
            assert h["SysType"] == "H"
            assert h["UnitType"] == "OS"

    def test_lookup_dfunit_by_capacity_tolerance(self):
        """22,400 BTU returns within 10% of 24,000 BTU target."""
        from services.wrightsoft_catalog import lookup_dfunit_by_capacity
        hits = lookup_dfunit_by_capacity(
            cooling_btu=24000, manufacturer="MITS", tolerance_pct=0.10,
        )
        caps = [int(h["ClgCap"]) for h in hits]
        # All within 10% tolerance band
        assert all(21600 <= c <= 26400 for c in caps), caps

    def test_dfunit_line_spec_extracts_numeric_fields(self):
        from services.wrightsoft_catalog import lookup_dfunit_by_model, dfunit_line_spec
        r = lookup_dfunit_by_model("38MARBQ24AA3")
        spec = dfunit_line_spec(r)
        assert spec["manufacturer"] == "CARR"
        assert spec["cooling_btu"] == 24000.0
        assert spec["weight_lb"] == 135.0
        assert spec["sys_type"] == "H"
        assert spec["unit_type"] == "OS"


# ─── Catalog coverage diagnostic (Day-11 Feature 3) ────────────────

class TestCoverageReport:
    def test_report_shape(self):
        from services.wrightsoft_catalog import coverage_report
        r = coverage_report()
        # Top-level totals
        for key in ("generic_parts", "covered_generics",
                    "overall_coverage_pct", "mapped_supplier_variants",
                    "suppliers", "dfunit_models"):
            assert key in r["totals"]
        assert isinstance(r["categories"], list)
        assert isinstance(r["suppliers"], list)

    def test_totals_match_known_catalog(self):
        from services.wrightsoft_catalog import coverage_report
        r = coverage_report()
        t = r["totals"]
        # Bundled Tom catalog: 3,178 generic parts, 3,014 distinct
        # generics covered, 4,112 supplier variants, 963 DFUnit models
        assert t["generic_parts"] >= 3000
        assert t["covered_generics"] >= 2900
        assert t["mapped_supplier_variants"] >= 4000
        assert t["dfunit_models"] >= 900
        # Overall coverage is ~95% of distinct generics
        assert t["overall_coverage_pct"] >= 90.0

    def test_categories_sorted_worst_coverage_first(self):
        """The category list is meant to drive prioritization — worst
        coverage should land at the top so Richard sees what to fix
        first."""
        from services.wrightsoft_catalog import coverage_report
        r = coverage_report()
        cats = r["categories"]
        if len(cats) >= 2:
            for i in range(len(cats) - 1):
                a = cats[i]["coverage_pct"]
                b = cats[i + 1]["coverage_pct"]
                assert a <= b, f"Categories out of order at index {i}: {a} > {b}"

    def test_each_category_has_supplier_breakdown(self):
        from services.wrightsoft_catalog import coverage_report
        r = coverage_report()
        # Find a category that DOES have suppliers and check shape
        non_empty = [c for c in r["categories"] if c["suppliers"]]
        assert non_empty, "Expected at least one category with supplier mappings"
        sup = non_empty[0]["suppliers"][0]
        assert "supplier_code" in sup
        assert "name" in sup
        assert "mapped_count" in sup
        assert sup["mapped_count"] > 0

    def test_supplier_rollup_sorted_by_distinct_generics(self):
        from services.wrightsoft_catalog import coverage_report
        r = coverage_report()
        ss = r["suppliers"]
        # Top supplier (WSF per the actual bundled catalog) should have
        # the most distinct generics covered
        if len(ss) >= 2:
            for i in range(len(ss) - 1):
                a = ss[i]["distinct_generics_covered"]
                b = ss[i + 1]["distinct_generics_covered"]
                assert a >= b, f"Suppliers out of order: {a} < {b}"


class TestCoverageEndpoint:
    def test_endpoint_returns_report(self):
        import os
        os.environ.setdefault("ANTHROPIC_API_KEY", "dev-test")
        os.environ.setdefault("FIRESTORE_PROJECT_ID", "dev-test")
        os.environ.setdefault("SERVICE_SHARED_SECRET", "")
        from app import create_app
        client = create_app().test_client()

        resp = client.get("/api/v1/bom/catalog-coverage")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert "totals" in body["data"]
        assert "categories" in body["data"]
        assert "suppliers" in body["data"]
