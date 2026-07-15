"""rup_home_run_parser.py — decode per-register home-run duct lengths
from `DUCT` blocks (Increment 2c).

Wrightsoft stores the duct-system tree as one `DUCT` block per node:
one node per register RUNOUT (labels match the BALDUCT register
labels — "BATH 2-A", "PRM. BEDROOM", ...) plus a handful of trunk /
branch nodes ("dmn1" main trunk, "st1" stub, "rb1"/"rsb1" return
branch, and one unlabeled sheet-metal node). Each runout node carries
the run's ROUTED LENGTH in feet — the same geometry-derived footage
Wrightsoft's Rheia plugin sums into the 3-in duct takeoff
(SKU 10-00-190) at export time.

Validated against 20 (rup, Rheia-BOM xls) ground-truth pairs from the
Reliable corpus: the sum of runout lengths reproduces the xls
10-00-190 footage to within rounding (several pairs EXACT, e.g.
640.0/640, 597.0/597) — see repro notes 2026-07-15. Pairs that miss
are rup-vs-xls revision skew (the .rup was re-saved after the BOM
export), not decode error.

DUCT record layout (schema 13), cursor after the `!BEG=DUCT` tag:

  | field                | type            | notes                          |
  |----------------------|-----------------|--------------------------------|
  | schema               | u32             | 13 observed                    |
  | object id            | u32             |                                |
  | label                | u32len + UTF-16 | register / trunk name          |
  | supply parent        | u32len + UTF-16 | "dmn1" (trunk node ref)        |
  | return parent        | u32len + UTF-16 | "rb1" / "rsb1"                 |
  | design numbers ×15   | f32             | cfm / friction / velocity ...  |
  | duct type code       | u32len + UTF-16 | "VinlFlx" / "RectFbg" / ...    |
  | property strings ×4  | u32len + UTF-16 | "p","p","c","c" (1-char codes) |
  | extra property       | u32len + UTF-16 | "" usually; "SB" seen          |
  | zeros                | u32 ×3          | reserved                       |
  | sequence no          | u32             | draw-order index (unique >0)   |
  | zero                 | u32             |                                |
  | pad                  | u16             |                                |
  | **routed length**    | **f32**         | **feet — the home-run length** |
  | trailing constant    | f32             | per-file constant (2.0, √17,   |
  |                      |                 | 1.583…) — not per-run data     |

The extra-property string makes the tail variable: it is decoded
greedily (a u32 that reads as a small, even byte length followed by
printable UTF-16 is a string; anything else ends the string run).
Trunk/branch nodes decode with length 0 or 0.1 and are excluded from
`parse_home_run_lengths` by the parent-reference rule below.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .rup_reader import RupCursor, RupReader

logger = logging.getLogger(__name__)


# Runout lengths beyond this are mis-parses, mirroring the physicality
# guard in rup_duct_drawing_parser (§2b.5).
_MAX_PHYSICAL_LENGTH_FT = 200.0

# Property strings are short codes ("p", "c", "h", "m", "SB"). Cap the
# byte length we will accept when greedily consuming them.
_MAX_PROP_STRING_BYTES = 64


def parse_home_run_lengths(reader: RupReader) -> List[dict]:
    """Return one dict per register home-run (supply runout) with its
    routed length in feet.

    Consumer contract:
        {
          "id":         int,    # MFC object index of the DUCT node
          "label":      str,    # register label ("BATH 2-A", ...)
          "duct_code":  str,    # "VinlFlx" / "RectFbg" / "ShtMetl"
          "length_ft":  float,  # routed home-run length, feet
          "seq":        int,    # draw-order index
        }

    Trunk / branch nodes (any node whose label is referenced as a
    parent by another node, or has no label) are excluded — they are
    the tree internals, not register home-runs. Their lengths are 0 or
    a 0.1 placeholder in the corpus.

    Summing `length_ft` over the returned rows reproduces the Rheia
    3-in duct takeoff (SKU 10-00-190) footage for the project.
    """
    nodes: List[dict] = []
    for cursor in reader.find_all_tags("DUCT"):
        try:
            node = _decode_duct_node(cursor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rup_home_run: DUCT decode failed: %s", exc)
            continue
        if node:
            nodes.append(node)

    # Parent-reference rule: labels used as supply/return parent are
    # tree internals (dmn1, st1, rb1, rsb1, srs1, ...).
    parent_labels = set()
    for n in nodes:
        parent_labels.add(n["_supply_parent"])
        parent_labels.add(n["_return_parent"])
    parent_labels.discard("")

    out: List[dict] = []
    for n in nodes:
        if not n["label"] or n["label"] in parent_labels:
            continue
        if not (0.0 < n["length_ft"] <= _MAX_PHYSICAL_LENGTH_FT):
            continue
        out.append({
            "id":         n["id"],
            "label":      n["label"],
            "duct_code":  n["duct_code"],
            "length_ft":  n["length_ft"],
            "seq":        n["seq"],
        })
    logger.info("rup_home_run: %d home-run lengths decoded (%d DUCT nodes)",
                len(out), len(nodes))
    return out


def home_run_total_ft(reader: RupReader) -> float:
    """Total home-run footage — the Rheia 3-in duct (10-00-190)
    takeoff quantity. Rounded to 1 decimal; Richard's exports carry
    whole-foot totals, so callers typically round() this."""
    return round(sum(r["length_ft"] for r in parse_home_run_lengths(reader)), 1)


# ─── Internals ────────────────────────────────────────────────────

def _decode_duct_node(cursor: RupCursor) -> Optional[dict]:
    """Decode one DUCT record per the layout table above."""
    _schema       = cursor.u32()        # 13 observed
    obj_id        = cursor.u32()
    label         = cursor.utf16_string()
    supply_parent = cursor.utf16_string()   # "dmn1"
    return_parent = cursor.utf16_string()   # "rb1" / "rsb1"
    for _ in range(15):                     # design numbers (cfm, vel, ...)
        cursor.f32()
    duct_code = cursor.utf16_string()       # "VinlFlx" / "RectFbg" / ...

    # 4 fixed property strings + exactly ONE extra property string
    # ("" usually, short codes like "SB" seen). The empty case is
    # byte-identical to a zero u32; utf16_string handles both shapes
    # (u32 len, then len bytes).
    for _ in range(4):
        cursor.utf16_string()
    if _looks_like_prop_string(cursor):
        cursor.utf16_string()
    else:
        cursor.u32()    # empty extra-property string (len 0)

    # Reserved zeros ×3, then sequence, zero, u16 pad.
    for _ in range(3):
        cursor.u32()
    seq = cursor.u32()
    cursor.u32()
    cursor.skip(2)

    length_ft = cursor.f32()
    _trail    = cursor.f32()    # per-file constant, not per-run data

    return {
        "id":             obj_id,
        "label":          label,
        "_supply_parent": supply_parent,
        "_return_parent": return_parent,
        "duct_code":      duct_code,
        "length_ft":      round(length_ft, 3),
        "seq":            seq,
    }


def _looks_like_prop_string(cursor: RupCursor) -> bool:
    """True if the bytes at the cursor read as a NON-EMPTY short
    printable UTF-16 string (u32 even byte-length 2..64, ASCII body).
    Used to decide whether the extra-property field carries text or
    is the empty string (a bare zero u32)."""
    buf, pos = cursor._buf, cursor.pos
    if pos + 4 > len(buf):
        return False
    byte_len = int.from_bytes(buf[pos:pos + 4], "little")
    if byte_len == 0 or byte_len % 2 or byte_len > _MAX_PROP_STRING_BYTES:
        return False
    body = buf[pos + 4:pos + 4 + byte_len]
    if len(body) < byte_len:
        return False
    try:
        text = body.decode("utf-16-le")
    except UnicodeDecodeError:
        return False
    return all(0x20 <= ord(ch) < 0x7F for ch in text)
