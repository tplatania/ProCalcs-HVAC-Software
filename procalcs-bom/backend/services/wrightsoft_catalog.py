"""
wrightsoft_catalog.py — Loader for the BOM-relevant CSVs Tom exported
from Wrightsoft's library.

Five small reference CSVs (~600 KB total) ship in
``backend/data/wrightsoft_catalog/`` and load eagerly on first use.
The 70 manufacturer-specific AHRI equipment catalogs (~239 MB,
1.45 M rows total) are NOT part of this loader — those land in
Firestore later (Phase 4) so the Docker image stays slim.

Files consumed:
  - categories.csv   (14 rows)  Wrightsoft category code → human name
  - manufacturers.csv (29 rows) 4-char source code → mfr details
  - generic_parts.csv (3,179)   generic_id + category + description + units
  - mapped_parts.csv (4,113)    generic_id ↔ supplier + manufacturer SKU
  - DFUnit.csv (964)            Ductless / mini-split equipment library

Inventory was verified clean in Phase 1 (see _repo-docs/RUP_BINARY_LAYOUT.md
follow-up notes): every file UTF-8 with BOM, every AHRI per-equipment-type
schema is consistent across all 12 manufacturers, no parse errors, no
uneven column counts.

Public surface (Phase 2+ adds more):
  - load_categories()        → dict[code, description]
  - load_manufacturers()     → dict[source_code, dict]
  - load_generic_parts()     → dict[generic_id, dict]
  - load_mapped_parts()      → list[dict] of generic→supplier mappings
  - load_dfunit()            → list[dict]
  - all_categories()         → list of category codes
  - lookup_skus_for_generic(generic_id, supplier_pref=None)
                             → list of (supplier, manufacturer_partnum)
"""

from __future__ import annotations

import csv
import logging
import os
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("procalcs_bom.wrightsoft_catalog")

# ---------------------------------------------------------------------
# Module-level cache. Populated lazily on first call to any loader.
# Thread-safe via a single lock — load completes in <500ms whether
# from local CSV (legacy) or the catalog API (Phase C).
# ---------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "wrightsoft_catalog"

# Phase C dispatch — when CATALOG_API_URL is set, every loader fetches
# from procalcs-catalog instead of reading local CSVs. Falls back to
# CSV on any client error so a misconfigured deploy doesn't take the
# BOM Generator offline.
_API_URL_ENV = "CATALOG_API_URL"
_API_TOKEN_ENV = "CATALOG_API_TOKEN"

_lock = threading.Lock()


_catalog_client = None  # lazy-init


def _get_client():
    """Return a singleton CatalogClient when CATALOG_API_URL is set,
    or None to signal 'use the local CSV path'."""
    global _catalog_client
    if _catalog_client is not None:
        return _catalog_client
    url = os.environ.get(_API_URL_ENV, "").strip()
    if not url:
        return None
    try:
        from services._catalog_client import CatalogClient
        _catalog_client = CatalogClient(
            base_url=url,
            service_token=os.environ.get(_API_TOKEN_ENV) or None,
            client_id="procalcs-bom",
            timeout_seconds=15.0,
            cache_ttl_seconds=300.0,
        )
        logger.info("CatalogClient initialized → %s", url)
        return _catalog_client
    except Exception as exc:  # noqa: BLE001
        logger.error("CatalogClient init failed (%s) — falling back to CSV", exc)
        return None


