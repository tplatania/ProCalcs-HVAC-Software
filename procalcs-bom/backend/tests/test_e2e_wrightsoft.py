"""
End-to-end harness for the Wrightsoft deterministic BOM pipeline
(Day-12). Catches integration drift before deploy by running synthetic
Wrightsoft BOM CSV fixtures through the FULL pipeline:

    raw CSV bytes
      → parse_wrightsoft_bom_rows()
        → build_bom_from_wrightsoft_lines()
          → BOM dict (line_items, totals, section grouping, source provenance)

Then asserts on locked-in expectations. Unlike the unit tests in
test_bom_from_wrightsoft.py — which exercise the helpers individually
against the real catalog — these tests pin the *contract* the SPA
relies on: that a particular CSV produces a particular set of mapped /
unmapped / DFUnit lines, with the expected supplier picks and section
assignments.

Why this exists: between Day-9 and Day-11 the SPA broke twice silently
because backend helpers changed shape (e.g. wrightsoft_dfunit source
got introduced; section_for_generic returned new strings). E2E pins
the surface so the next surface change is caught at PR time, not by
Richard.

Fixtures are tiny inline CSVs — each test names which behavior it
locks. To add a new fixture: pick generics with stable supplier
mappings (PEX0750/QST, DDFg06/WSF, 38MARBQ24AA3/DFUnit Carrier).
"""

from __future__ import annotations

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

from models.client_profile import (
    ClientProfile, SupplierInfo, MarkupTiers, BrandPreferences,
)
from services.bom_from_wrightsoft import (
    build_bom_from_wrightsoft_lines,
    parse_wrightsoft_bom_rows,
)


# ─── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def wsf_profile():
    """Profile preferring Wrightsoft's own bundled supplier (WSF) so
    most catalog mappings hit. Covers the broadest set of generics."""
    return ClientProfile(
        client_id="wsf-test",
        client_name="WSF Test Contractor",
        supplier=SupplierInfo(supplier_name="WSF"),
        markup=MarkupTiers(equipment_pct=10.0, materials_pct=15.0, consumables_pct=20.0),
        brands=BrandPreferences(),
        part_name_overrides=[],
    )


def _e2e(csv_text: str, profile: ClientProfile, job_id: str = "e2e-test"):
    """Pipe a CSV string through parse → build and return the BOM dict."""
    lines = parse_wrightsoft_bom_rows(csv_text.encode("utf-8"), filename="test.csv")
    return build_bom_from_wrightsoft_lines(
        lines=lines, profile=profile, job_id=job_id,
    )


# ─── Pipeline contract: shape ──────────────────────────────────────

def test_e2e_response_shape(wsf_profile):
    """The BOM dict the route returns has the keys the SPA reads."""
    csv = (
        "generic_id,quantity,description\n"
        "PEX0750,100,1/2-in PEX Tubing\n"
        "DDFg06,50,Round fiberglass duct 6 in\n"
    )
    bom = _e2e(csv, wsf_profile)

    required = {
        "job_id", "client_id", "supplier", "line_items", "totals",
        "item_count", "wrightsoft_mapped_item_count",
        "wrightsoft_unmapped_item_count", "wrightsoft_dfunit_item_count",
    }
    missing = required - set(bom.keys())
    assert not missing, f"missing top-level keys: {missing}"

    li_required = {"generic_id", "description", "section", "category",
                   "source", "quantity", "unit_cost"}
    for li in bom["line_items"]:
        missing = li_required - set(li.keys())
        assert not missing, f"line item missing keys: {missing}"


def test_e2e_item_counts_separate_mapped_dfunit_unmapped(wsf_profile):
    """Reviewers count on the three buckets being mutually exclusive
    and summing to item_count (excluding any other source types)."""
    csv = (
        "generic_id,quantity,description\n"
        "PEX0750,100,PEX                            \n"     # mapped (WSF or any)
        "38MARBQ24AA3,1,Carrier outdoor split        \n"     # dfunit
        "DEFINITELY_NOT_A_REAL_GENERIC_XYZ,1,Mystery\n"      # unmapped
    )
    bom = _e2e(csv, wsf_profile)

    mapped   = bom["wrightsoft_mapped_item_count"]
    dfunit   = bom["wrightsoft_dfunit_item_count"]
    unmapped = bom["wrightsoft_unmapped_item_count"]

    assert dfunit   == 1, "Carrier DFUnit model must hit the dfunit path"
    assert unmapped == 1, "fake generic must land in the unmapped bucket"
    assert mapped   >= 1, "PEX0750 should map (lots of suppliers cover it)"


