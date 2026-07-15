"""rup_equip_parser.py — decode placed equipment instances from EQUIP blocks.

Implements RUP_BINARY_FORMAT.md Increment 3 (§3.1-3.3). Every EQUIP
block shares `schema = 11` — both catalog templates AND placed
instances live in the same block type. The discriminator (§3.2) is
whether the block carries the full manufacturer-triplet + model-pair
signature:

  Template:     equipment_type + display_manufacturer only.
  Placed unit:  equipment_type + drawing_tag + display_mfr +
                catalog_key_mfr + source_code + condenser + coil.

Placed instances answer the "what equipment is on this job" question
Wrightsoft's BOM display shows. Retires the day-18 mfr-double-marker
heuristic (which was reacting to Wrightsoft's three-way manufacturer
notation Trane/TRANE/TRAN) and the day-17 free-standing model scan.

FIXES ALLY "0 EQUIPMENT" BUG: Ally's two Trane heat-pump systems and
BAYEA backup heat kits ARE in the file — sitting in EQUIP blocks
that the old aligned reader skipped because the string fields start
at odd absolute offsets. Structural walk finds them cleanly.

Consumer contract — one dict per placed instance:

    {
      "equipment_type":   str,   # "Split ASHP", "Elec strip", ...
      "drawing_tag":      str,   # "RCU-A-CB" (drawing placement tag)
      "manufacturer":     str,   # "Trane"   (display name)
      "mfr_catalog_key":  str,   # "TRANE"   (uppercase, catalog key)
      "part_source":      str,   # "TRAN"    (4-char PSrc code, joins RPRUWSF)
      "condenser_model":  str,   # "5TTV0X60A1"
      "coil_model":       str,   # "5TAMXD07AV51"
    }

Accessory/heat-strip records that fit the placed-instance signature
but only carry a single model (no matched pair) are still emitted
with the model in condenser_model and coil_model empty.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .rup_reader import RupCursor, RupReader

logger = logging.getLogger(__name__)


def parse_equipment(reader: RupReader) -> List[dict]:
    """Walk every EQUIP block, emit one dict per unique placed instance
    (per §3.2 signature). Templates are dropped silently. Multi-
    investment copies of the same placement are deduped by
    (equipment_type, condenser_model, coil_model) — Wrightsoft stores
    each placement once per investment (up to 4×) but the BOM display
    treats them as one physical unit."""
    seen_keys = set()
    out: List[dict] = []
    dropped_templates = 0
    for cursor in reader.find_all_tags("EQUIP"):
        try:
            row = _decode_equip(cursor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rup_equip: block decode failed: %s", exc)
            continue
        if row is None:
            dropped_templates += 1
            continue
        key = (row.get("equipment_type"),
               row.get("condenser_model"),
               row.get("coil_model"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(row)
    logger.info("rup_equip: %d unique placed instances "
                "(%d templates dropped, dedup applied)",
                len(out), dropped_templates)
    return out


def _decode_equip(cursor: RupCursor) -> Optional[dict]:
    """Decode one EQUIP block per §3.1's empirical layout.

    Byte layout (verified against RCU-A-CB at file 0x151821):
      +0x00  schema u32       = 11
      +0x04  object id u32
      +0x08  category/role u32
      +0x0C  4 bytes zero pad (doc §3.1 doesn't name this)
      +0x10  equipment_type utf16_string
      +next  drawing_tag utf16_string
      +next  display_manufacturer utf16_string
      +next  mfr_catalog_key utf16_string
      +next  part_source_code utf16_string
      +next  condenser_model utf16_string
      +next  coil_model utf16_string

    §3.2 discriminator — a placed instance carries BOTH:
      1. the manufacturer key + source_code pair
         (mfr_catalog_key non-empty AND part_source non-empty), AND
      2. at least the condenser_model (accessory/heat-strip records
         only have one model; systems have condenser + coil).

    Templates (catalog rows) lack the key/source pair, or lack the
    model, and are dropped.
    """
    schema = cursor.u32()
    if schema != 11:
        return None  # not a real EQUIP block
    _obj_id = cursor.u32()
    _flag   = cursor.u32()
    cursor.skip(4)                                # unnamed zero pad
    equipment_type   = cursor.utf16_string()
    drawing_tag      = cursor.utf16_string()
    display_mfr      = cursor.utf16_string()
    mfr_catalog_key  = cursor.utf16_string()
    part_source      = cursor.utf16_string()
    condenser_model  = cursor.utf16_string()
    coil_model       = cursor.utf16_string()

    # §3.2 placed-instance signature — refined empirically per Ally
    # BAYEA blocks: accessories (heat strips) have the mfr key + model
    # but NO part_source code. Systems (Trane split AC/HP) have all
    # three. So the discriminator is "has manufacturer key + has model".
    # Empty model = template (catalog row, not placed).
    if not mfr_catalog_key:
        return None  # not a real placed record (no resolved mfr)
    if not condenser_model:
        return None  # template — no resolved model
    return {
        "equipment_type":   equipment_type or None,
        "drawing_tag":      drawing_tag or None,
        "manufacturer":     display_mfr or None,
        "mfr_catalog_key":  mfr_catalog_key,
        "part_source":      part_source,
        "condenser_model":  condenser_model,
        "coil_model":       coil_model or None,
    }
