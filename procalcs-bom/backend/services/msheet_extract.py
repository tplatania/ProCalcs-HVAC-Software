"""msheet_extract.py — mechanical-schedule ("M-sheet") PDF extraction.

Extracts the equipment schedule + accessory callouts from a Wrightsoft /
ProCalcs mechanical-schedule PDF so a BOM can be reconciled against what
the schedule actually specifies (refrigerant pipe dims, condensate,
straps, air-device sizes). See docs/m-sheet-analysis-spec.md.

Origin: Richard (NE 132nd, 2026-09-24) — filters, refrigerant/condensate
pipes, thermostats, dampers, straps are "missing for a standard BOM";
Dana confirmed those live on the M-sheet. Proven on Rahim II: every one
of the four .rup equipment models appears in the schedule, and the
refrigerant pipe dims / type are right there.

Confidence tiers (a VECTOR pdf with a text layer):
  HIGH — equipment schedule (condenser/AHU model, tonnage, refrigerant
         pipe dims + type, max pipe length, electrical) and detail-page
         accessory presence (condensate trap, hurricane strap, isomode
         pad, expansion anchor).
  BEST-EFFORT — air-device neck sizes (diffuser callouts) via word-
         coordinate pairing; cfm and neck size sit in loosely-placed
         text blocks, so treat counts as approximate.
  NOT RELIABLE — thermostat tags are graphical on the plan, usually NOT
         in the text layer; returned as a "review the drawing" note,
         never a hard count.

Text via pdfplumber (pure-python / pdfminer.six — no system libs, so no
Dockerfile change). A scanned/flattened M-sheet has no text layer;
`has_text_layer()` reports that so callers can fall back to OCR/manual.

This module only EXTRACTS. Reconciliation against the BOM + any BOM
change is a separate, reviewer-gated step (see the reconciliation task).
"""
from __future__ import annotations

import io
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Known equipment-model shapes we reconcile against the .rup BOM.
_CONDENSER_RE = re.compile(r"\b(26SP[A-Z0-9]+|SUZ-[A-Z0-9]+|SVZ-[A-Z0-9]+|"
                           r"5[A-Z]{3}[A-Z0-9]{4,})\b")
_CARRIER_COND_RE = re.compile(r"\b(26SP[A-Z0-9]{6,})\b")
_CARRIER_AHU_RE = re.compile(r"\b(FJ5[A-Z0-9]{5,})\b")
_MIT_COND_RE = re.compile(r"\b(SUZ-[A-Z0-9]{5,})\b")
_MIT_AHU_RE = re.compile(r"\b(SVZ-[A-Z0-9]{5,})\b")
_REFRIG_TYPE_RE = re.compile(r"\b(R-?454B|R-?410A|R-?32|R-?22)\b")
_REFRIG_DIM_RE = re.compile(
    r"Refrig Pipe Dim[^\n]*?(\d+/\d+)\s*/\s*(\d+/\d+)")
_MAXPIPE_RE = re.compile(r"Max Pipe Length[^\n]*?([\d]+(?:\.\d+)?)\s*(?:\n|$)")
_TONNAGE_RE = re.compile(r"([\d.]+)\s*ton\(s\)")
_LABELLED_RE = {
    "mca_mop": re.compile(r"MCA/MOP\s+([0-9./]+)"),
    "static_pressure_in_wc": re.compile(r"STATIC PRESSURE, IN\. OF W\.C\.\s+([\d.]+)"),
    "weight_lbs": re.compile(r"WEIGHT, LBS\.\s+([\d]+)"),
}


def _open(pdf_bytes: bytes):
    import pdfplumber
    return pdfplumber.open(io.BytesIO(pdf_bytes))


def _layout_text(pdf) -> str:
    parts = []
    for p in pdf.pages:
        try:
            parts.append(p.extract_text(layout=True) or "")
        except Exception:  # noqa: BLE001
            parts.append(p.extract_text() or "")
    return "\n".join(parts)


def has_text_layer(pdf_bytes: bytes) -> bool:
    """False for a scanned/flattened M-sheet (→ needs OCR/manual)."""
    try:
        with _open(pdf_bytes) as pdf:
            return len((_layout_text(pdf)).strip()) > 200
    except Exception:  # noqa: BLE001
        return False


