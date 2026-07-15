"""rup_duct_parser.py — decode BALDUCT + DTYPREF from a .rup file.

Implements RUP_BINARY_FORMAT.md Increment 2 (§2.2-2.3). These two
record families are present in EVERY .rup — built OR un-built — so
they're the skeleton the geometry-recompute path hangs on when
RPITEM/RPRPART blocks aren't there (Ally, 13th Ave).

`BALDUCT` records are the balance table: each drawn register maps
to its Manual-D design CFM. Consumer for Richard's Duct Cuts card
(register-by-register CFM directly from the .rup, no .xls sidecar).

`DTYPREF` records are the duct-type dictionary: type_id → duct
construction code (`VinlFlx`, `RectFbg`, `ShtMetl`) plus design
parameters. Referenced by DUCTRUN records to pick each run's
construction category and therefore price.

Both parsers verified against §2.2 + §2.3 worked examples on 79th Ct:
- BALDUCT `FAM DIN KIT-C` (id 0x1FE5, cfm=131.0) — exact match.
- DTYPREF `VinlFlx` (type_id 0x166, params 900/400) — exact match.
"""

from __future__ import annotations

import logging
from typing import List

from .rup_reader import RupCursor, RupReader

logger = logging.getLogger(__name__)


def parse_baldict(reader: RupReader) -> List[dict]:
    """Return one dict per BALDUCT record: register label + design CFM.

    Consumer contract:
        {
          "id":     int,    # object index (increments by 2 per record)
          "label":  str,    # "FAM DIN KIT-C", "MASTER BEDROOM-A", ...
          "cfm":    float,  # design airflow in CFM
        }
    """
    out: List[dict] = []
    for cursor in reader.find_all_tags("BALDUCT"):
        try:
            row = _decode_balduct(cursor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rup_duct: BALDUCT decode failed: %s", exc)
            continue
        if row:
            out.append(row)
    logger.info("rup_duct: %d BALDUCT records decoded", len(out))
    return out


def parse_dtypref(reader: RupReader) -> List[dict]:
    """Return one dict per DTYPREF record: duct-type dictionary entry.

    Consumer contract:
        {
          "type_id":  int,    # joined by runs/registers
          "code":     str,    # "VinlFlx" (vinyl flex), "RectFbg"
                              # (rectangular fiberglass), "ShtMetl"
                              # (sheet metal)
          "param_a":  float,  # design bound (usually max CFM)
          "param_b":  float,  # design bound
        }
    """
    out: List[dict] = []
    for cursor in reader.find_all_tags("DTYPREF"):
        try:
            row = _decode_dtypref(cursor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rup_duct: DTYPREF decode failed: %s", exc)
            continue
        if row:
            out.append(row)
    logger.info("rup_duct: %d DTYPREF records decoded", len(out))
    return out


# ─── Internals ────────────────────────────────────────────────────

def _decode_balduct(cursor: RupCursor) -> dict:
    """§2.2 layout — schema u32, id u32, label utf16, cfm f32."""
    schema = cursor.u32()
    obj_id = cursor.u32()
    label  = cursor.utf16_string()
    cfm    = cursor.f32()
    return {
        "id":    obj_id,
        "label": label,
        "cfm":   round(cfm, 2),
    }


def _decode_dtypref(cursor: RupCursor) -> dict:
    """§2.3 layout — schema u32, type_id u32, code utf16, param_a f32,
    param_b f32."""
    schema  = cursor.u32()
    type_id = cursor.u32()
    code    = cursor.utf16_string()
    param_a = cursor.f32()
    param_b = cursor.f32()
    return {
        "type_id": type_id,
        "code":    code,
        "param_a": round(param_a, 2),
        "param_b": round(param_b, 2),
    }
