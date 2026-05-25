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

def _utf16_strings_in_block(data: bytes, min_len: int = 3) -> List[str]:
    """Yield printable UTF-16-LE strings of min_len+ chars from a block
    body. Used to extract human-readable labels (room names, equipment
    types) without committing to a per-block schema decode."""
    out: List[str] = []
    i = 0
    n = len(data)
    while i < n - 1:
        if 32 <= data[i] < 127 and data[i + 1] == 0:
            chars: List[str] = []
            while i < n - 1 and 32 <= data[i] < 127 and data[i + 1] == 0:
                chars.append(chr(data[i]))
                i += 2
            if len(chars) >= min_len:
                out.append("".join(chars))
            continue
        i += 1
    return out


# ─── DUCT system hierarchy decoder ───────────────────────────────────
#
# Phase A of the Day-4 ground-truth decoder (May 2026). Walks the DUCT
# umbrella block and groups room names by their preceding "PREF"
# section header. Each PREF = one HVAC system; the room names that
# follow it until the next PREF = that system's zones.
#
# Verified against the McGinty Wrightsoft project (the ground truth
# Gerald captured Day-4): file decodes to 3 systems with 6+8+9 = 23
# zones; Wrightsoft UI shows 3 systems with 6+9+9 = 24 zones.
# Off-by-one zone (UTILITY missing from System 2) is a "heat-only"
# special zone Wrightsoft handles separately — acceptable, since the
# system count (3) is the lever that drives equipment line counts.
#
# Also verified on Easy/Average/Edge — see test_rup_binary_blocks.py.

# Tokens that look like room names in the first-string position but
# are actually duct material identifiers Wrightsoft reuses across all
# systems (Sheet Metal, Vinyl Flex, Rectangular Fiberglass, etc.).
_DUCT_MATERIAL_TOKENS = {
    "ShtMetl", "ShMt", "VinlFlx", "VlFx", "RectFbg", "RtFg",
    "InsDuct", "FlxLNR",
}

# Section / structural marker strings that appear as the first string
# of a DUCT child record but aren't room names.
_DUCT_MARKER_TOKENS = {"PREF", "LOC", "RUN", "EqualFric", "ConstStatic"}

# Wrightsoft duct identifier grammar: 2-3 letter prefix (st=supply
# trunk, sb=supply branch, rb=return branch, rt=return trunk, rrs=
# return riser, srs=supply riser, sr=supply runout) + 1-3 digits +
# optional trailing letter. These are duct path IDs, not zones.
_DUCT_ID_PATTERN = re.compile(r"^(st|sb|sr|srs|rb|rt|rrs)\d{1,3}[A-Z]?$",
                              re.IGNORECASE)


