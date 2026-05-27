"""
bom_from_wrightsoft.py — Build a contractor BOM from Wrightsoft's
generic-part output (Day-9 / Tom's "use the produced information" path).

This is the consumer Tom asked about in his Slack message: instead of
re-deriving a BOM from raw RUP design data + AI, we take Wrightsoft's
own generated BOM (a list of generic-part IDs + quantities) and
translate each entry through the mapping infrastructure that's been
sitting unused since Phase 3.

Input contract:
    [{"generic_id": "PEX0750", "quantity": 250.0,
      "description": "1/2-in PEX Tubing"},
     ...]
    plus a ClientProfile (for supplier preference + markup).

Output: a BOM dict matching the existing /api/v1/bom/generate response
shape so downstream consumers (PDF renderer, comparator, run-history
SPA) don't need to special-case it.

Strategy per line:
  1. Look up the generic_id in Wrightsoft's catalog
     (services.wrightsoft_catalog.lookup_skus_for_generic) honoring
     the contractor's supplier preference when one is set
  2. If a manufacturer SKU exists → emit a "wrightsoft_mapped" line
     with that SKU, the Wrightsoft category-derived section, and
     description from generic_parts.csv (more authoritative than
     whatever the caller passed)
  3. If no mapping (generic_id not in mapped_parts.csv) → emit a line
     flagged "unmapped" so reviewers can see what catalog gaps exist
     (feeds the existing SKU-Backlog page)
  4. Apply markup + estimated cost via the same _get_unit_cost /
     _get_markup_pct helpers bom_service uses — keeps pricing logic
     centralized
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from models.client_profile import ClientProfile
from services import wrightsoft_catalog as wsc

logger = logging.getLogger("procalcs_bom.bom_from_wrightsoft")


# ─── Public API ─────────────────────────────────────────────────────

def build_bom_from_wrightsoft_lines(
    *,
    lines: list[dict[str, Any]],
    profile: ClientProfile,
    job_id: str,
    output_mode: str = "full",
) -> dict[str, Any]:
    """Build a complete BOM from a Wrightsoft generic-part listing.

    Returns the same dict shape /api/v1/bom/generate emits so the BOM
    flows through the existing persistence + diff + PDF pipeline
    unchanged.

    Args:
        lines: list of {"generic_id": str, "quantity": float|str,
                        "description": str | optional}
        profile: contractor profile (supplier preference + markup)
        job_id: identifier echoed in the response + bom_runs.job_id
        output_mode: profile output mode (full / cost_estimate / etc.)

    Provenance fields per line:
        source            = "wrightsoft_mapped" | "wrightsoft_unmapped"
        sku               = manufacturer part number (or None when unmapped)
        manufacturer      = 4-char source code from Wrightsoft (QST, GOOD, etc.)
        generic_id        = the original Wrightsoft generic ID — preserved
                            so the SKU Backlog can group unmapped lines
        cost_is_estimate  = True when fell back to estimated cost
    """
    # Lazy import — pulling from services.bom_service at module load
    # creates an import cycle (bom_service imports things that import
    # this file once it's registered as a sibling).
    from services.bom_service import _get_unit_cost, _get_markup_pct

    # Make sure the catalog is warm before the loop — avoids per-line
    # cache thrash when hundreds of lines arrive.
    wsc.load_mapped_parts()
    generic_parts = wsc.load_generic_parts()

    # Contractor's preferred supplier — read from the brands block.
    # Fall back to the AC brand when no explicit supplier code is set
    # so Goodman-preferring contractors still get filtered output.
    supplier_pref = _supplier_pref_for(profile)

    line_items: list[dict[str, Any]] = []
    mapped_count = 0
    unmapped_count = 0
    dfunit_count = 0

    for raw in lines:
        gen_id = (raw.get("generic_id") or "").strip()
        if not gen_id:
            continue
        try:
            quantity = float(raw.get("quantity") or 0)
        except (TypeError, ValueError):
            quantity = 0.0
        if quantity <= 0:
            # Skip zero-quantity rows. Wrightsoft sometimes outputs
            # placeholder rows; emitting them as $0 BOM lines is noise.
            continue

        # Day-11 — DFUnit equipment-spec lookup. Wrightsoft BOMs
        # sometimes reference DFUnit model numbers directly (ductless
        # / heat-pump units don't go through the parts catalog —
        # they're listed by Manufacturer + Model). If the generic_id
        # IS a DFUnit Model, we get the full unit spec for free:
        # manufacturer, capacity (BTU), dimensions, weight.
        dfunit_row = wsc.lookup_dfunit_by_model(gen_id)
        dfunit_spec = wsc.dfunit_line_spec(dfunit_row) if dfunit_row else None

        # Look up the contractor's manufacturer SKU
        sku_matches = wsc.lookup_skus_for_generic(gen_id, supplier_pref)
        catalog_row = generic_parts.get(gen_id) or {}
        # Wrightsoft's description is the source of truth (matches
        # the contractor's expectations); caller-provided description
        # is the fallback for items not in the catalog.
        description = (
            catalog_row.get("Description")
            or raw.get("description")
            or gen_id
        )
        unit = catalog_row.get("Units") or raw.get("unit") or "EA"
        section = wsc.section_for_generic(gen_id) or wsc.SECTION_OTHER
        category = _category_to_line_category(catalog_row.get("Category"))

        if dfunit_spec:
            # DFUnit direct match — authoritative manufacturer + model.
            # This path is used for ductless / heat-pump units that
            # Wrightsoft lists by model number rather than generic ID.
            # Equipment category is implied; section is Equipment.
            mapped_count += 1
            dfunit_count += 1
            # Description prefers a more informative composed string
            # over the raw catalog description when we have spec data.
            desc_with_spec = _compose_dfunit_description(description, dfunit_spec)
            line = _priced_line(
                generic_id=gen_id,
                description=desc_with_spec,
                quantity=quantity,
                unit=unit or "EA",
                section=wsc.SECTION_EQUIPMENT,
                category="equipment",
                profile=profile,
                sku=dfunit_spec["model"],
                manufacturer=dfunit_spec["manufacturer"],
                source="wrightsoft_dfunit",
                get_unit_cost=_get_unit_cost,
                get_markup_pct=_get_markup_pct,
            )
            # Attach the spec dict so PDF / SPA can display capacity,
            # dimensions, weight without re-looking up DFUnit downstream.
            line["dfunit_spec"] = dfunit_spec
        elif sku_matches:
            mapped_count += 1
            supplier_code, mfr_partnum = sku_matches[0]
            line = _priced_line(
                generic_id=gen_id,
                description=description,
                quantity=quantity,
                unit=unit,
                section=section,
                category=category,
                profile=profile,
                sku=mfr_partnum,
                manufacturer=supplier_code,
                source="wrightsoft_mapped",
                get_unit_cost=_get_unit_cost,
                get_markup_pct=_get_markup_pct,
            )
        else:
            unmapped_count += 1
            line = _priced_line(
                generic_id=gen_id,
                description=description,
                quantity=quantity,
                unit=unit,
                section=section,
                category=category,
                profile=profile,
                sku=None,
                manufacturer=None,
                source="wrightsoft_unmapped",
                get_unit_cost=_get_unit_cost,
                get_markup_pct=_get_markup_pct,
            )

        line_items.append(line)

    totals = _compute_totals(line_items)
    bom = {
        "job_id":      job_id,
        "client_id":   profile.client_id,
        "client_name": profile.client_name,
        "output_mode": output_mode,
        "generated_at": _utcnow_iso(),
        "supplier":    profile.supplier.supplier_name or "",
        "line_items":  line_items,
        "totals":      totals,
        "item_count":  len(line_items),
        # Provenance counts in the same vocabulary the existing BOM
        # response uses (catalog_match_item_count, etc.) so the SPA
        # surfaces them without special casing.
        "wrightsoft_mapped_item_count":   mapped_count,
        "wrightsoft_unmapped_item_count": unmapped_count,
        # Day-11 — how many of the mapped lines came from DFUnit
        # (authoritative equipment-library hits with full spec data)
        # vs the generic-parts mapping. Lets the SPA show e.g.
        # "12 mapped (3 from equipment library)".
        "wrightsoft_dfunit_item_count":   dfunit_count,
        "catalog_match_item_count":       0,
        "rules_engine_item_count":        0,
        "ai_item_count":                  0,
        # Day-9 marker so the SPA + comparator know this BOM came from
        # Wrightsoft's own output rather than the AI pipeline.
        "source_pipeline": "wrightsoft_bom",
    }
    logger.info(
        "Wrightsoft BOM built for job %s — %d lines (%d mapped / %d unmapped)",
        job_id, len(line_items), mapped_count, unmapped_count,
    )
    return bom


# ─── Internals ──────────────────────────────────────────────────────

def _supplier_pref_for(profile: ClientProfile) -> Optional[str]:
    """Read the contractor's preferred Wrightsoft supplier code from
    the profile's brand prefs. Returns None when no preference is set,
    which makes lookup_skus_for_generic return all suppliers in file
    order (caller picks the first)."""
    # The 4-char Wrightsoft source code may live in supplier_name
    # (some contractors save 'QST' or 'GOOD' there) or in the brand
    # fields. Best-effort match against the known manufacturer list.
    candidates: list[str] = []
    if profile.supplier and profile.supplier.supplier_name:
        candidates.append(profile.supplier.supplier_name)
    if profile.brands:
        for attr in ("ac_brand", "furnace_brand", "air_handler_brand"):
            v = getattr(profile.brands, attr, "")
            if v: candidates.append(v)
    known = set(wsc.load_manufacturers().keys())
    mfrs = wsc.load_manufacturers()
    for c in candidates:
        if not c: continue
        c_up = c.upper().strip()
        # Direct 4-char code match
        if c_up in known:
            return c_up
        # Substring match against manufacturer Name. Wrightsoft Names
        # have suffixes like "Goodman Mfg.", "LG Electronics" — match
        # the leading word against the candidate so "Goodman" → "GOOD".
        c_low = c.lower().strip()
        for code, row in mfrs.items():
            name = (row.get("Name") or "").lower().strip()
            if not name:
                continue
            # Match: name starts with candidate ("goodman mfg." starts with "goodman")
            # OR candidate starts with name (less common but tolerant)
            if name.startswith(c_low) or c_low.startswith(name):
                return code
    return None


def _category_to_line_category(wrightsoft_cat: Optional[str]) -> str:
    """Map a Wrightsoft category code to one of the line-item
    `category` vocabulary the rest of the BOM pipeline understands
    (equipment / duct / fitting / register / consumable / other)."""
    if not wrightsoft_cat:
        return "other"
    # Equipment-adjacent
    if wrightsoft_cat in ("EACCESSY", "HVACCTLS", "MSRP"):
        return "equipment"
    if wrightsoft_cat == "RHALL":
        return "equipment"  # radiant — closest bucket
    # Duct system
    if wrightsoft_cat in ("DSRCT", "DSRND"):
        return "duct"
    if wrightsoft_cat in ("DFRELB", "DFRPLN", "DFRTKO", "DFRTEE", "DFRTRS"):
        return "fitting"
    if wrightsoft_cat == "DFRBTR":
        return "register"
    if wrightsoft_cat == "HVDALL":
        return "duct"  # Rheia is high-velocity duct
    return "other"


def _priced_line(
    *,
    generic_id: str,
    description: str,
    quantity: float,
    unit: str,
    section: str,
    category: str,
    profile: ClientProfile,
    sku: Optional[str],
    manufacturer: Optional[str],
    source: str,
    get_unit_cost,
    get_markup_pct,
) -> dict[str, Any]:
    """Apply markup + estimated-cost fallback to a single line. Shared
    between the mapped and unmapped paths so the cost math is consistent."""
    unit_cost = float(get_unit_cost(description, category, profile) or 0.0)
    is_estimate = False
    # Equipment-category items with no mapped catalog cost still get
    # the estimated-cost fallback from bom_service so they don't emit
    # as $0 (Day-7 fix — same rule applies here).
    if unit_cost == 0.0 and category == "equipment":
        # _get_unit_cost already checks the estimated table when
        # category is equipment; the > 0 result above already includes
        # that fallback. If still 0, leave as 0.
        pass
    elif unit_cost > 0 and category == "equipment":
        # Mark estimated when the cost came from the hardcoded table
        # rather than a real catalog row. We can't tell from here
        # whether _get_unit_cost hit the estimate path or the supplier
        # cost map, so we conservatively flag only AI-style estimates
        # (no SKU) as such.
        is_estimate = sku is None

    markup_pct = float(get_markup_pct(category, profile) or 0.0)
    unit_price = round(unit_cost * (1 + markup_pct / 100), 2)
    total_cost = round(unit_cost * quantity, 2)
    total_price = round(unit_cost * (1 + markup_pct / 100) * quantity, 2)

    line: dict[str, Any] = {
        "category":    category,
        "description": description,
        "quantity":    quantity,
        "unit":        unit,
        "unit_cost":   unit_cost,
        "unit_price":  unit_price,
        "total_cost":  total_cost,
        "total_price": total_price,
        "markup_pct":  markup_pct,
        "section":     section,
        "source":      source,
        # Always preserve the generic_id — lets the SKU-Backlog page
        # aggregate unmapped IDs into a "what to add to mapped_parts.csv
        # next" prioritized list.
        "generic_id":  generic_id,
    }
    if sku:
        line["sku"] = sku
    if manufacturer:
        line["manufacturer"] = manufacturer
    if is_estimate:
        line["cost_is_estimate"] = True
    return line


def _compute_totals(line_items: list[dict[str, Any]]) -> dict[str, float]:
    total_cost = round(sum(li.get("total_cost") or 0 for li in line_items), 2)
    total_price = round(sum(li.get("total_price") or 0 for li in line_items), 2)
    return {"total_cost": total_cost, "total_price": total_price}


def _utcnow_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _compose_dfunit_description(fallback: str, spec: dict[str, Any]) -> str:
    """Build a human-readable description that incorporates the unit
    capacity + type when DFUnit spec data is available. Keeps the
    caller-provided description as a fallback when the spec is sparse.

    Examples:
        "Carrier 38MARBQ24AA3 — Heat Pump, Outdoor Split, 24,000 BTU"
        "Mitsubishi MUZ-GL18NA-U1 — Heat Pump, Outdoor Multi, 18,000 BTU"
    """
    mfr = spec.get("manufacturer") or ""
    model = spec.get("model") or ""
    parts: list[str] = []
    if mfr and model:
        parts.append(f"{_pretty_manufacturer(mfr)} {model}")
    elif model:
        parts.append(model)
    bits: list[str] = []
    sys_type = spec.get("sys_type")
    if sys_type == "H": bits.append("Heat Pump")
    elif sys_type == "A": bits.append("AC")
    unit_type_label = _UNIT_TYPE_LABEL.get(spec.get("unit_type") or "")
    if unit_type_label: bits.append(unit_type_label)
    cap = spec.get("cooling_btu") or spec.get("heating_btu")
    if cap: bits.append(f"{int(cap):,} BTU")
    if bits and parts:
        return f"{parts[0]} — {', '.join(bits)}"
    if parts:
        return parts[0]
    return fallback


_UNIT_TYPE_LABEL: dict[str, str] = {
    "OS": "Outdoor Split",
    "OM": "Outdoor Multi",
    "IW": "Indoor Wall",
    "IC": "Indoor Ceiling",
    "ID": "Indoor Duct",
    "IF": "Indoor Floor",
    "IA": "Indoor Air-Handler",
    "IU": "Indoor Universal",
}


# Mirrors the substring-tolerant supplier matching in _supplier_pref_for;
# used here to turn a 4-char code (CARR, MITS, DAIK) into a human name
# for display.
_MFR_DISPLAY: dict[str, str] = {
    "CARR": "Carrier", "MITS": "Mitsubishi", "DAIK": "Daikin",
    "FUJI": "Fujitsu", "GREE": "Gree",        "LGEL": "LG",
    "MRCL": "MrCool",  "WSF":  "Wrightsoft",
}

def _pretty_manufacturer(code: str) -> str:
    return _MFR_DISPLAY.get(code.upper(), code)


# ─── CSV / XLS ingestion (Day-9 endpoint input parser) ──────────────

# Column-name aliases the parser will try when locating the
# generic_id / quantity columns. Lowercased and stripped before match.
# Lets us tolerate variations across Wrightsoft versions without
# requiring Tom to rename columns. Order matters — first match wins.
# 'name' must come BEFORE 'item' — Wrightsoft's actual XLS export uses
# 'Name' as the part-identifier column (the row labelled 'Src | Name |
# Description | Phase | Qty | Un | Tax | Price | Ext price'). Older
# pre-Day-12 fixtures used 'item' or 'generic_id' so those still work
# as fallbacks. 'name' is intentionally NOT in the description alias
# list below — same column can't be both gid and description.
_GENERIC_ID_HEADER_ALIASES = (
    "name", "item", "generic_id", "generic id", "id", "part", "part_id",
    "part id", "generic", "code",
)
_QUANTITY_HEADER_ALIASES = (
    "qty", "quantity", "count", "amount", "number",
)
_DESCRIPTION_HEADER_ALIASES = (
    "description", "desc", "label",
)


def parse_wrightsoft_bom_rows(
    file_bytes: bytes,
    *,
    filename: str = "",
) -> list[dict[str, Any]]:
    """Parse a Wrightsoft BOM export (CSV or XLS/XLSX) into the
    {generic_id, quantity, description} shape build_bom_from_wrightsoft_lines
    expects.

    Tolerant of column-name variation — looks for common aliases
    ("Item" / "generic_id" / "Part"). Returns [] if no rows decode.
    Raises ValueError on a truly unparseable file so the caller can
    return a 400.

    Header detection: scans the first 10 rows for a row containing
    both a generic-id header AND a quantity header. The matched row
    pins the column indices for subsequent data rows.
    """
    if not file_bytes:
        raise ValueError("Empty file")

    name = (filename or "").lower()
    raw_rows: list[list[str]]
    if name.endswith(".csv") or _looks_like_csv(file_bytes):
        raw_rows = _read_csv_rows(file_bytes)
    else:
        # Defer XLS/XLSX parsing to the existing sample_bom helpers —
        # they already handle both formats with xlrd / openpyxl.
        from services.sample_bom import (
            _read_xlsx_rows, _read_xls_rows,  # noqa: PLC0415
        )
        is_xlsx = name.endswith(".xlsx") or file_bytes[:2] == b"PK"
        is_xls  = name.endswith(".xls") or file_bytes[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        if is_xlsx:
            raw_rows = _read_xlsx_rows(file_bytes)
        elif is_xls:
            raw_rows = _read_xls_rows(file_bytes)
        else:
            raise ValueError(
                "Unrecognized file format — accepts .csv, .xls, .xlsx "
                "(or send rows as a JSON body instead)."
            )

    return _rows_to_generic_lines(raw_rows)


def _looks_like_csv(file_bytes: bytes) -> bool:
    """Heuristic — comma + newline in the first 1KB, no binary signatures."""
    head = file_bytes[:1024]
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # XLS magic
        return False
    if head[:2] == b"PK":  # XLSX (ZIP)
        return False
    try:
        sample = head.decode("utf-8", errors="strict")
        return "," in sample and "\n" in sample
    except UnicodeDecodeError:
        return False


def _read_csv_rows(file_bytes: bytes) -> list[list[str]]:
    """Decode CSV bytes into list-of-list-of-strings."""
    import csv
    import io
    # utf-8-sig transparently strips the BOM Wrightsoft writes
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader]


def _rows_to_generic_lines(raw_rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Find the header row (scans first 10 rows), then map each data
    row to {generic_id, quantity, description}. Tolerates rows shorter
    than the header (treats missing cells as empty)."""
    if not raw_rows:
        return []

    header_idx, gid_col, qty_col, desc_col = _locate_header(raw_rows)
    if header_idx < 0:
        raise ValueError(
            "Could not find header row — expected columns including one of "
            f"{list(_GENERIC_ID_HEADER_ALIASES)} for generic ID and one of "
            f"{list(_QUANTITY_HEADER_ALIASES)} for quantity."
        )

    out: list[dict[str, Any]] = []
    for row in raw_rows[header_idx + 1:]:
        # Tolerant access — pad short rows so indexing doesn't IndexError
        def _at(i: int) -> str:
            if i < 0 or i >= len(row):
                return ""
            v = row[i]
            return str(v).strip() if v is not None else ""

        gid = _at(gid_col)
        if not gid:
            continue
        qty_raw = _at(qty_col)
        try:
            qty = float(qty_raw or 0)
        except ValueError:
            qty = 0.0
        line = {
            "generic_id": gid,
            "quantity":   qty,
            "description": _at(desc_col) if desc_col >= 0 else "",
        }
        out.append(line)
    return out


def _locate_header(raw_rows: list[list[Any]]) -> tuple[int, int, int, int]:
    """Scan the first 10 rows for one containing both a generic-id
    header alias AND a quantity header alias. Returns
    (header_row_index, gid_col, qty_col, description_col_or_-1).
    Returns (-1, 0, 0, -1) if no header is found.
    """
    for idx, row in enumerate(raw_rows[:10]):
        norm = [str(c or "").strip().lower() for c in row]
        gid_col = _first_alias_index(norm, _GENERIC_ID_HEADER_ALIASES)
        qty_col = _first_alias_index(norm, _QUANTITY_HEADER_ALIASES)
        if gid_col >= 0 and qty_col >= 0:
            desc_col = _first_alias_index(norm, _DESCRIPTION_HEADER_ALIASES)
            return idx, gid_col, qty_col, desc_col
    return -1, 0, 0, -1


def _first_alias_index(norm_row: list[str], aliases: tuple[str, ...]) -> int:
    for alias in aliases:
        if alias in norm_row:
            return norm_row.index(alias)
    return -1
