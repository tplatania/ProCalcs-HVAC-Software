"""
rup_parser.py — Canonical Wrightsoft Right-Suite Universal (.rup) parser
for the ProCalcs BOM pipeline.

Consolidates the two earlier prototypes:
  - experiments/rup_extractor.py   (UTF-16 byte-level extraction, BEG/END
                                    backreference, narrative text output)
  - phase1_validator/reference_code/rup_parser.py
                                   (structured dict shape, address / weather
                                    / model / tonnage / SEER regexes)

Extended per spec:
  docs/GERALD_HANDOFF_RUP_UPLOAD.md

Output shape matches the BOM engine's `design_data` contract
(see procalcs-bom/backend/utils/validators.py and
procalcs-bom/backend/services/bom_service.py):

    {
      "project": {
        "name": str, "address": str, "city": str, "state": str,
        "zip": str, "county": str,
        "contractor": {"name", "company", "phone", "email", "license"},
        "drafter":    {"name", "company"},
        "date": str,
      },
      "location": {"weather_station": str, "state": str},
      "building": {
        "type":          "single_level" | "two_story" | "multi_level" | "other",
        "duct_location": "attic" | "crawlspace" | "conditioned" | "basement" | "other",
      },
      "equipment":  [{"name", "type", "cfm", "tonnage", "model"}],
      "duct_runs":  [],   # populated via AI fallback in hybrid mode
      "fittings":   [],   # populated via AI fallback in hybrid mode
      "registers":  [],   # populated via AI fallback in hybrid mode
      "rooms":      [{"name", "ahu", "cfm"}],
      "metadata":   {"source_file", "app", "version", "timestamp"},
      "raw_rup_context": str,   # narrative text fallback for the AI prompt
    }

The `raw_rup_context` field holds a best-effort narrative rendering of the
file's contents. When the structured arrays (`duct_runs`, `fittings`,
`registers`) are empty — which is the current state because those fields
live in deeply-nested Wrightsoft binary we haven't reverse-engineered yet —
the BOM engine AI prompt can read `raw_rup_context` to estimate quantities
(Hybrid Option per the spec). This is the same architectural rule as
bom_service.py:7 — "AI reads text and reasons, Python does math".

Usage:
    from utils.rup_parser import parse_rup_bytes, parse_rup_file

    with open("project.rup", "rb") as f:
        design_data = parse_rup_bytes(f.read(), source_name="project.rup")

    # or
    design_data = parse_rup_file("project.rup")
"""

from __future__ import annotations

import re
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Section classification ──────────────────────────────────────────────────

_NON_ROOM_TOKENS = {
    "ECDUCTSYS", "TDUCTSYS", "DUCTRUN", "DUCTLOC", "SJD",
    "SURFACE", "WALLSURF", "CEILSURF", "GLAZSURF", "DOORSURF",
    "DLINFO", "REDI", "REDIST", "RGAREA", "RPTINFO", "COMPONTY",
    "CCONSTRUCTION", "CCONSMAT", "CCONSLAYER", "CFSPROP",
    "RHPANEL", "WALLINFO", "WALLTYINFO", "RB", "TDINFO", "ZIGI",
    "PARTLINKINFO", "DETAILMETHOD", "INFVENT", "VNTREQ", "VENTEQ",
    "FLCLTY", "CEILTY", "WALLTY", "GLAZTY", "JOBINFO", "JOBINFOK",
    "BEG", "END", "APP", "VRSN", "SN", "TIMESTAMP",
}

_VALID_BUILDING_TYPES = {
    "single level":  "single_level",
    "single-level":  "single_level",
    "one story":     "single_level",
    "one-story":     "single_level",
    "two story":     "two_story",
    "two-story":     "two_story",
    "multi level":   "multi_level",
    "multi-level":   "multi_level",
    "multi story":   "multi_level",
    "multi-story":   "multi_level",
}

_VALID_DUCT_LOCATIONS = {
    "attic":        "attic",
    "crawl":        "crawlspace",
    "crawlspace":   "crawlspace",
    "conditioned":  "conditioned",
    "basement":     "basement",
}


# ── Low-level primitives ────────────────────────────────────────────────────