@dataclass
class _Cache:
    categories: Optional[dict[str, str]] = None  # code -> description
    manufacturers: Optional[dict[str, dict[str, Any]]] = None  # source -> row
    generic_parts: Optional[dict[str, dict[str, Any]]] = None  # generic_id (item) -> row
    mapped_parts: Optional[list[dict[str, Any]]] = None  # one row per (generic, variant)
    mapped_by_generic: Optional[dict[str, list[dict[str, Any]]]] = None  # index
    # Reverse index — manufacturer_partnum (the SKU the contractor
    # actually orders) → list of mapping rows. Used by the BOM Engine
    # to verify AI-emitted SKUs against the bundled catalog.
    mapped_by_sku: Optional[dict[str, list[dict[str, Any]]]] = None
    dfunit: Optional[list[dict[str, Any]]] = None
    dfunit_by_model: Optional[dict[str, dict[str, Any]]] = None  # Model -> row
    # Day-15 — Tom's standard fitting-code template (set of canonical
    # codes designers SHOULD be using). Loaded from the catalog API.
    # bom-side: classify each Wrightsoft fitting on incoming BOMs;
    # codes NOT in this set get flagged as 'non-standard fitting'.
    fitting_template_codes: Optional[set[str]] = None
    # Day-15 — AHRI per-model spec cache. Lazy/sparse: each lookup hits
    # the catalog API and the result (row or None) is memoized so we
    # never re-query the same model in one process. 1.4M rows means we
    # CAN'T load it all; per-model lookups stay cheap because condenser
    # model is indexed in postgres.
    ahri_by_model: Optional[dict[str, Optional[dict[str, Any]]]] = None
    source: str = "uninitialized"


_cache = _Cache()


# ---------------------------------------------------------------------
# Loaders — each reads the corresponding CSV once and caches.
# ---------------------------------------------------------------------

