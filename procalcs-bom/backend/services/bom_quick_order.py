"""
bom_quick_order.py — Quick Order Summary builder (Day-17 / Tom's #1).

Walks a BOM's line_items and produces a contractor-facing rollup:
'buy at these quantities; we did the math.' Replaces the manual scan
of identical Wrightsoft rows the contractor would otherwise do on
paper before placing supply orders.

Two pieces of intelligence:
1. GROUPING — identical materials (Wrightsoft splits the same SKU
   across multiple rows because each row is a separate run to a
   different location). We group them back together by SKU family +
   nominal size so the contractor sees one line per orderable thing.
2. PACKAGING CONVERSION — duct ships in fixed-length boxes/sticks;
   contractors order in box-count. We translate raw LF to box count
   with ceil() so the contractor always has enough for waste.

Detailed line items stay intact (Wrightsoft's per-run layout is
preserved in the main BOM table). The Quick Order Summary is an
additional artifact at the top.

Deterministic only — no AI. If a SKU prefix isn't in the packaging
table, we surface the raw quantity without box conversion so the
contractor at least sees the total.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional


# ─── Packaging knowledge ───────────────────────────────────────────
#
# Maps Wrightsoft SKU prefix (the first 2-4 chars before the digits)
# to the standard packaging convention. Tom confirmed flex = 25 ft.
# Rect fiberglass + sheet-metal sticks are educated defaults — verify
# with Richard and adjust the table; the rest of the system rolls up
# automatically when these numbers change.

_PACKAGING: Dict[str, Dict[str, Any]] = {
    # Round vinyl flex duct (insulated)
    "DDVn": {"per_box": 25.0, "unit": "ft", "container": "box",
             "category": "Flex duct"},
    # Generic flex duct family
    "DDFl": {"per_box": 25.0, "unit": "ft", "container": "box",
             "category": "Flex duct"},
    # Rectangular fiberglass duct — cut from 4'×8' sheet board.
    # Per Tom (Jun 27): the duct is typically 4' long because the 8'
    # side is what gets cut down and folded around the cross-section.
    # Pre-made fiberglass items (mixing boxes, end caps) stay 'each'
    # below — their SKUs live under FBEC / FJB / FPL etc.
    "DRFg": {"per_box": 4.0, "unit": "ft", "container": "4-ft length",
             "category": "Fiberglass duct (cut from 4×8 board)"},
    # Rectangular sheet metal duct
    "DRMt": {"per_box":  5.0, "unit": "ft", "container": "stick",
             "category": "Sheet metal duct"},
    # Round sheet metal duct
    "DRSt": {"per_box":  5.0, "unit": "ft", "container": "stick",
             "category": "Sheet metal duct"},

    # Fittings — sold individually
    "FBTI": {"per_box": 1.0, "unit": "ea", "container": "ea",
             "category": "Ceiling boots"},
    "FBEC": {"per_box": 1.0, "unit": "ea", "container": "ea",
             "category": "End caps"},
    "FCLR": {"per_box": 1.0, "unit": "ea", "container": "ea",
             "category": "Collars"},
    "FRGR": {"per_box": 1.0, "unit": "ea", "container": "ea",
             "category": "Grilles / registers"},
    "FJB":  {"per_box": 1.0, "unit": "ea", "container": "ea",
             "category": "Junction boxes"},
    "FPL":  {"per_box": 1.0, "unit": "ea", "container": "ea",
             "category": "Plenums / take-offs"},
    "FTO":  {"per_box": 1.0, "unit": "ea", "container": "ea",
             "category": "Take-offs"},
    # Synthetic IDs from the .rup-direct adapter — keep them visible
    "DUCT":      {"per_box": 1.0, "unit": "run", "container": "run",
                  "category": "Duct runs (from .rup)"},
    "REGISTERS": {"per_box": 1.0, "unit": "ea", "container": "ea",
                  "category": "Registers (from .rup)"},
    "FITTINGS":  {"per_box": 1.0, "unit": "ea", "container": "ea",
                  "category": "Fittings (from .rup)"},
}


def _lookup_packaging(sku: str) -> Optional[Dict[str, Any]]:
    """Match the SKU's leading prefix against the packaging table.
    Case-insensitive — Wrightsoft writes prefixes mixed-case
    (DDVn04MI), our table holds them as `DDVn` for readability."""
    if not sku:
        return None
    upper = sku.upper()
    # Prefer the longer, more specific prefix
    for prefix in sorted(_PACKAGING.keys(), key=lambda x: -len(x)):
        if upper.startswith(prefix.upper()):
            return _PACKAGING[prefix]
    return None


# ─── Size extraction for grouping ──────────────────────────────────
#
# Wrightsoft SKUs encode the nominal size in the digits after the
# family prefix. Examples:
#   DDVn08MI       → 8" round
#   FBTI-1010-7    → 10" x 10" face x 7" round neck
#   FCLR-7         → 7" round
#   FRGRMCG-1614   → 16" x 14" face
#   DRFg1818MI     → 18" x 18" rectangular
#
# We extract the leading 2-4 digit size token after the family
# prefix to group identical sizes together.

_SIZE_RE = re.compile(r"^[A-Z]{2,6}-?(\d{2,4})", re.IGNORECASE)


def _extract_size_token(sku: str) -> str:
    """Return the leading size token (e.g. '08', '1614') or the SKU
    itself when we can't parse a size. Used as part of the group key."""
    if not sku:
        return ""
    m = _SIZE_RE.match(sku)
    return m.group(1) if m else sku