def extract_utf16_strings(data: bytes, min_len: int = 4) -> List[str]:
    """Pull all UTF-16 LE printable-ASCII runs from binary data.

    Ported from experiments/rup_extractor.py. This tolerates the binary
    chunks interspersed between ASCII text that Wrightsoft's format has —
    straight utf-16-le decode produces garbled runs that str.split on.
    """
    strings: List[str] = []
    current: List[str] = []
    i = 0
    end = len(data) - 1
    while i < end:
        val = int.from_bytes(data[i:i + 2], "little")
        if 32 <= val <= 126 or val in (9, 10, 13):
            current.append(chr(val))
        else:
            if len(current) >= min_len:
                strings.append("".join(current))
            current = []
        i += 2
    if len(current) >= min_len:
        strings.append("".join(current))
    return strings


_IDENT = re.compile(r"[A-Za-z0-9_]+")


def parse_sections(text: str) -> Dict[str, List[str]]:
    """Parse !BEG=SECTION ... !END=SECTION blocks.

    Wrightsoft is *almost* well-formed: !BEG=NAME pairs with !END=NAME in
    most cases, but there are known drift quirks — e.g. !BEG=JOBINFOK is
    closed by !END=JOBINFO (the K suffix is only on the opener). So we
    can't use a simple backreference.

    Strategy: walk the text, find each !BEG=NAME, then scan forward for
    an !END= whose name either equals NAME or is a prefix of NAME (handles
    the K-suffix drift). Stop at the next !BEG= if we hit it first, to
    prevent body bleed into adjacent sections.
    """
    sections: Dict[str, List[str]] = defaultdict(list)
    n = len(text)
    i = 0
    while i < n:
        beg = text.find("!BEG=", i)
        if beg < 0:
            break
        name_start = beg + 5
        m = _IDENT.match(text, name_start)
        if not m:
            i = name_start
            continue
        name = m.group(0)
        body_start = m.end()

        # Scan forward for the matching !END=.
        search = body_start
        body_end = -1
        while True:
            end_pos = text.find("!END=", search)
            if end_pos < 0:
                break
            end_name_start = end_pos + 5
            em = _IDENT.match(text, end_name_start)
            end_name = em.group(0) if em else ""

            # If we see a new !BEG= before any acceptable !END=, stop —
            # the section is malformed/truncated and we'd otherwise bleed.
            next_beg = text.find("!BEG=", search + 5)
            if 0 <= next_beg < end_pos:
                break

            if end_name == name or (end_name and name.startswith(end_name)):
                body_end = end_pos
                break
            search = end_name_start + len(end_name)

        if body_end < 0:
            i = body_start
            continue

        body = text[body_start:body_end].strip()
        if body:
            sections[name].append(body)
        i = body_end + 5

    return dict(sections)


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _parse_header(data: bytes) -> Dict[str, str]:
    """Read the short UTF-16 header block at the start of every .rup file."""
    try:
        header_text = data[:0xe0].decode("utf-16-le", errors="replace")
    except Exception:
        return {}
    fields = dict(re.findall(r"(\w+)=([^\r\n]+)", header_text))
    return {
        "app":       fields.get("APP", "").strip(),
        "version":   fields.get("VRSN", "").strip(),
        "serial":    fields.get("SN", "").strip(),
        "timestamp": fields.get("TIMESTAMP", "").strip(),
    }


# ── Structured field extractors ─────────────────────────────────────────────

