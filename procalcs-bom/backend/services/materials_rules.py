"""
Materials Rules Engine — deterministic line-item generator.

Walks the SKU catalog (services.sku_catalog) and emits BOM line items
based on parsed RUP ``design_data``. Each catalog entry declares:

  - ``trigger``  — a string from VALID_TRIGGERS that gates emission
  - ``quantity`` — a dict ``{mode: <str>, ...mode-specific args}``

The engine is intentionally simple: scope flags are computed once
from design_data, every catalog item is then evaluated independently.
No prompting, no external calls — pure Python — so the same design_data
always yields the same line items. Pricing comes from each item's
``default_unit_price`` (catalog) or, when non-zero, can be overridden
later by the contractor profile.

Public entry point:

    from services.materials_rules import generate_rule_lines
    lines = generate_rule_lines(design_data, output_mode="materials_only")

Returns a list of dicts shaped like::

    {
      "sku":         "10-00-190",
      "supplier":    "RHEA",
      "section":     "Rheia Duct System Equipment",
      "phase":       "Rough" | "Finish" | None,
      "description": "3-in Duct Uninsulated",
      "category":    "rheia"      # legacy bucket for existing PDF renderer
      "quantity":    856.0,
      "unit":        "ea" | "lf",
      "unit_cost":   0.0,
      "total_cost":  0.0,
      "trigger":     "rheia_in_scope",
      "rule_mode":   "rheia_per_lf",
      "source":      "rules_engine",
    }

Items with ``quantity == 0`` are filtered out — a triggered SKU with
no quantity is not "emit zero", it just means the design didn't match
that rule cleanly (e.g. no Rheia LF detected).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

try:
    from services import sku_catalog
except ImportError:  # pragma: no cover — flat-import fallback
    import sku_catalog  # type: ignore


logger = logging.getLogger('procalcs_bom')


# ---------------------------------------------------------------------------
# Scope flags — computed once per design_data
# ---------------------------------------------------------------------------

@dataclass
class Scope:
    """Boolean flags + counts pulled out of design_data so trigger
    evaluation is a cheap lookup."""
    # Equipment presence
    ahu_count: int = 0
    condenser_count: int = 0
    erv_count: int = 0
    heat_kit_count: int = 0
    # Duct shape
    rectangular_lf: float = 0.0
    round_vinyl_count: int = 0
    rheia_lf: float = 0.0           # total LF of small-diameter flexible duct (≤4")
    # Rheia-specific endpoint counts (pulled from registers if available,
    # else estimated from raw_rup_context)
    rheia_takeoffs: int = 0          # one trunk-to-branch per pair (in/out)
    rheia_high_sidewall_endpoints: int = 0
    rheia_ceiling_endpoints: int = 0
    # Fittings
    elbow_count: int = 0
    # General
    register_count: int = 0
    register_ceiling_round: int = 0
    register_ceiling_grill: int = 0
    register_high_wall_rect: int = 0

    @property
    def ahu_present(self) -> bool: return self.ahu_count > 0
    @property
    def condenser_present(self) -> bool: return self.condenser_count > 0
    @property
    def erv_present(self) -> bool: return self.erv_count > 0
    @property
    def heat_kit_present(self) -> bool: return self.heat_kit_count > 0
    @property
    def rectangular_duct(self) -> bool: return self.rectangular_lf > 0
    @property
    def round_vinyl_duct(self) -> bool: return self.round_vinyl_count > 0
    @property
    def rheia_in_scope(self) -> bool:
        # Either we detected small-diameter duct, OR a non-zero Rheia
        # endpoint count is in scope (covers parsers that don't emit ducts).
        return (
            self.rheia_lf > 0
            or self.rheia_high_sidewall_endpoints > 0
            or self.rheia_ceiling_endpoints > 0
        )


# Regexes used to mine raw_rup_context when structured arrays are sparse.
_DUCT_DIM_RE = re.compile(r"\b(\d{1,2})(?:\s*[\"x×])", re.IGNORECASE)
_DUCT_INCHES_RE = re.compile(r"\b(\d{1,2})\s*[-]?in\b", re.IGNORECASE)
_DUCT_3IN_RE = re.compile(r"\b3\s*[-]?in\b|\b3\"|\b3\s*inch", re.IGNORECASE)


def _extract_duct_diameters_inches(text: str) -> list[int]:
    """Best-effort parse of duct diameter mentions (in inches) from text.
    Used as a fallback when design_data.duct_runs is empty."""
    if not text:
        return []
    found: list[int] = []
    for match in _DUCT_DIM_RE.finditer(text):
        try:
            n = int(match.group(1))
            if 1 <= n <= 30:
                found.append(n)
        except ValueError:
            pass
    return found


def _has_small_diameter(text: str) -> bool:
    """Cheap heuristic: does the context mention 3-in / small-diameter duct?"""
    if not text:
        return False
    return bool(_DUCT_3IN_RE.search(text))


def _equipment_type(item: dict) -> str:
    """Normalize equipment type from the dict the parser emits.
    The parser uses several shapes; try them all."""
    if not isinstance(item, dict):
        return ""
    for key in ("type", "category", "kind", "name"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            # Normalize underscores → spaces so "air_handler" (parser
            # canonical form) matches the same keyword set as
            # "Air Handler" or "AHU - 1".
            return v.strip().lower().replace("_", " ")
    return ""


def compute_scope(design_data: dict) -> Scope:
    """Build a Scope from design_data. Tolerant of missing/None fields."""
    if not isinstance(design_data, dict):
        return Scope()

    s = Scope()

    # ─── Equipment ──────────────────────────────────────────────────────
    for eq in design_data.get("equipment") or []:
        t = _equipment_type(eq)
        # Wrightsoft tags AHUs as "AHU" or "AHU - 1" etc.
        if "ahu" in t or "air handler" in t:
            s.ahu_count += 1
        if "condenser" in t or "outdoor" in t or "compressor" in t:
            s.condenser_count += 1
        if "erv" in t or "energy recovery" in t:
            s.erv_count += 1
        if "heat" in t and ("kit" in t or "strip" in t or "electric" in t):
            s.heat_kit_count += 1

    # If no condenser explicitly tagged but at least one AHU is present
    # AND none of the AHUs are gas-fired (no "furnace" type), assume
    # 1 condenser per AHU. Industry default for residential split systems.
    if s.ahu_count > 0 and s.condenser_count == 0:
        any_furnace = any("furnace" in _equipment_type(e) or "gas" in _equipment_type(e)
                          for e in design_data.get("equipment") or [])
        if not any_furnace:
            s.condenser_count = s.ahu_count

    # Heat kit defaults to 1-per-AHU when no fossil-fuel furnace present
    # (matches sample BOM pattern of always shipping a kit with the AHU).
    if s.ahu_count > 0 and s.heat_kit_count == 0:
        any_furnace = any("furnace" in _equipment_type(e) or "gas" in _equipment_type(e)
                          for e in design_data.get("equipment") or [])
        if not any_furnace:
            s.heat_kit_count = s.ahu_count

    # ─── Duct runs ──────────────────────────────────────────────────────
    duct_runs = design_data.get("duct_runs") or []
    for d in duct_runs:
        if not isinstance(d, dict):
            continue
        shape = (d.get("shape") or d.get("type") or "").lower()
        diam = d.get("diameter_inches") or d.get("diameter") or 0
        try:
            diam = float(diam)
        except (TypeError, ValueError):
            diam = 0.0
        length = d.get("length_ft") or d.get("length") or d.get("lf") or 0
        try:
            length = float(length)
        except (TypeError, ValueError):
            length = 0.0

        if shape in ("rectangular", "rect"):
            s.rectangular_lf += length
        elif shape in ("round_vinyl", "vinyl"):
            s.round_vinyl_count += 1
        elif diam and diam <= 4:
            # Small-diameter rounds — treat as Rheia
            s.rheia_lf += length

    # ─── Fittings ───────────────────────────────────────────────────────
    for f in design_data.get("fittings") or []:
        if not isinstance(f, dict):
            continue
        ftype = (f.get("type") or f.get("kind") or "").lower()
        if "elbow" in ftype:
            s.elbow_count += int(f.get("quantity") or 1)

    # ─── Registers ──────────────────────────────────────────────────────
    registers = design_data.get("registers") or []
    s.register_count = len(registers)
    for r in registers:
        if not isinstance(r, dict):
            continue
        loc = (r.get("location") or r.get("placement") or "").lower()
        shape = (r.get("shape") or r.get("face") or "").lower()
        if "ceiling" in loc and "round" in shape:
            s.register_ceiling_round += 1
            s.rheia_ceiling_endpoints += 1
        elif "ceiling" in loc and ("grill" in shape or "rect" in shape):
            s.register_ceiling_grill += 1
        elif "high" in loc and "wall" in loc:
            s.register_high_wall_rect += 1
            s.rheia_high_sidewall_endpoints += 1

    # ─── Rheia fallback: when duct_runs are empty but raw_rup_context
    #     mentions small-diameter, infer from CFM count + room count ────
    ctx = design_data.get("raw_rup_context") or ""
    rheia_signal = (
        s.rheia_lf > 0
        or s.rheia_high_sidewall_endpoints > 0
        or s.rheia_ceiling_endpoints > 0
        or _has_small_diameter(ctx)
    )
    if rheia_signal and s.rheia_lf == 0:
        # Conservative LF estimate: ~30 LF per AHU + ~15 LF per room.
        # Room count from rooms array, or fall back to register count.
        room_count = len(design_data.get("rooms") or []) or s.register_count
        s.rheia_lf = max(30.0 * s.ahu_count + 15.0 * room_count, 100.0)

    # Take-offs: 1 per branch endpoint (high sidewall + ceiling).
    if s.rheia_in_scope and s.rheia_takeoffs == 0:
        s.rheia_takeoffs = max(
            s.rheia_high_sidewall_endpoints + s.rheia_ceiling_endpoints,
            # If we have no register data, fall back to room count
            len(design_data.get("rooms") or []),
            1,
        )

    return s


# ---------------------------------------------------------------------------
# Trigger evaluation
# ---------------------------------------------------------------------------

def evaluate_trigger(trigger: str, scope: Scope) -> bool:
    """Return True when a catalog entry's trigger matches the design scope."""
    if trigger == "always":
        return True
    if trigger == "ahu_present":
        return scope.ahu_present
    if trigger == "condenser_present":
        return scope.condenser_present
    if trigger == "erv_present":
        return scope.erv_present
    if trigger == "heat_kit_present":
        return scope.heat_kit_present
    if trigger == "rectangular_duct":
        return scope.rectangular_duct
    if trigger == "round_vinyl_duct":
        return scope.round_vinyl_duct
    if trigger == "rheia_in_scope":
        return scope.rheia_in_scope
    if trigger == "register_count":
        return scope.register_count > 0
    # Unknown trigger — log and skip
    logger.warning("Unknown trigger %r — skipping catalog item", trigger)
    return False