def _format_size_label(size_token: str, sku: str) -> str:
    """Format the size token for human reading. Two-digit tokens are
    diameters (8 → '8"'); 4-digit tokens are face dimensions
    (1614 → '16x14')."""
    if not size_token:
        return ""
    if size_token.isdigit():
        if len(size_token) <= 2:
            n = int(size_token)
            return f'{n}"'
        if len(size_token) == 4:
            return f'{int(size_token[:2])}x{int(size_token[2:])}'
        # 3 digits — unusual; show raw
        return size_token
    return size_token


# ─── Public API ────────────────────────────────────────────────────

# ─── Install consumables (Day-17, Tom's meeting + Richard Jun 29) ───
#
# Wrightsoft never itemizes mastic, foil tape, flex tape, or screws —
# but every install needs them. Compute deterministically from the
# fitting / flex-run counts on the BOM. Multipliers come from the
# contractor's ClientProfile.consumables_rules; the defaults below
# match the dataclass defaults so a missing profile still produces
# a sensible rollup.
#
# Per-unit cost (gallon, roll, box) comes from ClientProfile.supplier
# when present, else 0 — which trips the existing "needs price /
# $0 OK" affordance on the BOM result page, same as commodity stubs.

_CONSUMABLES_DEFAULTS = {
    "joints_per_mastic_gallon": 75,
    "joints_per_foil_roll":     30,
    "flex_runs_per_flex_roll":  40,
    "fittings_per_screw_box":   150,
    "include_mastic":           True,
    "include_foil_tape":        True,
    "include_flex_tape":        True,
    "include_screws":           True,
}

# SKU-prefix → joint-classification, used to count joints + flex runs
# from the BOM line_items.
_JOINT_PREFIXES = ("FBTI", "FBEC", "FCLR", "FRGR", "FJB", "FPL", "FTO")
_FLEX_PREFIXES  = ("DDVn", "DDFl")


def _classify_for_consumables(sku: str) -> str:
    """Return 'flex_run' for a flex-duct row, 'joint' for any fitting
    row, '' otherwise. Used to count consumable inputs."""
    u = (sku or "").upper()
    for p in _FLEX_PREFIXES:
        if u.startswith(p.upper()):
            return "flex_run"
    for p in _JOINT_PREFIXES:
        if u.startswith(p):
            return "joint"
    return ""