def _parse_project(sections: Dict[str, List[str]]) -> Dict[str, Any]:
    """JOBINFO / JOBINFOK is a free-form multi-line block with contractor +
    drafter contact info, address, date. Field order is stable enough in
    Wrightsoft v25.x that a positional parse works.
    """
    raw = ""
    for key in ("JOBINFOK", "JOBINFO"):
        if key in sections and sections[key]:
            raw = sections[key][0]
            break
    if not raw:
        return {}

    # Strip Windows file paths (noisy and unwanted)
    raw = re.sub(r"[A-Z]:\\[^\n]+", "", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    project: Dict[str, Any] = {
        "name":       lines[0] if lines else "",
        "address":    "",
        "city":       "",
        "state":      "",
        "zip":        "",
        "county":     "",
        "contractor": {},
        "drafter":    {},
        "date":       "",
    }

    # Address block typically lines 1..3 (street, city, zip).
    if len(lines) >= 4:
        project["address"] = lines[1]
        project["city"]    = lines[2]
        project["zip"]     = lines[3]

    # County tends to appear alone on a short line later in the block,
    # after the contractor/drafter blocks. Skip lines we already used for
    # address/city and skip known building-category labels.
    _skip = {
        project["city"], project["address"], project["zip"],
        "Detached", "Attached", "Multi Family", "Townhouse",
    }
    for line in lines[12:25]:
        if (re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+)?", line)
                and len(line) < 30
                and line not in _skip):
            project["county"] = line
            break

    # Contractor block — after project address, typically name / company /
    # street / city+state / zip / phone / email / website / license.
    contractor = {}
    if len(lines) >= 13:
        contractor["name"]    = lines[4]
        contractor["company"] = lines[5]
        # lines 6, 7, 8 are street/city/zip — collapse into an address line
        contractor["address"] = ", ".join(lines[6:9]).strip(", ")
        for ln in lines[9:16]:
            if re.match(r"^\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}$", ln):
                contractor["phone"] = ln
            elif "@" in ln and "." in ln:
                contractor["email"] = ln.strip().rstrip(",")
            elif re.match(r"^[A-Z]{2,4}\d{4,}", ln):
                contractor["license"] = ln
    project["contractor"] = {k: v for k, v in contractor.items() if v}

    # Date — a line of the form "Jan 1, 2025" or "Nov 14, 2025"
    for line in lines:
        m = re.match(r"^([A-Z][a-z]{2,8})\s+\d{1,2},\s+\d{4}$", line)
        if m:
            project["date"] = line
            break

    # Drafter block comes after date typically.
    if project["date"]:
        try:
            date_idx = lines.index(project["date"])
            if date_idx + 2 < len(lines):
                project["drafter"] = {
                    "name":    lines[date_idx + 1],
                    "company": lines[date_idx + 2],
                }
        except ValueError:
            pass

    return project


def _parse_building(sections: Dict[str, List[str]], full_text: str) -> Dict[str, str]:
    """BldgType + PREFS give us the enum values the validator accepts."""
    bldg_type = "other"
    duct_loc = "other"

    # BldgType is a single-entry section whose body is the human label.
    bldg_raw = ""
    if "BldgType" in sections and sections["BldgType"]:
        bldg_raw = sections["BldgType"][0].lower()
    for needle, enum_val in _VALID_BUILDING_TYPES.items():
        if needle in bldg_raw:
            bldg_type = enum_val
            break

    # PREFS mentions duct location in a label like "Ducts in Attic, Vented,..."
    prefs_raw = ""
    if "PREFS" in sections and sections["PREFS"]:
        prefs_raw = sections["PREFS"][0].lower()
    # Search either PREFS or the full text for a duct location hint
    search_target = prefs_raw or full_text.lower()
    for needle, enum_val in _VALID_DUCT_LOCATIONS.items():
        if f"ducts in {needle}" in search_target or f"duct in {needle}" in search_target:
            duct_loc = enum_val
            break

    return {"type": bldg_type, "duct_location": duct_loc}


def _extract_serial(full_text: str) -> str:
    """Grab the Wrightsoft SN field so we can exclude it from model-number
    regex hits (otherwise it shows up as a bogus equipment model)."""
    m = re.search(r"SN=([A-Z]{2,4}\d{4,})", full_text[:1000])
    return m.group(1) if m else ""