# ---------------------------------------------------------------------------
# Quantity resolvers — one per mode
# ---------------------------------------------------------------------------

def _resolve_source(source: str, scope: Scope) -> float:
    """Translate a 'source' string from the catalog into a numeric value
    pulled from the scope. Returns 0 if unknown."""
    if not source:
        return 0.0
    table = {
        "equipment.ahu":              scope.ahu_count,
        "equipment.condenser":        scope.condenser_count,
        "equipment.erv":              scope.erv_count,
        "equipment.heat_kit":         scope.heat_kit_count,
        "duct_runs.rectangular":      scope.rectangular_lf,
        "duct_runs.round_vinyl":      scope.round_vinyl_count,
        "registers":                  scope.register_count,
        "registers.ceiling_round":    scope.register_ceiling_round,
        "registers.ceiling_grill":    scope.register_ceiling_grill,
        "registers.high_wall_rect":   scope.register_high_wall_rect,
        "fittings.elbow":             scope.elbow_count,
    }
    if source not in table:
        logger.warning("Unknown quantity source %r", source)
    return float(table.get(source, 0))


def _qty_fixed(rule: dict, _scope: Scope) -> float:
    return float(rule.get("value") or 0)


def _qty_per_unit(rule: dict, scope: Scope) -> float:
    return _resolve_source(rule.get("source", ""), scope)