# ─── Pipeline contract: source provenance ──────────────────────────

def test_e2e_dfunit_source_takes_precedence_over_generic(wsf_profile):
    """A model that lives in DFUnit.csv must be tagged source=
    wrightsoft_dfunit (NOT wrightsoft_mapped). The SPA highlights
    DFUnit hits separately on the result page."""
    csv = (
        "generic_id,quantity,description\n"
        "38MARBQ24AA3,1,Carrier outdoor split\n"
    )
    bom = _e2e(csv, wsf_profile)
    assert len(bom["line_items"]) == 1
    li = bom["line_items"][0]
    assert li["source"] == "wrightsoft_dfunit"
    # DFUnit-enriched description includes manufacturer + capacity
    assert "Carrier" in li["description"]
    assert "24,000 BTU" in li["description"] or "24000" in li["description"].replace(",", "")


def test_e2e_unmapped_generic_preserves_id_for_sku_backlog(wsf_profile):
    """The SKU Backlog page groups unmapped lines by generic_id so
    Richard's team can prioritize what to encode next. The pipeline
    must echo the original generic_id back on unmapped lines."""
    csv = (
        "generic_id,quantity,description\n"
        "PHANTOM_GENERIC_NOT_IN_CATALOG,3,Mystery widget\n"
    )
    bom = _e2e(csv, wsf_profile)
    assert len(bom["line_items"]) == 1
    li = bom["line_items"][0]
    assert li["source"] == "wrightsoft_unmapped"
    assert li["generic_id"] == "PHANTOM_GENERIC_NOT_IN_CATALOG"
    # Unmapped lines may omit the sku key entirely or set it to None/""
    assert not li.get("sku"), "unmapped lines must not invent a SKU"


# ─── Pipeline contract: section grouping ───────────────────────────

def test_e2e_sections_route_to_known_buckets(wsf_profile):
    """SPA + XLSX renderer both group by section. Each emitted line
    must land in one of the known section buckets (or 'Other' as
    explicit escape hatch)."""
    csv = (
        "generic_id,quantity,description\n"
        "PEX0750,100,PEX\n"
        "DDFg06,50,Round duct\n"
        "38MARBQ24AA3,1,Carrier\n"
    )
    bom = _e2e(csv, wsf_profile)
    known = {
        "Equipment",
        "Duct System Equipment",
        "Rheia Duct System Equipment",
        "Labor",
        "Other",
    }
    sections = {li["section"] for li in bom["line_items"]}
    unknown = sections - known
    assert not unknown, f"unknown sections leaked into BOM: {unknown}"


def test_e2e_dfunit_routes_to_equipment_section(wsf_profile):
    csv = (
        "generic_id,quantity,description\n"
        "38MARBQ24AA3,1,Carrier outdoor split\n"
    )
    bom = _e2e(csv, wsf_profile)
    assert bom["line_items"][0]["section"] == "Equipment"


def test_e2e_round_duct_routes_to_duct_system(wsf_profile):
    csv = (
        "generic_id,quantity,description\n"
        "DDFg06,50,Round fiberglass duct 6 in\n"
    )
    bom = _e2e(csv, wsf_profile)
    li = bom["line_items"][0]
    assert li["section"] == "Duct System Equipment"


# ─── Pipeline contract: totals math ────────────────────────────────