def _parse_equipment(full_text: str) -> List[Dict[str, Any]]:
    """Enumerate AHUs from the `AHU - N|AHU - N` pipe-delimited line.
    Returns one entry per AHU with best-effort CFM/tonnage/model.
    """
    equipment: List[Dict[str, Any]] = []

    ahu_match = re.search(r"(AHU - \d+(?:\|AHU - \d+)+)", full_text)
    if not ahu_match:
        return equipment

    ahus = sorted(set(ahu_match.group(1).split("|")))

    # Aggregate signals — CFMs, tonnage, SEER, model numbers — we can't
    # cleanly associate them per-AHU without deeper binary parsing, so we
    # expose them on the first entry as hints and leave the rest blank.
    cfms = re.findall(r"(\d{2,5})\s*(?:cfm|CFM)", full_text)
    cfm_values = _dedupe([int(c) for c in cfms if c.isdigit()])

    tonnage_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:ton|TON)\b", full_text)
    tonnage = float(tonnage_match.group(1)) if tonnage_match else None

    seer_match = re.search(r"SEER\s*[:=]?\s*(\d+(?:\.\d+)?)", full_text, re.IGNORECASE)
    seer = float(seer_match.group(1)) if seer_match else None

    # Model-number regex hits are unreliable on the raw binary — they tend
    # to pick up serial numbers and HVAC contractor license codes. Leave
    # model extraction to the AI pass via raw_rup_context for now.
    model_numbers: List[str] = []

    for idx, name in enumerate(ahus):
        entry: Dict[str, Any] = {
            "name":    name.strip(),
            "type":    "air_handler",
            "cfm":     None,
            "tonnage": None,
            "model":   None,
        }
        if idx == 0:
            # Attach system-level signals to the first AHU so the AI prompt
            # has them to work with. Not strictly per-unit but better than
            # dropping the data.
            if cfm_values:
                entry["cfm"] = cfm_values[0]
            entry["tonnage"] = tonnage
            if model_numbers:
                entry["model"] = model_numbers[0]
        equipment.append(entry)

    return equipment


def _parse_rooms(full_text: str) -> List[Dict[str, Any]]:
    """Room → AHU assignment list, cleaned of section marker false positives."""
    rooms: List[Dict[str, Any]] = []
    seen: set = set()

    room_ahu = re.findall(r"([A-Z][A-Z0-9 \-]+?)\n(AHU - \d+)", full_text)
    for name_raw, ahu in room_ahu:
        name = name_raw.strip()
        if not name or name in _NON_ROOM_TOKENS or name.startswith("AHU"):
            continue
        key = (name, ahu.strip())
        if key in seen:
            continue
        seen.add(key)
        rooms.append({"name": name, "ahu": ahu.strip(), "cfm": None})

    return rooms


def _parse_location(sections: Dict[str, List[str]]) -> Dict[str, str]:
    """Weather station + state from WTHRDATA section."""
    if "WTHRDATA" not in sections or not sections["WTHRDATA"]:
        return {}
    wth = sections["WTHRDATA"][0]

    out: Dict[str, str] = {}
    station_match = re.search(
        r"([A-Za-z][A-Za-z\s]+(?:Executive|International|Regional|Municipal|Airport)[^|\n]{0,40})",
        wth,
    )
    if station_match:
        out["weather_station"] = station_match.group(1).strip()

    state_match = re.search(r"\|([A-Z]{2})\|", wth)
    if state_match:
        out["state"] = state_match.group(1)

    return out


# ── Narrative fallback text ─────────────────────────────────────────────────

def _build_raw_context(
    project: Dict[str, Any],
    building: Dict[str, str],
    equipment: List[Dict[str, Any]],
    rooms: List[Dict[str, Any]],
    full_text: str,
) -> str:
    """Assemble the narrative text the BOM engine AI prompt reads when the
    structured duct_runs / fittings / registers arrays are sparse.

    This is the `raw_rup_context` field and is the hybrid fallback mechanism
    from the spec — keep it rich enough that an HVAC-literate LLM can
    estimate quantities from it.
    """
    lines: List[str] = []
    lines.append("=== RUP PROJECT EXCERPT ===")
    if project.get("name"):
        lines.append(f"Project: {project['name']}")
    addr_bits = [project.get(k, "") for k in ("address", "city", "state", "zip")]
    addr_joined = ", ".join(b for b in addr_bits if b)
    if addr_joined:
        lines.append(f"Address: {addr_joined}")
    if building.get("type") or building.get("duct_location"):
        lines.append(
            f"Building: {building.get('type', 'unknown')} / "
            f"Ducts in {building.get('duct_location', 'unknown')}"
        )
    lines.append("")

    if equipment:
        lines.append(f"=== EQUIPMENT ({len(equipment)} units) ===")
        for eq in equipment:
            parts = [eq["name"]]
            if eq.get("cfm"):
                parts.append(f"{eq['cfm']} CFM")
            if eq.get("tonnage"):
                parts.append(f"{eq['tonnage']} ton")
            if eq.get("model"):
                parts.append(f"model {eq['model']}")
            lines.append("  " + " — ".join(parts))
        lines.append("")

    if rooms:
        lines.append(f"=== ROOMS ({len(rooms)} total) ===")
        for room in rooms:
            lines.append(f"  {room['name']} → {room['ahu']}")
        lines.append("")

    # Duct sizes + CFM values — raw, unassigned, for AI inference
    cfm_hits = _dedupe(re.findall(r"\d{2,5}\s*(?:cfm|CFM)", full_text))
    if cfm_hits:
        lines.append("CFM values present in file: " + ", ".join(cfm_hits[:25]))

    round_sizes = _dedupe(re.findall(r"\b\d{1,2}\s*\"", full_text))
    rect_sizes = _dedupe(re.findall(r"\b\d{1,3}\s*[xX]\s*\d{1,3}\b", full_text))
    if round_sizes or rect_sizes:
        sizes = round_sizes[:15] + rect_sizes[:15]
        lines.append("Duct dimensions observed: " + ", ".join(sizes))

    lines.append("")
    lines.append("(End of RUP excerpt — use the above to estimate duct linear "
                 "footage, fitting counts, and register quantities for BOM.)")
    return "\n".join(lines)


