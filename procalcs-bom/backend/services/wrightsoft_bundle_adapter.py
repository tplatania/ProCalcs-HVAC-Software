"""
wrightsoft_bundle_adapter.py — v2 equipment enrichment path.

The Windows extraction station runs RightSuite's COM interface
(`IRRXDocument.ValidateProject`) which writes a per-zone HVAC
equipment schedule to a BIFF-encoded Excel workbook. The Windows
session parses that with xlrd and produces JSON in the shape:

    {
      "<project name>": [
        {"zone": "AHU - 1", "fields": [
          {"name": "Cooling Manufacturer", "value": "Trane", "expected": ...},
          {"name": "Cooling Condenser",    "value": "5TTV0X60A1", ...},
          ...
        ]},
        ...
      ]
    }

This adapter walks that structure and emits per-zone BOM line
items in the same shape build_bom_from_wrightsoft_lines() consumes,
so equipment merges into the .xls-driven flow identically to the
existing .rup-derived path — but with fuller data (SEER / HSPF /
AFUE / cooling capacity come straight from Wrightsoft rather than
via an AHRI catalog round-trip) and better manufacturer coverage
(any manufacturer Wrightsoft names, not just the ones our prefix
regex table covers).

Per-zone emission rules (derived from the sister session's shape
notes and cross-checked against 79th Ct + Ally samples):

  - Cooling Condenser → ONE 'Condenser' line, ahri_spec attached
    (product_type, mfr, condenser+coil models, capacity, SEER/HSPF/AFUE).
  - Cooling Coil     → ONE 'Air Handler' line, no ahri_spec
    (the paired spec lives on the condenser line so the Equipment
    Specs card renders one row per system, not two).
  - Primary heating → NO separate line when:
      * Heating Type == Cooling Type (heat pump reuses the coil), OR
      * Heating Model is blank (elec strip inside the AHU).
    Emit a 'Furnace' line only when heating type is 'Gas Furnace'
    (or similar) with a non-blank Heating Model.
  - Backup heat kit → ONE 'Heat Kit' line whenever Backup Model
    is present. No ahri_spec (heat kits aren't in AHRI's tree).

Field names in the ValidateProject shape are variant-dependent
(AC vs heat pump vs furnace expose different fields; Heating Type
appears twice when backup heat is present). Parse by walking the
fields list in order and keying off Zone Name boundaries — do NOT
assume a fixed schema.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Manufacturer → 4-char Wrightsoft Src code. Mirrors bom_from_rup._MFR_NAME_TO_SRC.
# When a manufacturer isn't in this map, fall through to "WSF".
_MFR_TO_SRC: Dict[str, str] = {
    "TRANE":                "TRAN",
    "GOODMAN":              "GOOD",
    "CARRIER":              "CARR",
    "LENNOX":               "LENN",
    "BRYANT":               "BRYT",
    "RHEEM":                "RHEE",
    "AMERICAN STANDARD":    "AMST",
    "MITSUBISHI ELECTRIC":  "MITS",
    "MITSUBISHI":           "MITS",
    "LG":                   "LGE",
    "DAIKIN":               "DAIK",
    "BOSCH":                "BOSH",
    "YORK":                 "YORK",
    "PAYNE":                "PAYN",
}


def _mfr_src(mfr: str) -> str:
    key = (mfr or "").strip().upper()
    return _MFR_TO_SRC.get(key, "WSF")


def _fields_to_dict(fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Collapse a zone's fields list into a plain dict of {name: value}.

    Preserves duplicate keys by keeping the LAST occurrence — matters
    for `Heating Type`, which appears twice when a zone has backup
    heat (primary type first, "Elec strip" second). The BACKUP hit
    over-writes the primary in this dict — check `Backup Model`
    separately to detect backup presence rather than relying on
    the second `Heating Type` alone.
    """
    out: Dict[str, Any] = {}
    for f in fields or []:
        name = (f.get("name") or "").strip()
        val  = f.get("value")
        if not name:
            continue
        out[name] = val
    return out