def test_e2e_totals_sum_matches_line_items(wsf_profile):
    csv = (
        "generic_id,quantity,description\n"
        "PEX0750,100,PEX\n"
        "DDFg06,50,Round duct\n"
        "38MARBQ24AA3,1,Carrier\n"
    )
    bom = _e2e(csv, wsf_profile)
    sum_line_totals = sum(
        (li.get("total_price") or li.get("total_cost") or 0)
        for li in bom["line_items"]
    )
    declared = bom["totals"].get("total_price") or bom["totals"].get("total_cost") or 0
    assert abs(sum_line_totals - declared) < 0.01, (
        f"line-item sum {sum_line_totals} != declared total {declared}"
    )


# ─── Pipeline contract: CSV parser tolerance ───────────────────────

def test_e2e_parser_tolerates_header_aliases(wsf_profile):
    """parse_wrightsoft_bom_rows scans aliases for the header row.
    'Item' + 'Qty' (Wrightsoft's actual export columns) must work,
    not just 'generic_id' + 'quantity'."""
    csv = (
        "Item,Qty,Description\n"
        "PEX0750,100,PEX tubing\n"
    )
    lines = parse_wrightsoft_bom_rows(csv.encode("utf-8"), filename="test.csv")
    assert len(lines) == 1
    assert lines[0]["generic_id"] == "PEX0750"
    assert float(lines[0]["quantity"]) == 100.0


def test_e2e_passthrough_uses_wrightsoft_src_column(wsf_profile):
    """Real Wrightsoft BOMs include parts that aren't in the bundled
    mapping catalog (Goodman / Broan equipment SKUs, Rheia
    auto-generated codes, PGM-prefixed fittings). Wrightsoft's own
    Src + Name columns already tell us who supplies them and what
    the part number is — emit wrightsoft_passthrough lines for those
    instead of routing them all into the SKU Backlog.

    Locks in the Day-12 'use what Wrightsoft produced' behavior the
    Richmond T333 sample exposed (was emitting 18/21 lines as
    unmapped before this change)."""
    csv = (
        "Src,Name,Description,Phase,Qty,Un,Tax,Price,Ext price\n"
        ",,Equipment,,,,,,\n"
        "GOOD,AHVE24BP1300A,Air Handling Unit,None,1,0,,0,0\n"
        "BROAN,B150E75NT,ERV,None,1,0,,0,0\n"
        ",,Rheia Duct System Equipment,,,,,,\n"
        "RHEA,10-00-190,3-in Duct Uninsulated,Rough,768,0,,0,0\n"
    )
    bom = _e2e(csv, wsf_profile)
    # All three rows should be passthrough (none in bundled mapping)
    assert bom["wrightsoft_passthrough_item_count"] == 3
    assert bom["wrightsoft_unmapped_item_count"] == 0
    for li in bom["line_items"]:
        assert li["source"] == "wrightsoft_passthrough"
        # SKU == Name column, Manufacturer == Src column
        assert li["sku"] == li["generic_id"]
        assert li["manufacturer"] in {"GOOD", "BROAN", "RHEA"}


def test_e2e_section_hint_routes_unmapped_lines_correctly(wsf_profile):
    """Section-divider rows ('Equipment' / 'Duct System Equipment' /
    'Rheia Duct System Equipment') in the Wrightsoft export must
    propagate to subsequent data rows even when those rows aren't
    in the bundled mapping catalog. Without this, real BOMs piled
    almost everything into 'Other'."""
    csv = (
        "Src,Name,Description,Phase,Qty,Un,Tax,Price,Ext price\n"
        ",,Equipment,,,,,,\n"
        "GOOD,AHVE24BP1300A,AHU,None,1,0,,0,0\n"
        ",,Rheia Duct System Equipment,,,,,,\n"
        "RHEA,10-00-190,3-in Duct,Rough,768,0,,0,0\n"
        "RHEA,10-04-091,Slotted Diffuser,Finish,16,0,,0,0\n"
    )
    bom = _e2e(csv, wsf_profile)
    by_section = {}
    for li in bom["line_items"]:
        by_section.setdefault(li["section"], []).append(li["generic_id"])
    assert "AHVE24BP1300A" in by_section.get("Equipment", []), by_section
    assert "10-00-190" in by_section.get("Rheia Duct System Equipment", []), by_section
    assert "10-04-091" in by_section.get("Rheia Duct System Equipment", []), by_section


