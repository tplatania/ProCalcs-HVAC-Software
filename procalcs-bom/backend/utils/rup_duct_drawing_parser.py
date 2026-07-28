"""rup_duct_drawing_parser.py — decode CSDuctOb + CRDuctOb drawing
objects (Increment 2b).

RUP_BINARY_FORMAT.md §2b. Each drawing object carries both the run
size AND the endpoint coordinates in one record — no join to
DUCTRUN needed for the per-piece Duct Cuts list.

Key structural facts from §2b:

  * Instance envelope: `FF FE FF <len:u8> <UTF-16 ×len>` for each
    CString field. Fields separated by `CD CD BA` markers with
    variable padding.
  * Diameter is stored as TEXT, not a numeric value:
      - Round:   "8 \"" or "4 \""     → parse to diameter_in
      - Rect:    "Duct 12 \" x 10 \"" → parse to width_in × height_in
  * Endpoints are two packed u32s: high 16 bits = x, low 16 bits = y.
  * Grid unit = 1 inch (three converging static evidence lines per
    §2b.3; dynamic byte-proof pending, non-blocking).

Consumer contract per drawn segment:

    {
      "run_id":        str,     # "Supply Duct175" / "Return Duct42"
      "shape":         str,     # "round" | "rect"
      "diameter_in":   float,   # round only
      "width_in":      float,   # rect only
      "height_in":     float,   # rect only
      "cut_length_ft": float,   # hypot(Δx, Δy) / 12
    }

Rejects segments whose cut length is non-physical (>200 ft) per
§2b.5 as mis-parses from label-collisions with size strings.
"""

from __future__ import annotations

import logging
import math
import re
import struct
from typing import Iterator, List, Optional, Tuple

from .rup_reader import RupReader

logger = logging.getLogger(__name__)


# ─── Constants ────────────────────────────────────────────────────

# CString envelope prefix: FF FE FF <len:u8>
_CSTRING_PREFIX = b"\xff\xfe\xff"

# Label pattern per §2b.2: "Supply DuctN" or "Return DuctN".
_LABEL_RE = re.compile(r"^(?:Supply|Return) Duct\d+$")

# Size string patterns per §2b.1:
#   Round: "N \""  where N is an integer number of inches
#   Rect:  "Duct W \" x H \""
_ROUND_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\"?\s*$")
_RECT_RE  = re.compile(r"^\s*Duct\s+(\d+(?:\.\d+)?)\s*\"?\s*x\s*(\d+(?:\.\d+)?)\s*\"?\s*$")

# Reject segments longer than this — mis-parses per §2b.5.
_MAX_PHYSICAL_LENGTH_FT = 200.0

# Class name → drawing side
_CLASS_NAMES = {
    "CSDuctOb": "supply",  # rect trunks + round branches
    "CRDuctOb": "return",  # rect trunks + grilles
}


# ─── Primitives ────────────────────────────────────────────────────

def _read_cstring_at(buf: bytes, pos: int) -> Optional[Tuple[str, int]]:
    """Try to read an MFC CString envelope starting at `pos`.

    Returns (decoded_string, bytes_consumed) or None if the prefix
    doesn't match. Envelope: FF FE FF <len:u8> <UTF-16LE ×len>."""
    if pos + 4 > len(buf):
        return None
    if buf[pos:pos + 3] != _CSTRING_PREFIX:
        return None
    char_count = buf[pos + 3]
    body_start = pos + 4
    body_end = body_start + char_count * 2
    if body_end > len(buf):
        return None
    try:
        text = buf[body_start:body_end].decode("utf-16-le")
    except UnicodeDecodeError:
        return None
    return text, body_end - pos


def _iter_cstrings_in_range(buf: bytes, start: int,
                             end: int) -> Iterator[Tuple[int, str]]:
    """Yield (position, decoded_string) for every CString envelope
    found in buf[start:end]. Skips 1 byte at a time on failed matches —
    the FF FE FF pattern is distinctive enough that false positives
    are rare."""
    pos = start
    while pos < end - 4:
        hit = buf.find(_CSTRING_PREFIX, pos, end)
        if hit < 0:
            return
        result = _read_cstring_at(buf, hit)
        if result is None:
            pos = hit + 1
            continue
        text, consumed = result
        yield (hit, text)
        pos = hit + consumed


def _find_class_regions(buf: bytes) -> dict:
    """Locate the byte regions containing CSDuctOb and CRDuctOb
    instances. Region starts right after the class-name declaration;
    ends at the next class declaration (or a fixed cap)."""
    regions = {}
    for class_name in _CLASS_NAMES:
        ascii_bytes = class_name.encode("ascii")
        idx = buf.find(ascii_bytes)
        if idx < 0:
            continue
        # Region starts after the class-name string. There's some MFC
        # bookkeeping (typically ~8 bytes) before the first instance.
        regions[class_name] = idx + len(ascii_bytes)
    # Sort by start position; each region ends where the next begins
    # (or at end-of-file for the last).
    sorted_classes = sorted(regions, key=lambda c: regions[c])
    starts = [regions[c] for c in sorted_classes]
    starts.append(len(buf))
    return {sorted_classes[i]: (starts[i], starts[i + 1])
            for i in range(len(sorted_classes))}


