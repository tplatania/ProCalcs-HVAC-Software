"""rup_ductrun_parser.py — decode DUCTRUN records (Increment 2, partial).

RUP_BINARY_FORMAT.md §2.1. Fixed 28-byte payload per record. Runs
come in id-pairs (pair_flag 0 vs 1); each pair is one physical run
with two members reflecting the drawing plane geometry.

Ships the skeleton NOW — plane-length scalar, pair grouping, drawing
width, and object ids. This is enough to enumerate the runs and pair
them structurally.

The remaining priority-2 piece (per §2.5) — resolving each pair's
DUCT DIAMETER and true CUT LENGTH via a DUCTRUN ↔ DTYPREF ↔
CSDuctOb/CRDuctOb join — is deferred until the sister session's next
spec. When that lands, this module gets an additional decoder that
turns the plane-length scalar into actual per-piece cut lengths.

Consumer contract — one dict per DUCTRUN record:

    {
      "id":         int,    # MFC object index (id-pairs step by 2)
      "pair_flag":  int,    # 0 or 1 — the two members of a run pair
      "plane_len":  float,  # drawing-plane length scalar (not a
                            # ready-to-cut linear footage — see §2.1
                            # caveat; deferred to next spec)
      "draw_width": float,  # constant 6.0 in the observed corpus
    }

Convenience: `parse_ductrun_pairs` groups the flat list into pairs
by consecutive-id + opposite pair_flag, which is the shape a
geometry-recompute consumer wants.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Tuple

from .rup_reader import RupCursor, RupReader

logger = logging.getLogger(__name__)


def parse_ductrun(reader: RupReader) -> List[dict]:
    """Return one dict per DUCTRUN record in file order (§2.1)."""
    out: List[dict] = []
    for cursor in reader.find_all_tags("DUCTRUN"):
        try:
            row = _decode_ductrun(cursor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rup_ductrun: decode failed: %s", exc)
            continue
        out.append(row)
    logger.info("rup_ductrun: %d records decoded", len(out))
    return out


def parse_ductrun_pairs(reader: RupReader) -> List[Tuple[dict, dict]]:
    """Group DUCTRUN records into (side_a, side_b) pairs.

    Per §2.1 the runs come in consecutive-id pairs (id, id+2) with
    pair_flag 0 and 1. Every valid pair produces one tuple. Orphaned
    records (no matching pair) are dropped with a warning."""
    records = parse_ductrun(reader)
    pairs: List[Tuple[dict, dict]] = []
    i = 0
    while i + 1 < len(records):
        a, b = records[i], records[i + 1]
        # Expected pattern: (a.pair_flag=0, b.pair_flag=1) with
        # b.id == a.id + 2. When it holds, group them.
        if (a["pair_flag"] == 0 and b["pair_flag"] == 1
                and b["id"] == a["id"] + 2):
            pairs.append((a, b))
            i += 2
        else:
            logger.debug("rup_ductrun: orphaned record at index %d (id=0x%X)",
                         i, a["id"])
            i += 1
    return pairs


# ─── Internals ────────────────────────────────────────────────────

def _decode_ductrun(cursor: RupCursor) -> dict:
    """§2.1 fixed 28-byte payload — schema + id + pair + plane_len
    + draw_width + 2 trailer u32s."""
    _schema     = cursor.u32()   # 2, constant across all records
    obj_id      = cursor.u32()
    pair_flag   = cursor.u32()   # 0 or 1
    plane_len   = cursor.f32()
    draw_width  = cursor.f32()   # constant 6.0 observed
    _trailer1   = cursor.u32()   # constant 2
    _trailer2   = cursor.u32()   # constant 0
    return {
        "id":         obj_id,
        "pair_flag":  pair_flag,
        "plane_len":  round(plane_len, 3),
        "draw_width": round(draw_width, 3),
    }