def _to_float(v: Any) -> Optional[float]:
    """Parse Wrightsoft's stringy numeric fields. Values like '53000',
    '21', '105.8', '0'. Handles blanks and non-numerics gracefully."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _to_int(v: Any) -> Optional[int]:
    f = _to_float(v)
    return int(f) if f is not None else None


def _build_ahri_spec(cooling_type: str, mfr: str, condenser: str,
                     coil: str, capacity: Optional[float],
                     seer: Optional[float], hspf: Optional[float],
                     afue: Optional[float]) -> Dict[str, Any]:
    """Match the ahri_spec shape the SPA/PDF/XLS Equipment Specs
    renderers already consume:
        { product_type, manufacturer, condenser_model, coil_model,
          capacity_btu, seer, hspf, afue, ari_refno, trade_name }
    ari_refno stays None here — the AHRI catalog lookup is the only
    source for the certification number. A downstream enrichment
    step can merge it in later without disturbing these fields.
    """
    return {
        "product_type":    cooling_type or None,
        "manufacturer":    mfr or None,
        "condenser_model": condenser or None,
        "coil_model":      coil or None,
        "capacity_btu":    int(capacity) if capacity is not None else None,
        "seer":            seer,
        "hspf":            hspf,
        "afue":            afue,
        "ari_refno":       None,
        "trade_name":      None,
    }


def parse_validateproject_bundle(bundle: Dict[str, Any],
                                 project_name: Optional[str] = None
                                 ) -> List[Dict[str, Any]]:
    """Walk a ValidateProject-shaped bundle and emit BOM line items.

    Args:
        bundle: parsed JSON matching the sister session's shape
            (top-level dict keyed by project name; each project a
            list of {"zone", "fields"} dicts).
        project_name: which project to extract. If None and the
            bundle has exactly one project, that one is used.
            If None and multiple exist, raises ValueError so the
            caller can prompt the user.

    Returns:
        List of line-item dicts in the shape build_bom_from_wrightsoft_lines
        already consumes (generic_id / quantity / description / src /
        manufacturer / section_hint / unit / ahri_spec / com_zone
        / com_extracted).
    """
    if not isinstance(bundle, dict) or not bundle:
        return []

    # v1 schema dispatch — detect the bundle_schema_version marker.
    # v1 replaces the v0 top-level {project_name: [zones]} shape with a
    # documented envelope: {bundle_schema_version, producer_metadata,
    # project, line_items, zones}. Keep both branches — v0 bundles
    # from the sister session's early smokes still exist.
    if bundle.get("bundle_schema_version") == "v1":
        return _parse_v1(bundle, project_name)

    # Project resolution (v0 branch)
    projects = list(bundle.keys())
    if project_name is None:
        if len(projects) == 1:
            project_name = projects[0]
        else:
            raise ValueError(
                f"Bundle contains {len(projects)} projects: "
                f"{projects!r}. Pass project_name to select one."
            )
    if project_name not in bundle:
        raise ValueError(
            f"Project {project_name!r} not in bundle. "
            f"Available: {list(bundle.keys())!r}"
        )

    zones = bundle[project_name] or []
    lines: List[Dict[str, Any]] = []

    for zone in zones:
        zone_name = (zone.get("zone") or "").strip()
        raw_fields = zone.get("fields") or []
        fdict = _fields_to_dict(raw_fields)

        # ── Read the cooling side ────────────────────────────────
        cooling_type = (fdict.get("Cooling type") or "").strip()
        cooling_mfr  = (fdict.get("Cooling Manufacturer") or "").strip()
        cond_model   = (fdict.get("Cooling Condenser") or "").strip()
        coil_model   = (fdict.get("Cooling Coil") or "").strip()
        cooling_cap  = _to_float(fdict.get("Cooling Capacity"))
        seer         = _to_float(fdict.get("SEER"))
        hspf         = _to_float(fdict.get("HSPF"))
        afue_raw     = _to_float(fdict.get("AFUE"))
        # AFUE = 0 on an AC/heat-pump zone is a "not applicable" marker,
        # not a real efficiency. Suppress it so it doesn't misrender.
        afue = afue_raw if (afue_raw is not None and afue_raw > 0) else None

        ahri_spec = _build_ahri_spec(
            cooling_type, cooling_mfr, cond_model, coil_model,
            cooling_cap, seer, hspf, afue,
        )

        # ── Condenser line — spec attaches here ──────────────────
        if cond_model:
            lines.append({
                "generic_id":   cond_model,
                "quantity":     1,
                "description":  f"Condenser — {cooling_mfr} {cond_model} ({zone_name})".strip(),
                "src":          _mfr_src(cooling_mfr),
                "manufacturer": cooling_mfr,
                "section_hint": "Equipment",
                "unit":         "EA",
                "com_extracted": True,
                "com_zone":      zone_name,
                "ahri_spec":     ahri_spec,
            })

        # ── Coil / air-handler line — no spec (paired with CU) ───
        if coil_model:
            lines.append({
                "generic_id":   coil_model,
                "quantity":     1,
                "description":  f"Air Handler — {cooling_mfr} {coil_model} ({zone_name})".strip(),
                "src":          _mfr_src(cooling_mfr),
                "manufacturer": cooling_mfr,
                "section_hint": "Equipment",
                "unit":         "EA",
                "com_extracted": True,
                "com_zone":      zone_name,
            })

        # ── Primary heating — Furnace only ───────────────────────
        # For heat pumps the heating model equals the cooling coil
        # (same physical unit); for elec strip inside the AHU the
        # heating model is blank. Only a Gas Furnace (or similar
        # named furnace) needs its own line.
        heating_type = (fdict.get("Heating Type") or "").strip()
        heating_mfr  = (fdict.get("Heating Manufacturer") or "").strip()
        heating_model = (fdict.get("Heating Model") or "").strip()
        heating_output = _to_float(fdict.get("Heating Output"))
        heating_afue_raw = _to_float(fdict.get("AFUE"))

        looks_like_furnace = any(
            needle in heating_type.lower()
            for needle in ("furnace", "boiler")
        )
        if looks_like_furnace and heating_model:
            furnace_spec = {
                "product_type":    heating_type or None,
                "manufacturer":    heating_mfr or None,
                "condenser_model": None,
                "coil_model":      heating_model,
                "capacity_btu":    int(heating_output) if heating_output else None,
                "seer":            None,
                "hspf":            None,
                "afue":            heating_afue_raw if (heating_afue_raw and heating_afue_raw > 0) else None,
                "ari_refno":       None,
                "trade_name":      None,
            }
            lines.append({
                "generic_id":   heating_model,
                "quantity":     1,
                "description":  f"{heating_type} — {heating_mfr} {heating_model} ({zone_name})".strip(),
                "src":          _mfr_src(heating_mfr),
                "manufacturer": heating_mfr,
                "section_hint": "Equipment",
                "unit":         "EA",
                "com_extracted": True,
                "com_zone":      zone_name,
                "ahri_spec":     furnace_spec,
            })

        # ── Backup heat kit — emit whenever Backup Model present ─
        backup_model = (fdict.get("Backup Model") or "").strip()
        backup_mfr   = (fdict.get("Backup Manufacturer") or "").strip()
        backup_cap   = _to_float(fdict.get("Backup Capacity"))
        if backup_model:
            lines.append({
                "generic_id":   backup_model,
                "quantity":     1,
                "description":  f"Heat Kit — {backup_mfr} {backup_model} ({zone_name})".strip(),
                "src":          _mfr_src(backup_mfr),
                "manufacturer": backup_mfr,
                "section_hint": "Equipment",
                "unit":         "EA",
                "com_extracted": True,
                "com_zone":      zone_name,
                # Backup capacity carried in a lightweight ahri_spec
                # so the Equipment Specs card can render "26,273 BTU"
                # for the kit even though there's no AHRI cert data
                # for heat strips.
                "ahri_spec": {
                    "product_type":    "Elec strip",
                    "manufacturer":    backup_mfr or None,
                    "condenser_model": None,
                    "coil_model":      backup_model,
                    "capacity_btu":    int(backup_cap) if backup_cap else None,
                    "seer":            None,
                    "hspf":            None,
                    "afue":            None,
                    "ari_refno":       None,
                    "trade_name":      None,
                } if backup_cap else None,
            })

    logger.info(
        "wrightsoft_bundle_adapter: parsed project=%r zones=%d → %d line items",
        project_name, len(zones), len(lines),
    )
    return lines


def _parse_v1(bundle: Dict[str, Any],
              project_name: Optional[str]) -> List[Dict[str, Any]]:
    """v1 bundle parser — see wrightsoft-bundle-schema-v1.md.

    Unlike v0's positional field-list-per-zone, v1 zones carry
    typed sub-objects: cooling / heating / backup_heat / load_percent.
    Emit the same per-zone lines as the v0 branch (condenser + coil
    + optional furnace + optional backup heat kit)."""
    project_obj = bundle.get("project") or {}
    resolved = project_obj.get("name") or "unknown"
    if project_name and project_name != resolved:
        # Caller passed a project_name — accept it if it exactly matches;
        # otherwise treat as an error rather than silently ignore.
        raise ValueError(
            f"Project {project_name!r} not in bundle. "
            f"Available: [{resolved!r}]"
        )

    zones = bundle.get("zones") or []
    lines: List[Dict[str, Any]] = []

    for zone in zones:
        zone_name = (zone.get("zone_name") or "").strip()
        cooling = zone.get("cooling") or {}
        heating = zone.get("heating") or {}
        backup = zone.get("backup_heat") or {}

        cool_mfr   = (cooling.get("manufacturer") or "").strip()
        cond_model = (cooling.get("condenser_model") or "").strip()
        coil_model = (cooling.get("coil_model") or "").strip()
        cool_cap   = cooling.get("capacity_btu")
        seer       = cooling.get("seer")
        hspf       = cooling.get("hspf")
        afue       = cooling.get("afue")
        # Suppress AFUE == 0 marker (same rule as v0 branch)
        afue = afue if (afue is not None and afue > 0) else None

        ahri_spec = _build_ahri_spec(
            (cooling.get("type") or "").strip(),
            cool_mfr, cond_model, coil_model, cool_cap,
            seer, hspf, afue,
        )

        # Condenser line
        if cond_model:
            lines.append({
                "generic_id":   cond_model,
                "quantity":     1,
                "description":  f"Condenser — {cool_mfr} {cond_model} ({zone_name})".strip(),
                "src":          _mfr_src(cool_mfr),
                "manufacturer": cool_mfr,
                "section_hint": "Equipment",
                "unit":         "EA",
                "com_extracted": True,
                "com_zone":      zone_name,
                "ahri_spec":     ahri_spec,
            })

        # Coil / air handler line
        if coil_model:
            lines.append({
                "generic_id":   coil_model,
                "quantity":     1,
                "description":  f"Air Handler — {cool_mfr} {coil_model} ({zone_name})".strip(),
                "src":          _mfr_src(cool_mfr),
                "manufacturer": cool_mfr,
                "section_hint": "Equipment",
                "unit":         "EA",
                "com_extracted": True,
                "com_zone":      zone_name,
            })

        # Primary heating — only emit a Furnace/Boiler line when
        # heating.type names one. Heat pumps reuse the coil.
        htg_type = (heating.get("type") or "").strip().lower()
        htg_model = (heating.get("model") or "").strip()
        htg_mfr = (heating.get("manufacturer") or "").strip()
        htg_output = heating.get("output_btu")
        if htg_model and any(t in htg_type for t in ("furnace", "boiler")):
            furnace_spec = {
                "product_type":    heating.get("type"),
                "manufacturer":    htg_mfr or None,
                "condenser_model": None,
                "coil_model":      htg_model,
                "capacity_btu":    int(htg_output) if htg_output else None,
                "seer":            None,
                "hspf":            None,
                "afue":            None,
                "ari_refno":       None,
                "trade_name":      None,
            }
            lines.append({
                "generic_id":   htg_model,
                "quantity":     1,
                "description":  f"{heating.get('type')} — {htg_mfr} {htg_model} ({zone_name})".strip(),
                "src":          _mfr_src(htg_mfr),
                "manufacturer": htg_mfr,
                "section_hint": "Equipment",
                "unit":         "EA",
                "com_extracted": True,
                "com_zone":      zone_name,
                "ahri_spec":     furnace_spec,
            })

        # Backup heat kit
        backup_model = (backup.get("model") or "").strip()
        backup_mfr = (backup.get("manufacturer") or "").strip()
        backup_cap = backup.get("capacity_btu")
        if backup_model:
            lines.append({
                "generic_id":   backup_model,
                "quantity":     1,
                "description":  f"Heat Kit — {backup_mfr} {backup_model} ({zone_name})".strip(),
                "src":          _mfr_src(backup_mfr),
                "manufacturer": backup_mfr,
                "section_hint": "Equipment",
                "unit":         "EA",
                "com_extracted": True,
                "com_zone":      zone_name,
                "ahri_spec": {
                    "product_type":    "Elec strip",
                    "manufacturer":    backup_mfr or None,
                    "condenser_model": None,
                    "coil_model":      backup_model,
                    "capacity_btu":    int(backup_cap) if backup_cap else None,
                    "seer":            None,
                    "hspf":            None,
                    "afue":            None,
                    "ari_refno":       None,
                    "trade_name":      None,
                } if backup_cap else None,
            })

    logger.info("wrightsoft_bundle_adapter[v1]: project=%r zones=%d → %d lines",
                resolved, len(zones), len(lines))
    return lines