def _parse_duct_system_hierarchy(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Return the project's system → zones hierarchy by walking the
    DUCT umbrella block.

    Each returned dict:
        {"duct_label":   str | None  e.g. "RectTrunk/RoundBranch-AD"
         "sizing_model": str | None  e.g. "EqualFric"
         "zones":        list[str]   ordered, deduplicated room names}

    Empty / unlabeled systems are filtered out (Wrightsoft writes
    template-section PREFs for sketch/default state).
    """
    bodies = _block_bodies(file_bytes, "DUCT")
    systems: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for body in bodies:
        strs = _utf16_strings_in_block(body, min_len=2)
        # Dedupe within record — Wrightsoft repeats some labels 2-3x
        unique: List[str] = []
        for s in strs:
            if s not in unique:
                unique.append(s)
        if not unique:
            continue
        first = unique[0]

        # PREF record = new system header
        if first == "PREF":
            label = next(
                (s for s in unique[1:]
                 if len(s) > 3
                 and s not in _DUCT_MARKER_TOKENS
                 and s not in _DUCT_MATERIAL_TOKENS),
                None,
            )
            sizing = next(
                (s for s in unique[1:] if s in ("EqualFric", "ConstStatic")),
                None,
            )
            current = {"duct_label": label, "sizing_model": sizing, "zones": []}
            systems.append(current)
            continue

        if current is None:
            continue
        if first in _DUCT_MARKER_TOKENS or first in _DUCT_MATERIAL_TOKENS:
            continue
        if _DUCT_ID_PATTERN.fullmatch(first):
            continue

        # Treat the first string as a zone name. Strip trailing "-A" /
        # "-B" / ... sub-register suffix so multiple registers in one
        # room don't inflate the zone count.
        zone = re.sub(r"-[A-Z]$", "", first)
        if zone not in current["zones"]:
            current["zones"].append(zone)

    return [s for s in systems if s["zones"] and s.get("duct_label")]


# ─── Rectangular duct dimensions (Day-7 Phase D, partial) ─────────────
#
# Richard's Round-3 complaint: "Multiple rectangular ductwork missing
# in the BOM report. For example 6x10, 10x16, 10x12, 15x21, 16x14, 6x14,
# 6x18, 6x8, 10x10 and many more."
#
# Per-segment binary decoding is a multi-day investigation. The lighter-
# weight fix that closes the immediate gap: scan the file for distinct
# rectangular-dimension strings ("NxM") and surface them to the AI in
# the prompt. The AI then emits BOM lines for sizes it would otherwise
# skip entirely.
#
# Filtered to plausible HVAC duct dimensions only:
#   * width 4-36 inches (residential trunk + branch range)
#   * height 3-30 inches
#   * skip the giant "14x3" / "10x9" page-header artifacts that flood
#     the file (these aren't duct dimensions, they're Wrightsoft UI
#     layout coordinates).

# Known HVAC brands the contractor might pick from. Detected by simple
# count-in-file scan; only inferred when one brand dominates.
_HVAC_BRANDS = (
    "Carrier", "Goodman", "Lennox", "Trane", "Rheem", "Bryant",
    "Mitsubishi", "Daikin", "York", "Amana", "Heil", "Maytag",
    "American Standard", "Ruud", "Payne",
)


def _infer_dominant_brand(file_bytes: bytes) -> Optional[str]:
    """Day-8 — surface the contractor's actual equipment brand when one
    is dominant in the project file.

    Returns the brand name if a single brand has ≥3 mentions AND beats
    the runner-up by ≥3 (i.e. clear signal, not noise). Returns None
    otherwise (multi-brand projects, or no dominant brand detected) so
    the AI falls back to the contractor profile's default brand.

    Validated empirically:
      Edge:    Trane(7) → "Trane"
      McGinty: Bryant(7) → "Bryant"
      Easy:    Trane(3) → "Trane"
      Average: 8 brands tied at 1-2 → None (Wrightsoft default list,
               not a real contractor preference)
    """
    try:
        text = file_bytes.decode("utf-16-le", errors="replace")
    except Exception:
        return None
    counts = [(b, text.count(b)) for b in _HVAC_BRANDS]
    counts = [(b, n) for b, n in counts if n > 0]
    if not counts:
        return None
    counts.sort(key=lambda x: -x[1])
    top_brand, top_n = counts[0]
    runner_up = counts[1][1] if len(counts) > 1 else 0
    if top_n >= 3 and (top_n - runner_up) >= 3:
        return top_brand
    return None


_NXM_RE = re.compile(r'\b(\d{1,2})\s*[xX]\s*(\d{1,2})\b')

def _extract_rectangular_duct_dims(file_bytes: bytes) -> List[tuple]:
    """Return distinct (w, h) duct dimensions in the file, ordered by
    descending frequency then by w * h. Empty list if none plausible
    found.

    Heuristic filters:
      - 4 ≤ w ≤ 36 AND 4 ≤ h ≤ 30  (HVAC residential range; bumped
        height min from 3 to 4 on Day-7 — height=3 turned out to be
        UI layout artifacts ("14x3" / "10x3") not real ducts, hit on
        the Easy fixture's smaller binary where occurrence-count
        filter alone wasn't enough)
      - drop the "14x3" / "10x9" / "60x3" page-header / layout
        artifacts that appear 100+ times each (a real duct size
        rarely exceeds 8-10 occurrences across one project)
    """
    from collections import Counter
    try:
        text = file_bytes.decode("utf-16-le", errors="replace")
    except Exception:
        return []
    ctr: Counter = Counter()
    for w, h in _NXM_RE.findall(text):
        w, h = int(w), int(h)
        if 4 <= w <= 36 and 4 <= h <= 30:
            ctr[(w, h)] += 1
    # Drop artifacts that occur > 50 times — real duct sizes don't
    # repeat that much in a single project.
    plausible = {k: v for k, v in ctr.items() if v <= 50}
    # Sort: most frequent first, ties broken by area
    return sorted(
        plausible.items(),
        key=lambda kv: (-kv[1], -(kv[0][0] * kv[0][1])),
    )


def _infer_equipment_composition(ecductsys_labels: List[str]) -> Dict[str, Any]:
    """Day-7 — infer what equipment types each system contains, based
    on the names Wrightsoft attached to its systems.

    Different system types have different equipment compositions:

      Furnace-based (gas/oil):   Furnace + Evap Coil + Condenser + AHU
                                 (the McGinty case)
      AHU heat-pump:             AHU + Condenser
                                 (the Edge case — coil is built into the
                                 AHU, NOT a separate line item; no furnace)
      Heat pump:                 Air Handler + Heat Pump
      Unknown / unlabeled:       Safe default = AHU + Condenser

    Returns:
        {
          "label":      str  — short tag for the prompt ("furnace-based",
                              "AHU-only", etc.)
          "per_system": list[str] — equipment types to emit per system
          "excluded":   list[str] — types to explicitly NOT emit, with
                                    rationale (kills phantom-emission
                                    failure class on Edge-style projects)
        }
    """
    # Normalize labels — uppercase, strip whitespace
    labels = [l.upper().strip() for l in (ecductsys_labels or [])]

    has_furnace = any("FURNACE" in l for l in labels)
    has_ahu     = any(("AHU" in l) or ("AIR HANDLER" in l) for l in labels)
    has_hp      = any(("HEAT PUMP" in l) or l.startswith("HP")
                      or " HP" in l for l in labels)

    # Furnace-based — has separate evap coil
    if has_furnace:
        return {
            "label":      "furnace-based (gas/oil + AHU + coil + condenser)",
            "per_system": [
                "1× Gas Furnace",
                "1× Air Handler Unit (AHU)",
                "1× Evaporator Coil (separate from AHU)",
                "1× Condenser Unit",
            ],
            "excluded": [],
        }

    # AHU heat-pump-coil-integrated — Edge case
    if has_ahu and not has_furnace:
        return {
            "label":      "AHU-only with integrated coil (heat-pump-style)",
            "per_system": [
                "1× Air Handler Unit (AHU) with integrated evaporator coil",
                "1× Condenser Unit",
            ],
            "excluded": [
                "Gas Furnace (project has no furnaces)",
                "separate Evaporator Coil (it's integrated into the AHU)",
            ],
        }

    # Heat pump with named "HP" label
    if has_hp:
        return {
            "label":      "heat-pump-based",
            "per_system": [
                "1× Air Handler Unit (AHU)",
                "1× Heat Pump (outdoor unit)",
            ],
            "excluded": [
                "Gas Furnace (project is heat-pump-based)",
                "separate Condenser (the heat pump unit IS the condenser)",
            ],
        }

    # Safe fallback when no useful labels found
    return {
        "label":      "unknown — using safe default (AHU + condenser)",
        "per_system": [
            "1× Air Handler Unit (AHU)",
            "1× Condenser Unit",
        ],
        "excluded": [
            "Gas Furnace (unconfirmed — only emit if design data explicitly lists one)",
            "separate Evaporator Coil (unconfirmed — only emit if explicitly listed)",
        ],
    }


def _build_binary_enrichment_lines(
    file_bytes: bytes,
    text_equipment: List[Dict[str, Any]],
    text_rooms: List[Dict[str, Any]],
) -> List[str]:
    """Extract narrative-useful signals from RUP binary blocks the
    text-regex parser doesn't surface. Returns a list of lines to
    append to raw_rup_context.

    Phase 1 of Path B (May 2026 enrichment) — see RUP_BINARY_LAYOUT.md
    in designer-desktop _repo-docs for the empirical block inventory
    that drives which tags get sampled here.

    Sections emitted (each only if its block carries data):
      EQUIPMENT LIBRARY  — distinct equipment-type names from EQUIP
      EQUIPMENT PLACEMENT — count of ZEQUIP records (per-zone equipment)
      ROOMS (BALDUCT)    — real room names from BALDUCT records;
                           skipped when text_rooms already populated
      DUCT SYSTEM        — contractor's chosen duct-system label
                           from the DUCT umbrella block (e.g.
                           "Flex branch/trunks with junction boxes")
      REGISTER SIZING    — DREGINFO totals: register count, total
                           airflow CFM, total face area sq.in
      DESIGN COMPLEXITY  — DUCTRUN/DREGINFO/FITNG counts
    """
    from collections import Counter

    out: List[str] = []

    # ─────────────────────────────────────────────────────────────────
    # SECTION ORDER MATTERS — the AI anchors on what it sees first.
    #
    # Pre-Day-3 we led with EQUIPMENT LIBRARY (the inflated catalog of
    # equipment models the contractor has loaded — 21 split-AC entries,
    # 21 furnaces, etc.) and the AI happily emitted 14x AHU / 14x
    # condenser on McGinty (real answer: 3 systems). The library is
    # available equipment templates, NOT placements.
    #
    # Day-3 fix: ZEQUIP placement count goes FIRST with strong
    # "do not exceed" language. ECDUCTSYS named labels (when present)
    # go SECOND so the AI sees real placed names ("FURNACE 1",
    # "AHU - 1"). LIBRARY moves LAST + gets demoted to "menu of
    # options, ignore for sizing".
    # ─────────────────────────────────────────────────────────────────

    # 1) AUTHORITATIVE SYSTEM HIERARCHY — the Day-4 headline. Decodes
    # the DUCT umbrella block into N systems + their zones (verified
    # against the McGinty Wrightsoft project on Day-4: file decodes
    # to 3 systems / 23 zones, UI shows 3 systems / 24 zones — only
    # off-by-1 zone, system count exact).
    #
    # This is THE source of truth for equipment line counts. The
    # number of systems = the number of each major equipment type
    # the BOM should emit (1 AHU + 1 condenser + 1 furnace per
    # system, typically).
    try:
        systems = _parse_duct_system_hierarchy(file_bytes)
    except Exception:
        systems = []
    if systems:
        total_zones = sum(len(s["zones"]) for s in systems)
        # Day-7 — infer equipment COMPOSITION (not just count) from
        # ECDUCTSYS labels. Day-4 dictated "1 furnace + 1 coil + 1 AHU
        # + 1 condenser per system" for every project, which produced
        # phantom Gas Furnaces and phantom separate Evap Coils on
        # AHU-only / heat-pump-coil-integrated projects (Edge case).
        # Inferred composition kills that regression class.
        try:
            ec_bodies = _block_bodies(file_bytes, "ECDUCTSYS")
        except Exception:
            ec_bodies = []
        labels: List[str] = []
        for body in ec_bodies:
            strs = _utf16_strings_in_block(body, min_len=3)
            for s in strs:
                if s and s not in labels:
                    labels.append(s)
                    break
        composition = _infer_equipment_composition(labels)

        out.append(
            f"=== SYSTEM HIERARCHY (authoritative from binary: "
            f"{len(systems)} systems / {total_zones} zones) ==="
        )
        out.append(
            f"  This project has EXACTLY {len(systems)} HVAC system(s)."
        )
        for i, s in enumerate(systems, 1):
            zones_disp = ", ".join(s["zones"])
            if len(zones_disp) > 120:
                zones_disp = zones_disp[:117] + "..."
            label = s.get("duct_label") or "(unlabeled)"
            out.append(
                f"  System {i} (duct prefs: {label}): "
                f"{len(s['zones'])} zones — {zones_disp}"
            )
        # Composition-driven equipment instruction
        equip_list = ", ".join(composition["per_system"])
        excluded = composition.get("excluded") or []
        out.append(
            f"  PROJECT EQUIPMENT TYPE: {composition['label']} "
            f"(inferred from ECDUCTSYS labels: {labels[:4] or ['(none — using safe default)']})"
        )
        out.append(
            f"  CRITICAL — emit per system: {equip_list}. "
            f"Total = exactly {len(systems)} of each listed type. "
            f"DO NOT emit: {', '.join(excluded) if excluded else '(none excluded)'}. "
            "Heat kits, ERVs, and humidifiers only if explicitly indicated "
            "in the design data; default to 0 of those."
        )
        out.append("")

    # ─── EQUIPMENT BRAND (Day-8) ─────────────────────────────────────
    # Surface the contractor's actual brand preference when the file
    # clearly favors one. Closes Richard's Round-2 "wrong manufacturer"
    # complaint partway — at least the AI gets the brand right when
    # the file signal is unambiguous.
    dominant_brand = _infer_dominant_brand(file_bytes)
    if dominant_brand:
        out.append("=== EQUIPMENT BRAND (inferred from file) ===")
        out.append(
            f"  Project favors brand: {dominant_brand}. When emitting "
            "AHU / Condenser / Furnace / Heat Pump lines, prefer this "
            "brand over the contractor profile's catalog default. "
            "Other brands may appear in default lists — those are "
            "Wrightsoft templates, not contractor selections."
        )
        out.append("")

    # ─── RECTANGULAR DUCT + GRILLE SIZES (Day-7/8) ──────────────────
    # Distinct (width × height) rectangular dimensions extracted from
    # the file. The same NxM extractor catches rectangular duct
    # cross-sections AND register/grille face dimensions — they share
    # the same string format in the binary, no way to distinguish
    # from raw text alone. So the prompt asks for BOM lines covering
    # both purposes.
    #
    # Closes Richard's Round-3 complaints:
    #   - "Multiple rectangular ductwork missing in the BOM report"
    #   - "Grille sizes and count do not match the rup file"
    #
    # Per-segment LF (Richard: "6-in flex duct total is not 480 ft")
    # is NOT yet decoded — DUCTRUN +0x0c was previously hypothesized
    # as length but Day-7 investigation confirmed it's airflow (CFM)
    # not length. Per-segment LF likely requires walking DUCTLOC
    # coordinate pairs and computing Euclidean distance — separate
    # multi-day decoder still on the punch list.
    rect_dims = _extract_rectangular_duct_dims(file_bytes)
    if rect_dims:
        out.append(
            f"=== RECTANGULAR DIMENSIONS ({len(rect_dims)} distinct, "
            "extracted from binary) ==="
        )
        out.append(
            "  These dimensions cover BOTH rectangular duct cross-"
            "sections AND register/grille face sizes — Wrightsoft "
            "stores them in the same NxM format."
        )
        dim_strs = ", ".join(
            f"{w}×{h} ({n}×)" for (w, h), n in rect_dims[:25]
        )
        if len(rect_dims) > 25:
            dim_strs += f", ... (+{len(rect_dims) - 25} more)"
        out.append(f"  Sizes present: {dim_strs}")
        out.append(
            "  CRITICAL: Emit a separate BOM line for EACH distinct "
            "size for both ductwork and registers/grilles. Estimate "
            "linear footage per duct size and unit count per grille "
            "size from the project's total counts and zone "
            "distribution. Missing any of these sizes from the BOM "
            "is a failure mode — contractor reports flag this "
            "explicitly."
        )
        out.append("")

    # 2) ZEQUIP fallback — when the hierarchy decoder finds no
    # systems (Wrightsoft variants we haven't reverse-engineered yet),
    # fall back to the cruder ZEQUIP-zone-count ceiling.
    try:
        zeq_count = len(_block_bodies(file_bytes, "ZEQUIP"))
    except Exception:
        zeq_count = 0
    if zeq_count and not systems:
        out.append(
            f"=== EQUIPMENT PLACEMENT (fallback: {zeq_count} zone records) ==="
        )
        out.append(
            f"  This project has {zeq_count} ZEQUIP record(s) = "
            f"{zeq_count} zones that have equipment placed in them."
        )
        out.append(
            "  CRITICAL: zones != equipment units. In residential HVAC, one "
            "AHU + one condenser typically serves 4-10 zones. Estimate the "
            "number of systems by zone clustering (residential rule of "
            "thumb: ~6-10 zones per system). Total emitted equipment line "
            "items (AHU + condenser + furnace + coil + heat-kit + ERV + "
            "humidifier combined) MUST NOT exceed "
            f"{zeq_count} as a HARD ceiling, and will usually be far lower."
        )
        out.append("")

    # 2) Named equipment from ECDUCTSYS — when Wrightsoft labels a
    # system explicitly (e.g. "FURNACE 1", "AHU - 1", "Entire House"),
    # the label lives in the ECDUCTSYS block which pairs 1:1 with
    # ZEQUIP. A subset of records carry labels; the rest are sub-zones
    # that roll up to the most recent named record (pending Richard's
    # confirmation Day-3 — see PHASE_10_ZEQUIP_QA.md). Empirically
    # validated across all 4 sample fixtures.
    try:
        ec_bodies = _block_bodies(file_bytes, "ECDUCTSYS")
    except Exception:
        ec_bodies = []
    named_labels: List[str] = []
    for body in ec_bodies:
        strs = _utf16_strings_in_block(body, min_len=3)
        # Records often repeat the label 2-3 times; dedupe within record
        unique = []
        for s in strs:
            if s not in unique:
                unique.append(s)
        if unique:
            # First string is the system / equipment label
            named_labels.append(unique[0])
    if named_labels:
        label_counts = Counter(named_labels)
        out.append(
            f"=== NAMED EQUIPMENT ({len(named_labels)} of {len(ec_bodies)} "
            f"zones explicitly labeled) ==="
        )
        for label, count in label_counts.most_common():
            out.append(f"  {count}x labeled '{label}'")
        out.append(
            "  (These are the explicit equipment labels Wrightsoft "
            "attached to specific zones. Unlabeled zones inherit from "
            "the most recent labeled system.)"
        )
        out.append("")

    # 3) Real room names from BALDUCT. The text-regex parser misses
    # rooms entirely on Manual D / ducts-only RUPs. BALDUCT carries
    # them cleanly. Skip if text_rooms already populated (Edge case)
    # since we'd just duplicate the rooms section.
    if not text_rooms:
        try:
            bal_bodies = _block_bodies(file_bytes, "BALDUCT")
        except Exception:
            bal_bodies = []
        room_names: List[str] = []
        for body in bal_bodies:
            strs = _utf16_strings_in_block(body, min_len=2)
            if strs:
                room_names.append(strs[0])
        # Drop obvious garbage tokens (parser tags like "rb1" / "rb2")
        # while keeping real names like "Master Bedroom" / "PANTRY".
        cleaned = [n for n in room_names if not re.fullmatch(r"[a-z]{1,3}\d{1,3}", n)]
        if cleaned:
            out.append(f"=== ROOMS ({len(cleaned)} from balance records) ===")
            for name in cleaned:
                out.append(f"  {name}")
            out.append("")

    # 4) Duct system label — extracted from the DUCT umbrella block,
    # first record carrying multi-character UTF-16 strings. Wrightsoft
    # nests DUCTLOC (geometry) and DUCTRUN (segments) under DUCT;
    # only the parent record carries the contractor's system-name
    # label (e.g. "Flex branch/trunks with junction boxes",
    # "RectTrunk/Flex Branch - Updated:") plus the sizing model
    # ("EqualFric"). This is catalog-relevant: the system label is
    # what the contractor's BOM aliases to (Flex vs Rigid vs Rectangular
    # trunk-and-branch all source different SKU families).
    try:
        duct_bodies = _block_bodies(file_bytes, "DUCT")
    except Exception:
        duct_bodies = []
    duct_system_label: Optional[str] = None
    duct_sizing_model: Optional[str] = None
    for body in duct_bodies[:8]:  # scan first few; usually it's body 0
        strs = _utf16_strings_in_block(body, min_len=4)
        # Skip 3-char child markers ('LOC', 'RUN', 'PREF', etc.)
        meaningful = [s for s in strs if len(s) > 4]
        if meaningful:
            # Heuristic: first long string is the system label; an
            # "EqualFric" / "ConstStatic" sibling is the sizing model
            duct_system_label = meaningful[0]
            for s in meaningful[1:]:
                if any(k in s for k in ("Fric", "Static", "Equal", "Const")):
                    duct_sizing_model = s
                    break
            break
    if duct_system_label:
        out.append("=== DUCT SYSTEM ===")
        out.append(f"  System: {duct_system_label}")
        if duct_sizing_model:
            out.append(f"  Sizing model: {duct_sizing_model}")
        out.append(
            "  (This is the contractor's chosen duct system — it determines "
            "which SKU family applies: flex vs rigid vs rectangular trunk.)"
        )
        out.append("")

    # 5) Register sizing totals — DREGINFO carries per-register airflow
    # and face area. Total CFM is a strong scale signal: an 8-AHU
    # residence sums to ~64-68k CFM, a single-AHU ADU to ~8-10k. The
    # AI can use the totals to sanity-check register-count line items
    # and to estimate trunk sizing.
    #
    # Field interpretation (empirical, May 2026):
    #   +0x24 float = airflow CFM per register (values cluster at
    #                  300 / 400 across all 3 sample RUPs)
    #   +0x28 float = face area sq.in per register (75 / 80)
    # See _repo-docs/RUP_BINARY_LAYOUT.md for the dump that
    # established this — Edge totals 66,700 CFM which checks out at
    # ~8,300 CFM per AHU for 8 AHUs.
    try:
        dreg_bodies = _block_bodies(file_bytes, "DREGINFO")
    except Exception:
        dreg_bodies = []
    if dreg_bodies:
        try:
            cfms = [
                struct.unpack_from("<f", b, 0x24)[0]
                for b in dreg_bodies
                if len(b) >= 0x28
            ]
            areas = [
                struct.unpack_from("<f", b, 0x28)[0]
                for b in dreg_bodies
                if len(b) >= 0x2C
            ]
        except Exception:
            cfms, areas = [], []
        nonzero_cfms = [c for c in cfms if c > 0.5]
        if nonzero_cfms:
            total_cfm  = sum(nonzero_cfms)
            total_area = sum(a for a in areas if a > 0.5)
            avg_cfm    = total_cfm / len(nonzero_cfms)
            out.append("=== REGISTER SIZING ===")
            out.append(
                f"  {len(nonzero_cfms)} registers, total {total_cfm:,.0f} CFM "
                f"(avg {avg_cfm:.0f} CFM/register)"
            )
            if total_area > 0:
                out.append(f"  Total face area: {total_area:,.0f} sq.in")
            out.append(
                "  (Use total CFM to size trunk ducts and to sanity-check "
                "register quantity lines.)"
            )
            out.append("")

    # 6) Design complexity / scale signals — record counts for the
    # three big per-instance block types. Even without per-record
    # decode (deferred to Phase C/D), the magnitudes help the AI
    # reason about scale: 22 ducts vs 192 ducts is a different job.
    try:
        ductrun_count = len(_block_bodies(file_bytes, "DUCTRUN"))
        dreginfo_count = len(_block_bodies(file_bytes, "DREGINFO"))
        fitng_count = len(_block_bodies(file_bytes, "FITNG"))
    except Exception:
        ductrun_count = dreginfo_count = fitng_count = 0
    if ductrun_count or dreginfo_count or fitng_count:
        out.append("=== DESIGN COMPLEXITY (binary block counts) ===")
        if ductrun_count:
            out.append(f"  Duct runs (DUCTRUN): {ductrun_count}")
        if dreginfo_count:
            out.append(f"  Registers/diffusers (DREGINFO): {dreginfo_count}")
        if fitng_count:
            out.append(f"  Fitting instances (FITNG): {fitng_count}")
        out.append(
            "  (Use these counts to estimate fitting, register, and duct-run "
            "quantities when structured arrays are empty.)"
        )
        out.append("")

    # 7) LAST — equipment library. DEMOTED from its old Day-1 position
    # at the top of the prompt because the AI was anchoring on it
    # ("21x Split AC available, so emit 14 AHU lines"). This is the
    # menu of equipment models the contractor has loaded into the
    # project, not the count of placed equipment. Kept in the prompt
    # at all only because the brand/model spread is useful catalog-
    # matching signal (e.g. "contractor uses Goodman split-ACs").
    try:
        equip_records = _parse_equip_blocks(file_bytes)
    except Exception:
        equip_records = []
    if equip_records:
        name_counts = Counter(e.get("raw_name", "") for e in equip_records if e.get("raw_name"))
        if name_counts:
            out.append(
                f"=== AVAILABLE EQUIPMENT MODELS ({sum(name_counts.values())} entries) ==="
            )
            for name, count in name_counts.most_common():
                out.append(f"  {count} model(s): {name}")
            out.append(
                "  IMPORTANT: This is the project's available-equipment "
                "MENU — not what's installed. Do NOT use these counts to "
                "size the BOM. The authoritative placement count is the "
                "EQUIPMENT PLACEMENT section at the top of this context."
            )
            out.append("")

    return out


def _build_raw_context(
    project: Dict[str, Any],
    building: Dict[str, str],
    equipment: List[Dict[str, Any]],
    rooms: List[Dict[str, Any]],
    full_text: str,
    file_bytes: Optional[bytes] = None,
) -> str:
    """Assemble the narrative text the BOM engine AI prompt reads when the
    structured duct_runs / fittings / registers arrays are sparse.

    This is the `raw_rup_context` field and is the hybrid fallback mechanism
    from the spec — keep it rich enough that an HVAC-literate LLM can
    estimate quantities from it.

    May 2026 enrichment (Phase 1 of Path B): when ``file_bytes`` is
    supplied, additional sections are appended from binary blocks that
    the text-regex parser doesn't surface — equipment library names
    from EQUIP, real room names from BALDUCT (replaces the missing
    rooms section on Manual D / ducts-only RUPs), and aggregate counts
    from DUCTRUN/DREGINFO/FITNG/ZEQUIP. This roughly doubles the AI's
    context on Easy + Average sample RUPs (487/462 → ~770/1080 chars)
    and keeps it backwards-compatible: callers that don't pass
    file_bytes get the original text-only context.
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

    # ─── Binary-derived enrichment (Phase 1 — May 2026) ────────────
    # All optional. Each section appends only if file_bytes is provided
    # AND the corresponding block has data. Keeps test fixtures and any
    # caller that hands us pre-extracted text+arrays working unchanged.
    if file_bytes:
        lines.extend(_build_binary_enrichment_lines(file_bytes, equipment, rooms))

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

    raw_context = _build_raw_context(
        project, building, equipment, rooms, full_text,
        file_bytes=file_bytes,
    )

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