def _consumable_row(category_label: str, label: str, total: int,
                    container: str, unit_price: float) -> Dict[str, Any]:
    """Build a single Quick-Order rollup row for one consumable type."""
    return {
        "category":      "Install consumables",
        "label":         label,
        "size":          category_label,  # reused column for the short name
        "total":         float(total),
        "unit":          container,
        "container":     container,
        "per_container": 1.0,
        "containers":    int(total),
        "run_count":     0,
        "sku_count":     1,
        "unit_price":    float(unit_price or 0),
        "total_price":   float((unit_price or 0) * total),
        "is_consumable": True,
    }


def compute_consumables(line_items: List[Dict[str, Any]],
                        rules: Optional[Dict[str, Any]] = None,
                        supplier: Optional[Dict[str, Any]] = None
                        ) -> List[Dict[str, Any]]:
    """Compute the install-consumables rollup rows.

    rules    — dict shaped like ConsumablesRules.to_dict(); missing keys
               fall back to _CONSUMABLES_DEFAULTS.
    supplier — dict shaped like SupplierInfo.to_dict(); provides per-unit
               costs (mastic_cost_per_gallon, tape_cost_per_roll, etc.).
               Missing → unit_price 0, which is fine; the SPA's
               '$0 OK / needs price' affordance handles it.
    """
    r = {**_CONSUMABLES_DEFAULTS, **(rules or {})}
    s = supplier or {}

    joints = 0
    flex_runs = 0
    fittings = 0
    for li in line_items or []:
        sku = (li.get("generic_id") or li.get("sku") or "").strip()
        if not sku:
            continue
        qty = float(li.get("quantity") or 0)
        if qty <= 0:
            continue
        kind = _classify_for_consumables(sku)
        if kind == "joint":
            joints   += int(round(qty))
            fittings += int(round(qty))
        elif kind == "flex_run":
            flex_runs += 1   # one connection per flex-duct line, regardless of LF

    out: List[Dict[str, Any]] = []
    if r["include_mastic"] and joints > 0:
        gallons = math.ceil(joints / max(1, int(r["joints_per_mastic_gallon"])))
        out.append(_consumable_row(
            "Mastic",
            f"Duct mastic — seals ~{r['joints_per_mastic_gallon']} joints per gallon",
            gallons, "gallon", float(s.get("mastic_cost_per_gallon") or 0),
        ))
    if r["include_foil_tape"] and joints > 0:
        rolls = math.ceil(joints / max(1, int(r["joints_per_foil_roll"])))
        out.append(_consumable_row(
            "Foil tape",
            f"UL-181A-P foil tape — ~{r['joints_per_foil_roll']} joints per roll",
            rolls, "roll", float(s.get("tape_cost_per_roll") or 0),
        ))
    if r["include_flex_tape"] and flex_runs > 0:
        rolls = math.ceil(flex_runs / max(1, int(r["flex_runs_per_flex_roll"])))
        out.append(_consumable_row(
            "Flex tape",
            f"UL-181B-FX flex-duct tape — ~{r['flex_runs_per_flex_roll']} flex runs per roll",
            rolls, "roll", float(s.get("tape_cost_per_roll") or 0),
        ))
    if r["include_screws"] and fittings > 0:
        boxes = math.ceil(fittings / max(1, int(r["fittings_per_screw_box"])))
        out.append(_consumable_row(
            "Sheet metal screws",
            f"Sheet metal screws — ~{r['fittings_per_screw_box']} attachments per box",
            boxes, "box", float(s.get("screws_cost_per_box") or 0),
        ))
    return out