def test_e2e_subtotal_rows_do_not_reset_section_hint(wsf_profile):
    """A 'Subtotal, Equipment' row appearing between data rows must
    not clear the rolling section hint — otherwise the next row
    silently falls back to 'Other'."""
    csv = (
        "Src,Name,Description,Phase,Qty,Un,Tax,Price,Ext price\n"
        ",,Duct System Equipment,,,,,,\n"
        "WSF,DDVn10,Round vinyl duct,None,3,0,,2,6\n"
        ",,\"Subtotal, Duct System Equipment\",,,,,,8\n"
        "WSF,FBTI-10,Ceiling round register,None,2,0,,43.6,87.2\n"
    )
    bom = _e2e(csv, wsf_profile)
    sections = {li["generic_id"]: li["section"] for li in bom["line_items"]}
    # Both lines must land in Duct System Equipment — subtotal must
    # not have wiped the hint.
    assert sections.get("FBTI-10") == "Duct System Equipment", sections


def test_e2e_parser_handles_real_wrightsoft_xls_columns(wsf_profile):
    """The real Wrightsoft XLS export uses these exact columns:
        Src | Name | Description | Phase | Qty | Un | Tax | Price | Ext price
    The 'Name' column carries the generic_id (or manufacturer SKU for
    pre-mapped equipment). Plus section-divider rows like 'Equipment',
    'Subtotal, Equipment', 'Duct System Equipment' have empty Src/Name
    cells and must be skipped silently.

    Regression test for the 'Could not find header row' bug Gerald hit
    on (Sample BOM) Lot 1 T075 Elm ACL BOM.xls — caused by 'name'
    living only in the description alias list.
    """
    csv = (
        "Src,Name,Description,Phase,Qty,Un,Tax,Price,Ext price\n"
        ",,Equipment,,,,,,\n"
        "GOODMAN,AHVE24BP1300A,AHU,None,1,0,,0,0\n"
        "WSF,DDVn10,\"Round vinyl duct, D = 10\",None,3,0,,2,6\n"
        ",,\"Subtotal, Equipment\",,,,,,0\n"
        ",,Duct System Equipment,,,,,,\n"
        "PGM,DRFg1712MI,\"Rect fiberglass duct\",None,4.12,0,,6.5,26.8\n"
    )
    lines = parse_wrightsoft_bom_rows(csv.encode("utf-8"), filename="real.csv")
    # 3 data rows; 3 section/subtotal rows skipped because Name is blank
    names = [l["generic_id"] for l in lines]
    assert names == ["AHVE24BP1300A", "DDVn10", "DRFg1712MI"], (
        f"expected the 3 Name-column values, got {names}"
    )
    # End-to-end build still works on the parsed rows.
    bom = build_bom_from_wrightsoft_lines(
        lines=lines, profile=wsf_profile, job_id="real-wsf-test",
    )
    assert bom["item_count"] == 3


def test_e2e_parser_handles_utf8_bom():
    """Wrightsoft exports include a UTF-8 BOM; parser must strip it
    silently or the first generic_id is misread."""
    csv = "﻿generic_id,quantity,description\nPEX0750,1,PEX\n"
    lines = parse_wrightsoft_bom_rows(csv.encode("utf-8"), filename="test.csv")
    assert len(lines) == 1
    assert lines[0]["generic_id"] == "PEX0750"


def test_e2e_parser_rejects_empty_file():
    with pytest.raises(ValueError):
        parse_wrightsoft_bom_rows(b"", filename="empty.csv")


def test_e2e_parser_skips_rows_without_generic(wsf_profile):
    """Comments + blank rows in the CSV must not become line items."""
    csv = (
        "generic_id,quantity,description\n"
        "PEX0750,100,PEX\n"
        ",,(blank row)\n"
        ",0,(no generic)\n"
    )
    bom = _e2e(csv, wsf_profile)
    # Only the real PEX row should make it through.
    assert bom["item_count"] == 1
    assert bom["line_items"][0]["generic_id"].upper() == "PEX0750"
