"""
rup_extractor.py — SUPERSEDED by procalcs-bom/backend/utils/rup_parser.py

Kept for history. The canonical parser used by the production BOM pipeline
lives in the procalcs-bom package and produces a structured design_data
dict matching the BOM engine's contract (duct_runs / fittings / equipment /
registers / building / raw_rup_context). See:
    - procalcs-bom/backend/utils/rup_parser.py
    - procalcs-bom/backend/tests/test_rup_pipeline.py
    - docs/GERALD_HANDOFF_RUP_UPLOAD.md  (the driving spec)

This prototype returns narrative text rather than structured data. Its
primitives (extract_utf16_strings, parse_sections with BEG/END handling,
NON_ROOMS whitelist) were ported into the canonical parser.

Extracts HVAC load data from Wrightsoft Right-Suite Universal .rup files
and returns clean, LLM-ready text.

Usage:
    python rup_extractor.py yourfile.rup
    python rup_extractor.py yourfile.rup --output extracted.txt
    python rup_extractor.py yourfile.rup --json
"""

import re
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict


# Force UTF-8 on stdout so the '→' in Room→AHU assignments doesn't crash on
# Windows consoles (cp1252). No-op on Unix and on Windows consoles that are
# already UTF-8. Falls back silently if the stream can't be reconfigured.
def _ensure_utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


_ensure_utf8_stdout()


# ── Section types that contain HVAC load/design data worth keeping ──────────
LOAD_SECTIONS = {
    "JOBINFOK", "JOBINFO",          # project + contractor info
    "COMPONTY",                      # building component types
    "CConstruction",                 # construction assemblies
    "FLCLTY", "CEILTY", "WALLTY",   # floor/ceiling/wall types
    "GLAZTY",                        # glazing types
    "DOORSURF", "GLAZSURF",         # door/window surfaces
    "WALLSURF", "CEILSURF",         # wall/ceiling surfaces
    "SURFACE",                       # generic surfaces
    "INFVENT", "VNTREQ", "VENTEQ",  # infiltration & ventilation
    "ECDUCTSYS", "TDUCTSYS",        # duct systems
    "DUCTRUN", "DUCTLOC",           # duct runs & locations
    "SJD",                           # supply/junction duct
    "DLINFO",                        # design load info
    "REDIST", "REDI",               # redistribution
    "RGAREA",                        # register area
    "RptInfo",                       # report definitions
}

# Sections that are structural/internal noise — skip
SKIP_SECTIONS = {
    "RECHDR", "CConsMat", "CConsLayer", "CFSProp",
    "RHPANEL", "WALLINFO", "WALLTYINFO", "RB",
    "TDINFO", "ZIGI", "PartLinkInfo", "DetailMethod",
}


def extract_utf16_strings(data: bytes, min_len: int = 4) -> list[str]:
    """Pull all UTF-16 LE readable strings from binary data."""
    strings = []
    current = []
    i = 0
    while i < len(data) - 1:
        val = int.from_bytes(data[i:i+2], "little")
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


def parse_sections(text: str) -> dict[str, list[str]]:
    """Parse !BEG=SECTION ... !END=SECTION blocks into a dict.

    Balances the BEG/END pair by name so the body of one section can't bleed
    into the next when the lazy match otherwise over-reaches. Example of the
    previous bug: FLCLTY[1] captured '!BEG=RHPANEL\\nFS-STAPLE\\nBENDSUP'
    because !END=\\S+ accepted any END marker.
    """
    sections = defaultdict(list)
    # Backreference \1 forces !END= to match the same name as its !BEG=.
    pattern = re.compile(r"!BEG=(\S+)\s*(.*?)\s*!END=\1", re.DOTALL)
    for match in pattern.finditer(text):
        name = match.group(1)
        body = match.group(2).strip()
        if body:
            sections[name].append(body)
    return dict(sections)


def dedupe_preserve_order(lst: list[str]) -> list[str]:
    """Remove duplicates while preserving insertion order."""
    seen = set()
    result = []
    for item in lst:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def extract_job_info(sections: dict) -> str:
    """Format project/job information."""
    lines = []
    for key in ("JOBINFOK", "JOBINFO"):
        if key in sections:
            raw = dedupe_preserve_order(sections[key])[0]
            # Strip internal file paths (noisy)
            raw = re.sub(r"[A-Z]:\\[^\n]+", "", raw)
            raw = re.sub(r"\n{3,}", "\n\n", raw)
            lines.append(f"=== PROJECT INFO ===\n{raw.strip()}")
            break
    return "\n".join(lines)