def build_quick_order(line_items: List[Dict[str, Any]],
                      consumables_rules: Optional[Dict[str, Any]] = None,
                      supplier: Optional[Dict[str, Any]] = None
                      ) -> List[Dict[str, Any]]:
    """Return the Quick Order Summary rollup.

    Each entry:
        {
          "category":      str,    # e.g. "Flex duct"
          "label":         str,    # e.g. '8" round flex duct'
          "size":          str,    # e.g. '8"' / '16x14'
          "total":         float,  # summed quantity in the unit field
          "unit":          str,    # 'ft' | 'ea' | 'run'
          "container":     str,    # 'box' | 'stick' | 'ea'
          "per_container": float,  # e.g. 25.0
          "containers":    int,    # ceil(total / per_container)
          "run_count":     int,    # how many BOM rows rolled up here
        }

    Sorted by category then by size token so the PDF/XLS/SPA renderer
    can group with thin headers.
    """
    # group key = (sku_family_prefix, size_token)
    groups: Dict[tuple, Dict[str, Any]] = {}
    for li in line_items or []:
        sku = (li.get("generic_id") or li.get("sku") or "").strip()
        if not sku:
            continue
        qty = float(li.get("quantity") or 0)
        if qty <= 0:
            continue
        pkg = _lookup_packaging(sku)
        if pkg is None:
            # Unknown family — bucket by description so the contractor
            # still sees the total. Avoids silently dropping work.
            family = "_misc"
            category = "Other items"
            unit = (li.get("unit") or "ea").lower()
            container = unit
            per = 1.0
        else:
            # Take prefix up to first digit/dash; that's the family
            family = re.match(r"^[A-Z]+", sku.upper()).group(0)
            category = pkg["category"]
            unit = pkg["unit"]
            container = pkg["container"]
            per = float(pkg["per_box"])
        size = _extract_size_token(sku)
        key = (category, family, size)
        if key not in groups:
            groups[key] = {
                "category":      category,
                "label":         _label_for(li, family, size, pkg),
                "size":          _format_size_label(size, sku) if pkg else "",
                "total":         0.0,
                "unit":          unit,
                "container":     container,
                "per_container": per,
                "containers":    0,
                "run_count":     0,
                "skus":          set(),
            }
        groups[key]["total"] += qty
        groups[key]["run_count"] += 1
        groups[key]["skus"].add(sku)

    rows: List[Dict[str, Any]] = []
    for row in groups.values():
        if row["per_container"] > 0:
            row["containers"] = int(math.ceil(row["total"] / row["per_container"]))
        # Drop the set so the dict is JSON-serializable
        row["sku_count"] = len(row["skus"])
        row.pop("skus", None)
        rows.append(row)

    # Sort: ducts first, then fittings, then misc. Within each
    # category, sort by size token (8" before 10" before 12").
    _CATEGORY_ORDER = [
        "Flex duct",
        "Fiberglass duct (cut from 4×8 board)",
        "Rectangular duct",
        "Sheet metal duct",
        "Ceiling boots", "Collars", "End caps",
        "Plenums / take-offs", "Take-offs",
        "Grilles / registers", "Junction boxes",
        "Duct runs (from .rup)", "Registers (from .rup)",
        "Fittings (from .rup)", "Other items",
        "Install consumables",
    ]
    cat_rank = {c: i for i, c in enumerate(_CATEGORY_ORDER)}

    def _sort_key(r):
        cat = r["category"]
        # Try to parse leading number for natural size sort
        size_n = 9999
        s = r["size"]
        m = re.match(r"(\d+)", s)
        if m:
            size_n = int(m.group(1))
        return (cat_rank.get(cat, 999), cat, size_n, s)

    rows.sort(key=_sort_key)

    # Append install consumables at the bottom — mastic, tape, screws.
    # Quantities derived from the joint / flex-run counts above.
    rows.extend(compute_consumables(line_items, consumables_rules, supplier))
    return rows


def _label_for(li: Dict[str, Any], family: str,
               size: str, pkg: Optional[Dict[str, Any]]) -> str:
    """Build a human label for the group. Prefers the description
    Wrightsoft put on the row (it's already contractor-friendly)
    truncated to the part before the comma."""
    desc = (li.get("description") or "").strip()
    if desc:
        # 'Round vinyl duct, D = 8", medium insulation' → 'Round vinyl duct, D = 8"'
        for sep in [",  medium", ",  med", ", medium", ", med"]:
            if sep in desc:
                desc = desc.split(sep)[0]
                break
        return desc[:80]
    if pkg:
        size_label = _format_size_label(size, "")
        return f'{size_label} {pkg["category"].lower()}'
    return family