# ─── Instance walker ──────────────────────────────────────────────

def _parse_instance(buf: bytes, label_pos: int, label: str,
                    next_label_pos: int, side: str
                    ) -> Optional[dict]:
    """Decode one drawing-object instance from its label position to
    the next label position (or region end).

    Layout per §2b.2:
      * label CString (already at label_pos)
      * P1 u32 (packed x=high16, y=low16)
      * P2 u32 (packed x=high16, y=low16)
      * MFC field markers + property CStrings
      * size CString (somewhere in the field stream)
    """
    # Skip the label CString itself.
    label_end = label_pos + 4 + len(label) * 2  # 4-byte envelope + UTF-16 body
    if label_end + 8 > len(buf):
        return None

    # The two endpoints are consecutive u32 immediately after the
    # label. Empirically confirmed on the Supply Duct175 worked
    # example (§2b.2): 0x03E409A2 → (996, 2466), 0x03E50A14 →
    # (997, 2580).
    p1_raw = struct.unpack_from("<I", buf, label_end)[0]
    p2_raw = struct.unpack_from("<I", buf, label_end + 4)[0]
    x1, y1 = (p1_raw >> 16) & 0xFFFF, p1_raw & 0xFFFF
    x2, y2 = (p2_raw >> 16) & 0xFFFF, p2_raw & 0xFFFF

    dx = x2 - x1
    dy = y2 - y1
    cut_length_ft = math.hypot(dx, dy) / 12.0

    # §2b.5 physicality reject — mis-parses show up as absurd lengths.
    if cut_length_ft > _MAX_PHYSICAL_LENGTH_FT:
        return None
    if cut_length_ft <= 0:
        return None

    # Walk the CStrings within this instance's region to find the size
    # string. The size is identifiable by content — "Duct W x H" for
    # rect, or "N\"" for round. Skip property CStrings like "0.0",
    # "1", or short numeric values.
    instance_end = min(next_label_pos, len(buf))
    shape = None
    diameter_in = None
    width_in = None
    height_in = None
    for _pos, s in _iter_cstrings_in_range(buf, label_end + 8, instance_end):
        stripped = s.strip()
        # Rect: "Duct W \" x H \""
        m = _RECT_RE.match(stripped)
        if m:
            width_in = float(m.group(1))
            height_in = float(m.group(2))
            shape = "rect"
            break
        # Round: "N \"" — only accept if string doesn't look like a
        # property field (properties are usually "0.0" / "1" / short).
        # Round diameters are 3-30 typically.
        m = _ROUND_RE.match(stripped)
        if m:
            val = float(m.group(1))
            # Only treat as diameter if it looks like a duct size.
            # Property fields tend to be 0.0-2.0 (drops, counts).
            if 3.0 <= val <= 30.0:
                diameter_in = val
                shape = "round"
                break

    if shape is None:
        # No size found within the instance region — skip.
        return None

    out = {
        "run_id":        label,
        "side":          side,
        "shape":         shape,
        "cut_length_ft": round(cut_length_ft, 3),
    }
    if shape == "round":
        out["diameter_in"] = diameter_in
    else:
        out["width_in"] = width_in
        out["height_in"] = height_in
    return out


def parse_duct_segments(reader: RupReader) -> List[dict]:
    """Decode every CSDuctOb + CRDuctOb drawing-object instance into
    one per-segment dict per §2b.4's consumer contract.

    Returns segments in file order, with `side` populated ("supply"
    or "return") from which class region the instance came from.
    Non-physical mis-parses (>200 ft) are silently rejected per §2b.5.
    """
    buf = reader._buf
    regions = _find_class_regions(buf)
    out: List[dict] = []
    rejected = 0

    for class_name, (start, end) in regions.items():
        side = _CLASS_NAMES[class_name]
        # Find every label position (Supply DuctN / Return DuctN) in
        # this region.
        label_positions: List[Tuple[int, str]] = []
        for pos, s in _iter_cstrings_in_range(buf, start, end):
            if _LABEL_RE.match(s):
                label_positions.append((pos, s))
        # Decode each instance, using the next label position as the
        # end boundary.
        for i, (lpos, label) in enumerate(label_positions):
            next_pos = (label_positions[i + 1][0]
                         if i + 1 < len(label_positions) else end)
            # Day-29 (Richard's screenshot): side from the LABEL, not
            # the class region. MFC CArchive declares each class once
            # (first instance) — after both declarations, supply and
            # return instances interleave freely, so region-based
            # attribution mislabeled e.g. "Supply Duct56" as return.
            # Wrightsoft's own object name carries the side.
            label_side = "supply" if label.startswith("Supply") else "return"
            row = _parse_instance(buf, lpos, label, next_pos, label_side)
            if row is None:
                rejected += 1
                continue
            out.append(row)

    logger.info("rup_duct_drawing: %d segments (%d rejected as mis-parses)",
                len(out), rejected)
    return out