# ── Structural block parser (binary path) ──────────────────────────────────
#
# Wrightsoft .rup files are densely-packed binary records bracketed by
# UTF-16-LE markers `!BEG=<TAG>` ... `!END=<TAG>`. The regex-on-text path
# above misses 90%+ of structural data because it only sees free-floating
# strings — counts and per-instance attributes live in fixed-width binary
# fields between the markers.
#
# This block carries the tags we know how to decode. See
# /Users/geraldvillaran/Projects/designer-desktop/_repo-docs/RUP_BINARY_LAYOUT.md
# for the empirical layout notes that drive the field offsets here.

def _block_bodies(file_bytes: bytes, tag: str) -> List[bytes]:
    """Yield the body bytes (between BEG and END markers) for every block
    of the given tag. Order follows file position."""
    beg = ("!BEG=" + tag).encode("utf-16-le")
    end = ("!END=" + tag).encode("utf-16-le")
    out: List[bytes] = []
    pos = 0
    while True:
        b = file_bytes.find(beg, pos)
        if b < 0:
            break
        e = file_bytes.find(end, b + len(beg))
        if e < 0:
            break
        out.append(file_bytes[b + len(beg):e])
        pos = e + len(end)
    return out


# Map Wrightsoft equipment names (UTF-16 strings inside EQUIP blocks) to
# the canonical types compute_scope() reads in materials_rules.py. The
# mapping is intentionally permissive — substring match against a normalized
# (lowercase, whitespace-collapsed) form. New equipment types Wrightsoft
# emits should be added here as they're discovered.
_EQUIPMENT_NAME_MAP: List[Tuple[str, str]] = [
    # (substring trigger,            canonical type)
    ("air handler",                   "air_handler"),
    ("ahu",                           "air_handler"),
    ("split ac",                      "condenser"),
    ("condenser",                     "condenser"),
    ("heat pump",                     "heat_pump"),
    ("furnace",                       "furnace"),
    ("heat kit",                      "heat_kit"),
    ("electric heat",                 "heat_kit"),
    ("erv",                           "erv"),
    ("hrv",                           "erv"),
    ("energy recovery",               "erv"),
]


def _classify_equipment_name(raw: str) -> str:
    """Normalize a Wrightsoft equipment name into a canonical type. Falls
    back to 'other' so the structured parser doesn't lose records — the
    rules engine ignores 'other' but downstream UIs can still display the
    raw name."""
    norm = " ".join(raw.lower().split())
    for needle, canonical in _EQUIPMENT_NAME_MAP:
        if needle in norm:
            return canonical
    return "other"