def _qty_per_lf(rule: dict, scope: Scope) -> float:
    return _resolve_source(rule.get("source", ""), scope)


def _qty_per_register(rule: dict, scope: Scope) -> float:
    return _resolve_source(rule.get("source", ""), scope)


def _qty_rheia_per_lf(rule: dict, scope: Scope) -> float:
    if not scope.rheia_in_scope or scope.rheia_lf <= 0:
        return 0.0
    divisor = rule.get("divisor")
    if divisor:
        try:
            return max(round(scope.rheia_lf / float(divisor)), 1)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0
    return scope.rheia_lf


def _qty_rheia_per_takeoff(rule: dict, scope: Scope) -> float:
    if not scope.rheia_in_scope:
        return 0.0
    # Inside / outside take-offs are paired 1:1 in the sample BOM,
    # so emit the same total regardless of the 'side' arg.
    return float(scope.rheia_takeoffs)


def _qty_rheia_per_endpoint(rule: dict, scope: Scope) -> float:
    if not scope.rheia_in_scope:
        return 0.0
    endpoint = (rule.get("endpoint") or "").lower()
    if endpoint == "high_sidewall":
        return float(scope.rheia_high_sidewall_endpoints)
    if endpoint == "ceiling":
        return float(scope.rheia_ceiling_endpoints)
    return 0.0