def extract_equipment(text: str) -> str:
    """Pull AHU/equipment references and duct CFM data."""
    lines = ["=== EQUIPMENT & DUCT SUMMARY ==="]

    # AHU list
    ahu_match = re.search(r"(AHU - \d+(?:\|AHU - \d+)*)", text)
    if ahu_match:
        ahus = ahu_match.group(1).split("|")
        lines.append(f"Air Handling Units: {', '.join(ahus)}")

    # CFM annotations
    cfm_hits = re.findall(r"(\d+(?:\.\d+)?\s*cfm)", text, re.IGNORECASE)
    cfm_unique = dedupe_preserve_order(cfm_hits)
    if cfm_unique:
        lines.append(f"CFM values found: {', '.join(cfm_unique[:20])}")

    # Duct sizes
    duct_sizes = re.findall(r"\b(\d+\s*[xX]\s*\d+|\d+\s*\")", text)
    duct_unique = dedupe_preserve_order(duct_sizes)
    if duct_unique:
        lines.append(f"Duct dimensions: {', '.join(duct_unique[:20])}")

    # Room-to-AHU assignments
    room_ahu = re.findall(r"([A-Z][A-Z0-9 \-]+?)\n(AHU - \d+)", text)
    if room_ahu:
        # Drop false positives — the regex catches section markers and stray
        # AHU labels that live adjacent to real room names in the binary.
        NON_ROOMS = {
            "ECDUCTSYS", "TDUCTSYS", "DUCTRUN", "DUCTLOC", "SJD",
            "SURFACE", "WALLSURF", "CEILSURF", "GLAZSURF", "DOORSURF",
            "DLINFO", "REDI", "REDIST", "RGAREA", "RptInfo", "COMPONTY",
            "CConstruction", "CConsMat", "CConsLayer", "CFSProp",
            "RHPANEL", "WALLINFO", "WALLTYINFO", "RB", "TDINFO", "ZIGI",
            "PartLinkInfo", "DetailMethod", "INFVENT", "VNTREQ", "VENTEQ",
            "FLCLTY", "CEILTY", "WALLTY", "GLAZTY", "JOBINFO", "JOBINFOK",
        }
        assignments = []
        seen = set()
        for room, ahu in room_ahu:
            name = room.strip()
            # Drop known section markers and anything that looks like another
            # AHU label ("AHU - 1" → "AHU - 1" is meaningless).
            if name in NON_ROOMS or name.startswith("AHU"):
                continue
            key = (name, ahu.strip())
            if key in seen:
                continue
            seen.add(key)
            assignments.append((name, ahu.strip()))

        if assignments:
            lines.append("\nRoom → AHU assignments:")
            for room, ahu in assignments:
                lines.append(f"  {room} → {ahu}")

    return "\n".join(lines)


def extract_constructions(sections: dict) -> str:
    """Summarize building assembly types."""
    lines = ["=== BUILDING CONSTRUCTIONS ==="]
    for sec_name in ("COMPONTY", "CConstruction"):
        if sec_name in sections:
            unique = dedupe_preserve_order(sections[sec_name])
            for entry in unique[:30]:
                # First non-empty line is usually the label
                label = next((l.strip() for l in entry.split("\n") if l.strip()), "")
                if label and not label.startswith("!"):
                    lines.append(f"  {label}")
    return "\n".join(lines)


def extract_surfaces(sections: dict) -> str:
    """Pull surface/envelope definitions."""
    lines = ["=== SURFACES & ENVELOPE ==="]
    for sec_name in ("SURFACE", "WALLSURF", "CEILSURF", "GLAZSURF", "DOORSURF"):
        entries = sections.get(sec_name, [])
        unique = dedupe_preserve_order(entries)
        if unique:
            lines.append(f"\n-- {sec_name} ({len(unique)} unique) --")
            for e in unique[:10]:
                first_line = next((l.strip() for l in e.split("\n") if l.strip()), "")
                if first_line:
                    lines.append(f"  {first_line}")
    return "\n".join(lines)


def extract_duct_systems(sections: dict) -> str:
    """Summarize duct system definitions."""
    lines = ["=== DUCT SYSTEMS ==="]
    for sec_name in ("ECDUCTSYS", "TDUCTSYS", "DUCTRUN"):
        entries = sections.get(sec_name, [])
        unique = dedupe_preserve_order(entries)
        if unique:
            lines.append(f"\n-- {sec_name} --")
            for e in unique[:5]:
                lines.append(e[:200])
    return "\n".join(lines)


def extract_report_types(sections: dict) -> str:
    """List which reports are defined in the project."""
    lines = ["=== AVAILABLE REPORTS ==="]
    if "RptInfo" in sections:
        for entry in dedupe_preserve_order(sections["RptInfo"]):
            # Format: !CODE\nHuman readable name
            parts = [l.strip() for l in entry.split("\n") if l.strip()]
            if len(parts) >= 2:
                lines.append(f"  {parts[1]}")
            elif parts:
                lines.append(f"  {parts[0]}")
    return "\n".join(lines)


def build_llm_context(filepath: str) -> tuple[str, dict]:
    """Main entry point. Returns (text_for_llm, raw_sections_dict)."""
    data = Path(filepath).read_bytes()

    # Extract header
    try:
        header_raw = data[:0xe0].decode("utf-16-le", errors="replace")
    except Exception:
        header_raw = ""

    header_fields = dict(re.findall(r"(\w+)=([^\r\n]+)", header_raw))

    # Extract all UTF-16 text
    strings = extract_utf16_strings(data)
    full_text = "\n".join(strings)

    # Parse sections
    sections = parse_sections(full_text)

    # Build readable output
    blocks = [
        f"# Wrightsoft Right-Suite Universal Project",
        f"# App: {header_fields.get('APP', 'RSU')}  Version: {header_fields.get('VRSN', '?')}  Saved: {header_fields.get('TIMESTAMP', '?')}",
        "",
        extract_job_info(sections),
        "",
        extract_equipment(full_text),
        "",
        extract_constructions(sections),
        "",
        extract_surfaces(sections),
        "",
        extract_duct_systems(sections),
        "",
        extract_report_types(sections),
    ]

    return "\n".join(blocks), sections


def to_json(sections: dict) -> str:
    """Serialize deduplicated sections to JSON."""
    output = {}
    for name, entries in sections.items():
        unique = dedupe_preserve_order(entries)
        output[name] = unique
    return json.dumps(output, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract HVAC data from .rup files for LLM use")
    parser.add_argument("file", help="Path to .rup file")
    parser.add_argument("--output", help="Write output to file instead of stdout")
    parser.add_argument("--json", action="store_true", help="Output full section JSON")
    args = parser.parse_args()

    text, sections = build_llm_context(args.file)

    if args.json:
        result = to_json(sections)
    else:
        result = text

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"Written to {args.output}")
    else:
        print(result)