def _parse_equip_blocks(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Decode every !BEG=EQUIP block into a structured record.

    Block layout (empirical, see RUP_BINARY_LAYOUT.md):
        +0x00  uint32  schema_version (typically 0x0b = 11)
        +0x04  uint32  record_id
        +0x08  uint32  flags (bitfield — exact semantics TBD)
        +0x0c  uint32  reserved
        +0x10  uint32  name_length_bytes (UTF-16, so chars * 2)
        +0x14  bytes   name (UTF-16-LE, name_length_bytes long)
        +...   binary  fixed-position float32/uint32 fields (CFM, tonnage —
                       not decoded yet)

    Returns one dict per record with at minimum {raw_name, type, record_id}.
    The text-regex _parse_equipment fallback runs only if this returns empty.
    """
    bodies = _block_bodies(file_bytes, "EQUIP")
    out: List[Dict[str, Any]] = []
    for idx, body in enumerate(bodies):
        if len(body) < 0x14:
            continue
        try:
            schema_version, record_id, flags, _reserved, name_len = struct.unpack_from(
                "<IIIII", body, 0
            )
        except struct.error:
            continue
        # Name length is in bytes (UTF-16, so 2 per char). Cap at body size
        # to defend against bad lengths in malformed records.
        name_end = 0x14 + min(name_len, len(body) - 0x14)
        try:
            raw_name = body[0x14:name_end].decode("utf-16-le", errors="replace")
        except Exception:
            raw_name = ""
        # Strip trailing nulls and whitespace.
        raw_name = raw_name.rstrip("\x00").strip()
        if not raw_name:
            continue
        out.append({
            "name":       raw_name,
            "type":       _classify_equipment_name(raw_name),
            "raw_name":   raw_name,
            "record_id":  record_id,
            "flags":      flags,
            "schema":     schema_version,
            # CFM/tonnage/model decoded by future passes against more RUPs.
            "cfm":        None,
            "tonnage":    None,
            "model":      None,
        })
    return out


# ── Public API ──────────────────────────────────────────────────────────────

def parse_rup_bytes(file_bytes: bytes, source_name: str = "") -> Dict[str, Any]:
    """Parse the raw bytes of a Wrightsoft .rup file into BOM design_data.

    Returns a dict matching the BOM engine contract (see module docstring).
    Unknown fields are set to empty lists / empty dicts / None — never
    missing — so downstream consumers can rely on key presence.
    """
    header = _parse_header(file_bytes)

    strings = extract_utf16_strings(file_bytes)
    full_text = "\n".join(strings)
    sections = parse_sections(full_text)

    project   = _parse_project(sections)
    location  = _parse_location(sections)
    building  = _parse_building(sections, full_text)

    # Equipment: text-regex path stays primary for now. The structural
    # _parse_equip_blocks helper exists and is exercised by tests, but
    # empirical inspection (see _repo-docs/RUP_BINARY_LAYOUT.md) showed
    # that EQUIP blocks carry the equipment LIBRARY (every type Wrightsoft
    # offers — 132 entries on Edge) rather than placed project instances.
    # The placed instances live in ZEQUIP (50 records on Edge for an
    # 8-AHU residence — ~6 zone-equipment items per AHU). ZEQUIP parser
    # is a follow-up; until it lands, the regex path's AHU-pipe pattern
    # remains the most reliable signal for compute_scope.
    equipment = _parse_equipment(full_text)

    rooms     = _parse_rooms(full_text)

    raw_context = _build_raw_context(project, building, equipment, rooms, full_text)

    return {
        "project":   project,
        "location":  location,
        "building":  building,
        "equipment": equipment,
        "duct_runs": [],   # hybrid — filled by AI from raw_rup_context
        "fittings":  [],   # hybrid — filled by AI from raw_rup_context
        "registers": [],   # hybrid — filled by AI from raw_rup_context
        "rooms":     rooms,
        "metadata": {
            "source_file": source_name,
            "app":         header.get("app", ""),
            "version":     header.get("version", ""),
            "timestamp":   header.get("timestamp", ""),
            "section_count": len(sections),
        },
        "raw_rup_context": raw_context,
    }


def parse_rup_file(path: str) -> Dict[str, Any]:
    """Read a .rup file from disk and return parsed design_data."""
    p = Path(path)
    return parse_rup_bytes(p.read_bytes(), source_name=p.name)


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="Parse a Wrightsoft .rup file")
    parser.add_argument("file", help="Path to a .rup file")
    parser.add_argument("--raw-context", action="store_true",
                        help="Print only the narrative raw_rup_context")
    args = parser.parse_args()

    data = parse_rup_file(args.file)
    if args.raw_context:
        print(data["raw_rup_context"])
    else:
        print(json.dumps(data, indent=2, default=str))