def _qty_fitting_count(rule: dict, scope: Scope) -> float:
    return _resolve_source(rule.get("source", ""), scope)


_QTY_RESOLVERS = {
    "fixed":              _qty_fixed,
    "per_unit":           _qty_per_unit,
    "per_lf":             _qty_per_lf,
    "per_register":       _qty_per_register,
    "rheia_per_lf":       _qty_rheia_per_lf,
    "rheia_per_takeoff":  _qty_rheia_per_takeoff,
    "rheia_per_endpoint": _qty_rheia_per_endpoint,
    "fitting_count":      _qty_fitting_count,
}


def resolve_quantity(rule: dict, scope: Scope) -> float:
    """Dispatch on rule['mode']. Unknown modes return 0 with a warning."""
    if not isinstance(rule, dict):
        return 0.0
    mode = rule.get("mode")
    fn = _QTY_RESOLVERS.get(mode)
    if not fn:
        logger.warning("Unknown quantity mode %r", mode)
        return 0.0
    try:
        return float(fn(rule, scope))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Quantity resolver failed for mode=%s: %s", mode, exc)
        return 0.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# Map catalog section → legacy "category" bucket so the existing PDF
# renderer / line-item formatter (which keys on category) keeps working
# without changes. Sections that don't map fall back to "consumable".
_SECTION_TO_CATEGORY = {
    "Equipment":                       "equipment",
    "Duct System Equipment":           "duct",
    "Rheia Duct System Equipment":     "rheia",
    "Labor":                           "labor",
}


def _unit_for(item: sku_catalog.SKUItem) -> str:
    """Best-guess unit string for the line item. Catalog doesn't store
    unit explicitly today, so infer from the quantity mode."""
    mode = (item.quantity or {}).get("mode", "")
    if mode in ("per_lf", "rheia_per_lf"):
        return "lf"
    return "ea"


def generate_rule_lines(
    design_data: dict,
    *,
    output_mode: str = "full",
    catalog: Optional[list[sku_catalog.SKUItem]] = None,
) -> list[dict]:
    """Emit deterministic line items for the given design.

    Args:
        design_data: parsed RUP envelope (output of /parse-rup .data field).
        output_mode: passed through to each line item's ``output_mode``
            field for downstream filtering. The engine itself is mode-
            agnostic — pricing / cost columns are always populated and
            the formatter strips what's not requested.
        catalog: override the catalog (used in tests). Defaults to the
            live catalog with disabled items excluded.

    Returns:
        list[dict] — one entry per emitted SKU, with quantity > 0.
    """
    scope = compute_scope(design_data)
    items = catalog if catalog is not None else sku_catalog.all_items(include_disabled=False)
    lines: list[dict] = []

    for sku_item in items:
        if not evaluate_trigger(sku_item.trigger, scope):
            continue
        qty = resolve_quantity(sku_item.quantity, scope)
        if qty <= 0:
            continue

        unit = _unit_for(sku_item)
        unit_cost = float(sku_item.default_unit_price or 0)
        total_cost = round(qty * unit_cost, 2) if unit_cost else 0.0

        lines.append({
            "sku":         sku_item.sku,
            "supplier":    sku_item.supplier,
            "section":     sku_item.section,
            "category":    _SECTION_TO_CATEGORY.get(sku_item.section, "consumable"),
            "phase":       sku_item.phase,
            "description": sku_item.description,
            "quantity":    qty,
            "unit":        unit,
            "unit_cost":   unit_cost,
            "total_cost":  total_cost,
            "trigger":     sku_item.trigger,
            "rule_mode":   (sku_item.quantity or {}).get("mode"),
            "source":      "rules_engine",
            "output_mode": output_mode,
        })

    return lines


def summarize_scope(scope: Scope) -> dict:
    """Return a JSON-safe dict of every flag/count for diagnostics."""
    keys = (
        "ahu_count", "condenser_count", "erv_count", "heat_kit_count",
        "rectangular_lf", "round_vinyl_count",
        "rheia_lf", "rheia_takeoffs",
        "rheia_high_sidewall_endpoints", "rheia_ceiling_endpoints",
        "elbow_count", "register_count",
        "register_ceiling_round", "register_ceiling_grill",
        "register_high_wall_rect",
    )
    out = {k: getattr(scope, k) for k in keys}
    out["rheia_in_scope"] = scope.rheia_in_scope
    return out