def extract_equipment_schedule(text: str) -> List[Dict[str, Any]]:
    """One record per system (condenser↔AHU), with the specs the .rup
    lacks. HIGH confidence."""
    systems: List[Dict[str, Any]] = []

    carr_c = _CARRIER_COND_RE.search(text)
    carr_a = _CARRIER_AHU_RE.search(text)
    if carr_c or carr_a:
        systems.append({
            "system_tag": "CU-1 / AHU-1",
            "condenser_model": carr_c.group(1) if carr_c else None,
            "ahu_model": carr_a.group(1) if carr_a else None,
            "tonnage": _first(_TONNAGE_RE, text),
            "refrigerant_type": _first(_REFRIG_TYPE_RE, text),
            **{k: _first(rx, text) for k, rx in _LABELLED_RE.items()},
        })

    mit_c = _MIT_COND_RE.search(text)
    mit_a = _MIT_AHU_RE.search(text)
    if mit_c or mit_a:
        dim = _REFRIG_DIM_RE.search(text)
        systems.append({
            "system_tag": "CU-2 / AHU-2",
            "condenser_model": mit_c.group(1) if mit_c else None,
            "ahu_model": mit_a.group(1) if mit_a else None,
            "refrig_pipe_dim_in": (f"{dim.group(1)} / {dim.group(2)}" if dim else None),
            "max_pipe_length_ft": _first(_MAXPIPE_RE, text),
        })
    return systems


def extract_detail_accessories(text: str) -> Dict[str, bool]:
    """Presence of installation-detail callouts (Richard's list).
    HIGH confidence (keyword presence on the details page)."""
    # Both-words-present is more robust than adjacency — the layout text
    # can split "HURRICANE\nSTRAP" across columns/lines.
    return {
        "condensate_trap": bool(re.search(r"TRAP|DRAIN PAN|condensate", text, re.I)),
        "hurricane_strap": bool(re.search(r"HURRICANE", text, re.I)
                                and re.search(r"STRAP", text, re.I)),
        "isomode_pad": bool(re.search(r"ISOMODE", text, re.I)),
        "expansion_anchor": bool(re.search(r"EXPANSION\s*ANCHOR", text, re.I)),
    }


def extract_air_devices(pdf) -> List[Dict[str, Any]]:
    """Diffuser/register neck sizes by pairing each '<n> cfm' with the
    nearest '<d> "' token by word coordinates. BEST-EFFORT — the plan
    text is loosely placed, so treat as approximate."""
    devices: List[Dict[str, Any]] = []
    for page in pdf.pages:
        try:
            words = page.extract_words(use_text_flow=False)
        except Exception:  # noqa: BLE001
            continue
        cfm_pts, dia_pts = [], []
        for i, w in enumerate(words):
            t = w["text"]
            if t.lower() == "cfm" and i > 0 and re.fullmatch(r"\d+", words[i - 1]["text"]):
                cfm_pts.append((int(words[i - 1]["text"]),
                                (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2))
            m = re.fullmatch(r"(\d+)", t)
            # a diameter token is a small integer immediately followed by ".
            if m and i + 1 < len(words) and words[i + 1]["text"] in ('"', '”'):
                d = int(m.group(1))
                if 3 <= d <= 24:
                    dia_pts.append((d, (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2))
        for cfm, cx, cy in cfm_pts:
            if not dia_pts:
                break
            d, _, _ = min(dia_pts, key=lambda p: (p[1] - cx) ** 2 + (p[2] - cy) ** 2)
            devices.append({"cfm": cfm, "neck_in": d})
    return devices


def extract_msheet(pdf_bytes: bytes) -> Dict[str, Any]:
    """Top-level: everything the M-sheet can supply, tiered by confidence."""
    if not has_text_layer(pdf_bytes):
        return {"has_text_layer": False,
                "note": "No text layer (scanned M-sheet) — needs OCR/manual."}
    with _open(pdf_bytes) as pdf:
        text = _layout_text(pdf)
        equipment = extract_equipment_schedule(text)
        accessories = extract_detail_accessories(text)
        air_devices = extract_air_devices(pdf)
    return {
        "has_text_layer": True,
        "equipment": equipment,
        "detail_accessories": accessories,
        "air_devices": air_devices,          # best-effort
        "thermostats": {                     # not reliable in text
            "count": None,
            "note": "Thermostat tags are graphical on the plan and usually "
                    "not in the text layer — review the drawing.",
        },
    }


def _first(rx: re.Pattern, text: str) -> Optional[str]:
    m = rx.search(text)
    return m.group(1).strip() if m else None