def _read_csv_dict(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8-with-BOM CSV into a list of dicts. utf-8-sig
    transparently strips the BOM that Wrightsoft writes on every file."""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


# ─── Phase C — API → CSV-shape adapters ────────────────────────────
#
# The catalog API serializes rows with snake_case keys (manufacturer,
# clg_cap, …). Existing callers in procalcs-bom expect the original
# CSV shape (Manufacturer, ClgCap, …). These small adapters keep
# downstream code untouched.

def _api_to_csv_manufacturer(row: dict) -> dict:
    return {
        "Source":  row.get("source") or "",
        "Type":    row.get("type") or "",
        "Name":    row.get("name") or "",
        "Address": row.get("address") or "",
        "City":    row.get("city") or "",
        "State":   row.get("state") or "",
        "Zip":     row.get("zip") or "",
        "Phone":   row.get("phone") or "",
        "Email":   row.get("email") or "",
        "Web":     row.get("web") or "",
        "Contact": row.get("contact") or "",
    }


def _api_to_csv_generic(row: dict) -> dict:
    return {
        "Category":    row.get("category") or "",
        "Item":        row.get("item") or "",
        "Description": row.get("description") or "",
        "Units":       row.get("units") or "",
    }


def _api_to_csv_dfunit(row: dict) -> dict:
    return {
        "Manufacturer":   row.get("manufacturer") or "",
        "Model":          row.get("model") or "",
        "SysType":        row.get("sys_type") or "",
        "UnitType":       row.get("unit_type") or "",
        "ClgCap":         row.get("clg_cap"),
        "HtgCap":         row.get("htg_cap"),
        "PowerCode":      row.get("power_code") or "",
        "Series":         row.get("series") or "",
        "MixPipeId":      row.get("mix_pipe_id") or "",
        "VapPipeId":      row.get("vap_pipe_id") or "",
        "Height":         row.get("height"),
        "Width":          row.get("width"),
        "Depth":          row.get("depth"),
        "Weight":         row.get("weight"),
        "MaxPipeLen":     row.get("max_pipe_len"),
        "MaxPipeHeight":  row.get("max_pipe_height"),
    }


def load_categories() -> dict[str, str]:
    """Wrightsoft category code (e.g. 'DFRBTR') → human description.
    Sourced from procalcs-catalog when CATALOG_API_URL is set;
    falls back to local CSV otherwise."""
    with _lock:
        if _cache.categories is None:
            client = _get_client()
            if client is not None:
                try:
                    items = client.categories()
                    _cache.categories = {
                        (r.get("category") or ""): (r.get("description") or "")
                        for r in items
                    }
                    _cache.source = "catalog_api"
                except Exception as exc:  # noqa: BLE001
                    logger.warning("catalog API categories failed (%s) — CSV fallback", exc)
            if _cache.categories is None:
                rows = _read_csv_dict(_DATA_DIR / "categories.csv")
                _cache.categories = {r["Category"]: r["Description"] for r in rows}
                _cache.source = "csv"
            logger.info("Loaded %d Wrightsoft categories from %s",
                        len(_cache.categories), _cache.source)
    return _cache.categories


def load_manufacturers() -> dict[str, dict[str, Any]]:
    """4-char source code → manufacturer metadata row."""
    with _lock:
        if _cache.manufacturers is None:
            client = _get_client()
            if client is not None:
                try:
                    items = client.manufacturers()
                    _cache.manufacturers = {
                        (r.get("source") or ""): _api_to_csv_manufacturer(r)
                        for r in items if r.get("source")
                    }
                except Exception as exc:  # noqa: BLE001
                    logger.warning("catalog API manufacturers failed (%s) — CSV fallback", exc)
            if _cache.manufacturers is None:
                rows = _read_csv_dict(_DATA_DIR / "manufacturers.csv")
                _cache.manufacturers = {r["Source"]: r for r in rows}
            logger.info("Loaded %d Wrightsoft manufacturers", len(_cache.manufacturers))
    return _cache.manufacturers


def load_generic_parts() -> dict[str, dict[str, Any]]:
    """generic_id → row with Category / Description / Units."""
    with _lock:
        if _cache.generic_parts is None:
            client = _get_client()
            if client is not None:
                try:
                    # 3,178 generics — fits under the API's 5000 ceiling
                    items = client.generics(limit=5000)
                    _cache.generic_parts = {
                        (r.get("item") or ""): _api_to_csv_generic(r)
                        for r in items if r.get("item")
                    }
                except Exception as exc:  # noqa: BLE001
                    logger.warning("catalog API generics failed (%s) — CSV fallback", exc)
            if _cache.generic_parts is None:
                rows = _read_csv_dict(_DATA_DIR / "generic_parts.csv")
                _cache.generic_parts = {r["Item"]: r for r in rows}
            logger.info("Loaded %d Wrightsoft generic parts", len(_cache.generic_parts))
    return _cache.generic_parts


def load_mapped_parts() -> list[dict[str, Any]]:
    """Generic-part → manufacturer-SKU mapping rows. Mapping API row
    shape is already snake_case-matching the existing callers
    (generic_item, preferred_source, manufacturer_partnum, etc.) —
    no key translation needed for this one."""
    with _lock:
        if _cache.mapped_parts is None:
            rows: Optional[list[dict[str, Any]]] = None
            client = _get_client()
            if client is not None:
                try:
                    # 4,112 rows — paginate twice to be safe against
                    # any future row growth. API ceiling is 5000 per
                    # call but pagination would require an offset
                    # param which the v1 API lacks; rely on the 5000
                    # ceiling for now.
                    rows = _fetch_all_mapped_parts(client)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("catalog API mapped_parts failed (%s) — CSV fallback", exc)
            if rows is None:
                rows = _read_csv_dict(_DATA_DIR / "mapped_parts.csv")
            _cache.mapped_parts = rows
            # Build indexes
            idx: dict[str, list[dict[str, Any]]] = defaultdict(list)
            sku_idx: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in rows:
                gid = r.get("generic_item")
                if not gid:
                    continue
                idx[gid].append(r)
                sku = (r.get("manufacturer_partnum") or "").strip()
                if sku:
                    sku_idx[sku].append(r)
            _cache.mapped_by_generic = dict(idx)
            _cache.mapped_by_sku = dict(sku_idx)
            logger.info(
                "Loaded %d Wrightsoft mapped parts (%d distinct generics, %d distinct SKUs)",
                len(rows), len(_cache.mapped_by_generic), len(_cache.mapped_by_sku),
            )
    return _cache.mapped_parts


def _fetch_all_mapped_parts(client) -> list[dict[str, Any]]:
    """Bulk fetch via the catalog API's paginating /mappings endpoint.
    Single round-trip for the full table (4k+ rows fit in one call;
    the SDK paginates if the catalog grows past the limit ceiling)."""
    return client.mappings(limit=5000)


def load_fitting_template_codes() -> set[str]:
    """Day-15 — return the set of canonical fitting codes Tom's
    standard template defines. Used to flag non-standard fittings
    on incoming Wrightsoft BOMs.

    API-only — no local CSV fallback yet. When CATALOG_API_URL is
    unset OR the call fails, returns an empty set, which makes
    is_standard_fitting_code() answer 'unknown' (no flagging).
    The bom service should treat empty-set as 'classifier disabled,
    do not flag', NOT 'everything is non-standard'.
    """
    with _lock:
        if _cache.fitting_template_codes is not None:
            return _cache.fitting_template_codes
        codes: set[str] = set()
        client = _get_client()
        if client is not None:
            try:
                rows = client.fitting_template()
                codes = {(r.get("fitting_code") or "").strip()
                         for r in rows
                         if r.get("fitting_code")}
                logger.info("Loaded %d canonical fitting codes from catalog API",
                            len(codes))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "fitting-template load failed (%s) — non-standard "
                    "fitting flagging disabled for this process", exc,
                )
        _cache.fitting_template_codes = codes
        return codes


def is_standard_fitting_code(code: Optional[str]) -> Optional[bool]:
    """Day-15 classifier.

    Returns:
      True  — code is in Tom's canonical template
      False — code is not in the template (FLAG as non-standard)
      None  — classifier disabled (no template loaded; don't flag)
    """
    codes = load_fitting_template_codes()
    if not codes:
        return None  # classifier disabled
    if not code:
        return False
    return code.strip() in codes


def load_dfunit() -> list[dict[str, Any]]:
    """Ductless / mini-split / heat-pump equipment library. 19 columns:
    Manufacturer (4-char), Model, SysType (H=heat pump / A=AC),
    UnitType (OS=Outdoor Split, IW=Indoor Wall, IC=Indoor Ceiling,
    OM=Outdoor Multi, ID=Indoor Duct, IA/IF/IU=various indoor styles),
    ClgCap (BTU), HtgCap (BTU), Series, Width / Depth / Height / Weight,
    MaxPipeLen / MaxPipeHeight.

    Day-11 — also builds a by-Model index so lookup_dfunit_by_model()
    is O(1)."""
    with _lock:
        if _cache.dfunit is None:
            rows: Optional[list[dict[str, Any]]] = None
            client = _get_client()
            if client is not None:
                try:
                    api_rows = client.dfunit(limit=2000)
                    rows = [_api_to_csv_dfunit(r) for r in api_rows]
                except Exception as exc:  # noqa: BLE001
                    logger.warning("catalog API dfunit failed (%s) — CSV fallback", exc)
            if rows is None:
                rows = _read_csv_dict(_DATA_DIR / "DFUnit.csv")
            _cache.dfunit = rows
            idx: dict[str, dict[str, Any]] = {}
            for r in rows:
                model = (r.get("Model") or "").strip()
                if model:
                    # Last wins on dupes (catalog has <5).
                    idx[model] = r
            _cache.dfunit_by_model = idx
            logger.info(
                "Loaded %d Wrightsoft DFUnit entries (%d distinct models)",
                len(rows), len(idx),
            )
    return _cache.dfunit


def lookup_dfunit_by_model(model: str) -> Optional[dict[str, Any]]:
    """Return the DFUnit row whose Model column matches exactly,
    or None. Case-sensitive — Wrightsoft model numbers are mixed-case
    and authoritative (e.g. 38MARBQ24AA3, not 38marbq24aa3)."""
    if not model:
        return None
    load_dfunit()  # populates _cache.dfunit_by_model
    return (_cache.dfunit_by_model or {}).get(model.strip())


def lookup_dfunit_by_capacity(
    *,
    cooling_btu: Optional[float] = None,
    heating_btu: Optional[float] = None,
    manufacturer: Optional[str] = None,
    sys_type: Optional[str] = None,
    unit_type: Optional[str] = None,
    tolerance_pct: float = 0.10,
) -> list[dict[str, Any]]:
    """Find DFUnit rows matching a capacity target within tolerance.

    Filters in priority order:
      manufacturer (4-char code, exact match) →
      sys_type ('H' heat pump / 'A' AC, exact) →
      unit_type ('OS'/'IW'/etc., exact) →
      capacity (cooling or heating BTU within +/- tolerance_pct)

    Sorted: smallest absolute capacity-delta first.

    Returns [] when nothing matches.
    """
    rows = load_dfunit()
    out = list(rows)

    if manufacturer:
        mfr = manufacturer.upper()
        out = [r for r in out if (r.get("Manufacturer") or "").upper() == mfr]
    if sys_type:
        out = [r for r in out if (r.get("SysType") or "") == sys_type]
    if unit_type:
        out = [r for r in out if (r.get("UnitType") or "") == unit_type]

    target = cooling_btu if cooling_btu is not None else heating_btu
    target_col = "ClgCap" if cooling_btu is not None else "HtgCap"
    if target:
        def _delta(r):
            try:
                v = float(r.get(target_col) or 0)
            except (TypeError, ValueError):
                return float("inf")
            return abs(v - target)
        tol_band = target * tolerance_pct
        out = [r for r in out if _delta(r) <= tol_band]
        out.sort(key=_delta)

    return out


def dfunit_line_spec(row: dict[str, Any]) -> dict[str, Any]:
    """Project a DFUnit row into a compact spec dict suitable for
    surfacing as line-item metadata. Caller is responsible for
    handling None (when no DFUnit match was found)."""
    def _float(k):
        try:
            v = row.get(k)
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None
    return {
        "manufacturer":   row.get("Manufacturer") or None,
        "model":          row.get("Model") or None,
        "sys_type":       row.get("SysType") or None,
        "unit_type":      row.get("UnitType") or None,
        "cooling_btu":    _float("ClgCap"),
        "heating_btu":    _float("HtgCap"),
        "width_in":       _float("Width"),
        "depth_in":       _float("Depth"),
        "height_in":      _float("Height"),
        "weight_lb":      _float("Weight"),
    }


# ─── AHRI per-model spec lookup (Day-15) ───────────────────────────
#
# The AHRI tree has 1.4M rows — too big to load locally. Instead we
# query the catalog API per model number and memoize. Cache hits (incl.
# negative "not found" results) stay in-process for the life of the
# worker so a BOM with the same equipment listed multiple times only
# hits the API once.

def _query_ahri_by_model(model: str) -> Optional[dict[str, Any]]:
    """Hit the catalog API for the first AHRI unit matching this
    condenser model. Returns the row dict, or None if not found or the
    catalog isn't reachable. The cache layer is in lookup_ahri_by_model.

    Day-16 fix: each product-type call is wrapped independently so a
    slow / timed-out HP lookup doesn't abort the AC + FURNACE attempts.
    Trane condensers in particular live under AC (not HP) and the
    HP-side scan was hitting the SDK 15 s timeout for some models."""
    client = _get_client()
    if client is None:
        return None
    # Try HP, then AC, then FURNACE — most useful product types for
    # residential Wrightsoft BOMs. Each call is independent so the
    # error on one type doesn't poison the next.
    for product_type in ("HP", "AC", "FURNACE"):
        try:
            rows = client.ahri(product_type, condenser_model=model, limit=1)
        except Exception as exc:  # noqa: BLE001 — best-effort enrichment
            logger.warning("AHRI %s lookup failed for %s — %s",
                           product_type, model, exc)
            continue
        if rows:
            row = dict(rows[0])
            row["product_type"] = product_type
            return row
    return None


def lookup_ahri_by_model(model: str) -> Optional[dict[str, Any]]:
    """Memoized per-process AHRI lookup by condenser model. Returns
    the AHRI row (with product_type added) or None when no match."""
    if not model:
        return None
    key = model.strip()
    if not key:
        return None
    if _cache.ahri_by_model is None:
        _cache.ahri_by_model = {}
    if key not in _cache.ahri_by_model:
        _cache.ahri_by_model[key] = _query_ahri_by_model(key)
    return _cache.ahri_by_model[key]


def ahri_line_spec(row: dict[str, Any]) -> dict[str, Any]:
    """Project an AHRI row into a compact spec dict the BOM line can
    carry as metadata (drives the PDF / XLS efficiency columns)."""
    if not row:
        return {}
    return {
        "product_type":   row.get("product_type") or None,
        "manufacturer":   row.get("ahri_manufacturer") or row.get("manufacturer") or None,
        "condenser_model": row.get("condenser_model") or None,
        "coil_model":     row.get("coil_model") or None,
        "capacity_btu":   row.get("capacity"),
        "seer":           row.get("seer"),
        "eer95":          row.get("eer95"),
        "hspf":           row.get("hspf"),
        "afue":           row.get("afue"),
        "ari_refno":      row.get("ari_refno") or None,
        "trade_name":     row.get("trade_name") or None,
    }


# ---------------------------------------------------------------------
# Lookup helpers — built on top of the loaders above.
# Phase 2 will extend with category-section mapping; Phase 4 with AHRI.
# ---------------------------------------------------------------------

def all_categories() -> list[str]:
    """Sorted list of every category code Wrightsoft knows."""
    return sorted(load_categories().keys())


def all_manufacturer_codes() -> list[str]:
    """Sorted list of every supplier/manufacturer 4-char code."""
    return sorted(load_manufacturers().keys())


def lookup_skus_for_generic(
    generic_id: str,
    supplier_pref: Optional[str] = None,
) -> list[tuple[str, str]]:
    """Return [(supplier_code, manufacturer_partnum)] for a generic_id.

    If supplier_pref is given AND that supplier has a mapping, only the
    matching rows are returned (preserves quantity-variant ordering).
    Otherwise every supplier match is returned in file order.

    Returns [] if the generic_id has no mapping (caller decides whether
    to fall back to displaying the generic description, ask the AI, etc).
    """
    load_mapped_parts()  # populates _cache.mapped_by_generic
    rows = (_cache.mapped_by_generic or {}).get(generic_id, [])
    out = [(r["preferred_source"], r["manufacturer_partnum"]) for r in rows]
    if supplier_pref:
        filtered = [(s, p) for s, p in out if s == supplier_pref]
        if filtered:
            return filtered
    return out


def lookup_mapping_by_sku(sku: str) -> Optional[dict[str, Any]]:
    """Reverse lookup: given a manufacturer SKU the contractor would
    actually order (e.g. 'Q4PC100XRED' or '38MARBQ24AA3'), return the
    matching mapped_parts.csv row — or None.

    Returns the first match when multiple suppliers carry the same SKU
    (rare but possible — same OEM part stocked through different
    distributors). Caller can ask for the generic_item / preferred_source
    out of the returned dict.

    Used by the BOM Engine to verify AI-emitted SKUs against the bundled
    catalog — when an AI line's SKU is in the catalog, we know the
    answer is real and can re-tag the source from 'ai_*' to a verified
    provenance.
    """
    if not sku:
        return None
    load_mapped_parts()  # populates _cache.mapped_by_sku
    rows = (_cache.mapped_by_sku or {}).get(sku.strip(), [])
    return rows[0] if rows else None


def category_for_generic(generic_id: str) -> Optional[str]:
    """Return the Wrightsoft category code for a generic_id, or None
    if unknown. The category IS the bridge between an individual SKU
    and the contractor section structure — see section_for_category."""
    parts = load_generic_parts()
    row = parts.get(generic_id)
    return row.get("Category") if row else None


# ---------------------------------------------------------------------
# Phase 2 — Wrightsoft category → contractor section mapping
#
# The contractor sample BOM (`Lot 1 T075 Elm ACL`) groups items into
# four sections: Equipment / Duct System Equipment / Rheia Duct System
# Equipment / Labor. Wrightsoft has 13 raw categories. The mapping
# below routes each Wrightsoft category to the appropriate contractor
# section. Categories that don't fit cleanly (RHALL = radiant heating,
# HVACCTLS = controls, MSRP = mini-split refrigeration pipes) are
# explicitly flagged so future updates don't silently fall through.
#
# This mapping is the SOURCE OF TRUTH for grouping in PDF + JSON BOM
# output. Anything that wants to know "which section does this SKU
# belong in" goes through section_for_category.
# ---------------------------------------------------------------------

# Contractor section labels — match the sample BOM verbatim so the
# generated PDF reads the same as a designer-built spreadsheet.
SECTION_EQUIPMENT       = "Equipment"
SECTION_DUCT_SYSTEM     = "Duct System Equipment"
SECTION_RHEIA           = "Rheia Duct System Equipment"
SECTION_LABOR           = "Labor"
SECTION_OTHER           = "Other"  # fallback — investigate if it ever appears

# Wrightsoft category codes (13 total) → contractor section.
# Verified against Wrightsoft's categories.csv.
_CATEGORY_TO_SECTION: dict[str, str] = {
    # Standard duct-system fittings — the bulk of any project's BOM.
    "DFRBTR":   SECTION_DUCT_SYSTEM,    # Duct boots and registers
    "DFRELB":   SECTION_DUCT_SYSTEM,    # Duct elbows
    "DFRPLN":   SECTION_DUCT_SYSTEM,    # Duct plenum fittings
    "DFRTKO":   SECTION_DUCT_SYSTEM,    # Duct take offs
    "DFRTEE":   SECTION_DUCT_SYSTEM,    # Duct tees and wyes
    "DFRTRS":   SECTION_DUCT_SYSTEM,    # Duct transitions
    "DSRCT":    SECTION_DUCT_SYSTEM,    # Rectangular ducts
    "DSRND":    SECTION_DUCT_SYSTEM,    # Round ducts

    # Rheia / high-velocity small-diameter — universal across ProCalcs
    # projects per Tom + Richard 2026-04-29. Lives in its own section
    # so designers can see Rheia parts at a glance.
    "HVDALL":   SECTION_RHEIA,          # High velocity duct system

    # Equipment-adjacent
    "EACCESSY": SECTION_EQUIPMENT,      # Equipment accessories
    "HVACCTLS": SECTION_EQUIPMENT,      # HVAC Control System
    "MSRP":     SECTION_EQUIPMENT,      # Mini Split Refrigeration Pipes

    # Radiant heating — appears in catalog but rare in the residential
    # forced-air projects ProCalcs typically handles. Not in the sample
    # contractor BOM. Routed to Equipment as the safest bucket; revisit
    # if any radiant-heavy project surfaces.
    "RHALL":    SECTION_EQUIPMENT,      # Radiant heating
}

# Equipment items decoded from EQUIP / ZEQUIP / DFUnit blocks don't
# carry a Wrightsoft category code (they're equipment, not parts). They
# go straight to the Equipment section.
EQUIPMENT_CATEGORY_PSEUDO = "_EQUIPMENT"
_CATEGORY_TO_SECTION[EQUIPMENT_CATEGORY_PSEUDO] = SECTION_EQUIPMENT


def section_for_category(category: Optional[str]) -> str:
    """Map a Wrightsoft category code to the contractor section the
    line item should appear under. Unknown categories return
    SECTION_OTHER so they're visible in output rather than silently
    bucketed into Equipment.

    Pass EQUIPMENT_CATEGORY_PSEUDO for lines that come from the
    equipment library, not the generic-parts catalog.
    """
    if not category:
        return SECTION_OTHER
    return _CATEGORY_TO_SECTION.get(category, SECTION_OTHER)


def section_for_generic(generic_id: str) -> str:
    """Convenience: lookup category, then route to section. Returns
    SECTION_OTHER if the generic_id isn't in the catalog at all."""
    cat = category_for_generic(generic_id)
    return section_for_category(cat)


def all_sections() -> list[str]:
    """The four canonical sections, in display order. Used by the PDF
    template + bom_service formatter to emit consistent ordering."""
    return [
        SECTION_EQUIPMENT,
        SECTION_DUCT_SYSTEM,
        SECTION_RHEIA,
        SECTION_LABOR,
    ]


def categories_in_section(section: str) -> list[str]:
    """Reverse lookup — every REAL Wrightsoft category routed to a
    given section. Pseudo-categories (those prefixed with '_', used
    internally for items that don't carry a Wrightsoft category like
    raw equipment) are excluded so callers don't try to look them up
    in load_categories() and get a KeyError."""
    return sorted(
        c for c, s in _CATEGORY_TO_SECTION.items()
        if s == section and not c.startswith("_")
    )


# ---------------------------------------------------------------------
# Diagnostic / health
# ---------------------------------------------------------------------

def cache_summary() -> dict[str, Any]:
    """Diagnostic view of what's loaded — used by /api/v1/health and
    by tests that want to confirm the catalog is reachable without
    calling lookup helpers."""
    return {
        "data_dir": str(_DATA_DIR),
        "categories":     len(_cache.categories) if _cache.categories else 0,
        "manufacturers":  len(_cache.manufacturers) if _cache.manufacturers else 0,
        "generic_parts":  len(_cache.generic_parts) if _cache.generic_parts else 0,
        "mapped_parts":   len(_cache.mapped_parts) if _cache.mapped_parts else 0,
        "mapped_unique_generics": (
            len(_cache.mapped_by_generic) if _cache.mapped_by_generic else 0
        ),
        "dfunit":         len(_cache.dfunit) if _cache.dfunit else 0,
    }


# ---------------------------------------------------------------------
# Day-11 — coverage diagnostic: what fraction of the catalog has at
# least one supplier mapping, broken down per category + per supplier.
# Powers the SPA "Catalog Coverage" diagnostic page so Richard's team
# can see at a glance which categories have the worst coverage and
# prioritize what to add to mapped_parts.csv next.
# ---------------------------------------------------------------------

def coverage_report() -> dict[str, Any]:
    """Build a coverage report from the bundled CSVs.

    Per-category breakdown:
        category code, human description, total generics in category,
        generics with at least one supplier mapping, coverage %,
        per-supplier mapping count.

    Per-supplier roll-up:
        supplier code, mfr name, distinct generics covered.

    Totals at the top so the SPA can show a single-number headline.
    """
    cats = load_categories()
    mfrs = load_manufacturers()
    generics = load_generic_parts()
    mapped = load_mapped_parts()
    mapped_by_generic = _cache.mapped_by_generic or {}

    # Index generic IDs by category
    generics_by_cat: dict[str, list[str]] = defaultdict(list)
    for gid, row in generics.items():
        cat = (row.get("Category") or "").strip() or "_UNCATEGORIZED"
        generics_by_cat[cat].append(gid)

    # Per-supplier: distinct generics covered
    supplier_generics: dict[str, set[str]] = defaultdict(set)
    for m in mapped:
        src = (m.get("preferred_source") or "").strip()
        gid = (m.get("generic_item") or "").strip()
        if src and gid:
            supplier_generics[src].add(gid)

    # Per-category breakdown
    categories: list[dict[str, Any]] = []
    for cat_code, cat_generics in generics_by_cat.items():
        total_in_cat = len(cat_generics)
        covered = sum(1 for gid in cat_generics if gid in mapped_by_generic)
        coverage_pct = round(100.0 * covered / total_in_cat, 1) if total_in_cat else 0.0

        # Per-supplier counts within this category
        per_supplier: dict[str, int] = defaultdict(int)
        for gid in cat_generics:
            for m in mapped_by_generic.get(gid, []):
                src = (m.get("preferred_source") or "").strip()
                if src:
                    per_supplier[src] += 1
        suppliers = [
            {
                "supplier_code": s,
                "name":          (mfrs.get(s) or {}).get("Name") or s,
                "mapped_count":  n,
            }
            for s, n in sorted(per_supplier.items(), key=lambda kv: -kv[1])
        ]

        categories.append({
            "category":         cat_code,
            "description":      cats.get(cat_code, "(uncategorized)"),
            "total_generics":   total_in_cat,
            "covered_generics": covered,
            "coverage_pct":     coverage_pct,
            "suppliers":        suppliers,
        })

    # Sort categories: worst coverage first (most actionable for Richard)
    categories.sort(key=lambda c: (c["coverage_pct"], -c["total_generics"]))

    suppliers_rollup = [
        {
            "supplier_code":  s,
            "name":           (mfrs.get(s) or {}).get("Name") or s,
            "distinct_generics_covered": len(gids),
        }
        for s, gids in sorted(
            supplier_generics.items(),
            key=lambda kv: -len(kv[1]),
        )
    ]

    total_generics = len(generics)
    total_covered  = len(mapped_by_generic)
    overall_pct = round(100.0 * total_covered / total_generics, 1) if total_generics else 0.0

    return {
        "totals": {
            "generic_parts":           total_generics,
            "covered_generics":        total_covered,
            "overall_coverage_pct":    overall_pct,
            "mapped_supplier_variants": len(mapped),
            "suppliers":               len(supplier_generics),
            "dfunit_models":           len(_cache.dfunit_by_model or {}),
        },
        "categories":        categories,
        "suppliers":         suppliers_rollup,
    }
