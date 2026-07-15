"""rup_duct_geometry.py — per-segment duct geometry (Increment 2b).

Wraps rup_duct_drawing_parser per §2b's key reframe: no DUCTRUN →
drawing-object join is needed for the Duct Cuts list — each drawing
object (CSDuctOb / CRDuctOb) already carries both size AND
endpoints. This module is the feature-gate layer that upstream code
(bom_from_rup.py) calls to decide whether to emit per-piece cut data.

Empirical probe today (2026-07-09) confirms:
  * CSDuctOb and CRDuctOb classes exist at file offsets 0x25EA01 and
    0x2667C9 in 79th Ct+BOM (each declared once via MFC `FF FF`
    pattern followed by class name).
  * Standard duct diameters (4"-20") do NOT appear as f32 values in
    the CSDuctOb region — diameters must be encoded differently
    (indexed into a table, stored as u32 inches, or embedded in a
    packed drawing property).
  * DTYPREF type_ids (0x166, 0x167, 0x168...) do NOT appear as u32
    values in the CSDuctOb region either — the join key isn't a
    direct type_id reference.
  * DUCTRUN pair statistics show a consistent b/a ratio ≈ 0.55
    across the 86 non-zero pairs, suggesting side_a is a drawn
    length and side_b is a derived value, but the physical
    interpretation requires structural knowledge we don't have yet.

Sister session's Ghidra pass on RSU.EXE `Serialize()` call sites is
the safe path to real decode. Static empirical inference alone would
be speculation.

Consumer contract when live — one dict per duct run:

    {
      "run_id":         int,     # DUCTRUN side_a id (pair anchor)
      "diameter_in":    float,   # nominal diameter (round duct) or
                                 # equivalent hydraulic diameter (rect)
      "cut_length_ft":  float,   # real linear footage, ready for BOM
      "type_code":      str,     # "VinlFlx" / "RectFbg" / "ShtMetl"
      "type_id":        int,     # DTYPREF join key for pricing/rules
    }

Integration site: `bom_from_rup.py` calls `join_duct_geometry(reader)`
after `parse_ductrun` — when this returns non-empty, the un-built
geometry-recompute path uses these rows to synthesize per-code duct
lines and the "build first" UX guardrail becomes silent.
"""

from __future__ import annotations

import logging
from typing import List

from .rup_reader import RupReader
from .rup_duct_drawing_parser import parse_duct_segments

logger = logging.getLogger(__name__)


def join_duct_geometry(reader: RupReader) -> List[dict]:
    """Return per-segment duct geometry rows per §2b.4's contract.

    Each drawing-object instance (CSDuctOb = supply, CRDuctOb =
    return) produces one row with run_id, shape, size (round vs
    rect), and cut_length_ft. §2b confirmed no DUCTRUN join needed —
    each drawing object is self-contained on size + endpoints.
    """
    return parse_duct_segments(reader)


def is_geometry_join_available() -> bool:
    """Consumer-side feature check. True as of Increment 2b delivery
    on 2026-07-10. Kept as a flag so a future spec revision can
    gate the path without touching every call site."""
    return True
