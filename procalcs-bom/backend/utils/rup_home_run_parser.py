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

MOUNT TYPE (ceiling / high-sidewall / pass-through), decoded
2026-07-16: the boot mount is NOT in the DUCT record. It lives in the
register drawing objects (`CSRegOb` region): each drawn register is
followed by a `DREGPERF` block that — when the register is on a Rheia
system — carries the marker string "RHEA" and then the LITERAL Rheia
boot SKU the takeoff will emit for that register:

  | field         | type            | value                            |
  |---------------|-----------------|----------------------------------|
  | schema        | u32             | 2                                |
  | object id     | u32             |                                  |
  | system tag    | u32len + UTF-16 | "RHEA" (empty on return grilles) |
  | ints ×3       | u32             | 0, 1, 1 observed                 |
  | design number | f64             | per-register CFM-derived scalar  |
  | **boot SKU**  | u32len + UTF-16 | "10-01-220" ceiling boot         |
  |               |                 | "10-01-200" high-sidewall boot   |
  |               |                 | "10-01-210" pass-through boot    |

The register's LABEL (matching the DUCT runout label, suffixes
included: "FOYER-B", "KIT-A/GREAT/DIN-E") is the nearest CString
envelope `CD CD BA FF FE FF <len:u8> <UTF-16 ×len>` preceding the
DREGPERF tag inside the same register object.

Validated against the full 2026-07-15 corpus (1,076 rup/xls pairs
with boot counts): per-SKU counts reproduce the xls exactly on 92.6%
of pairs (ceiling 96.8% / sidewall 94.6% / pass-through 97.2%);
misses are rup-vs-xls revision skew, the same failure mode as the
footage check above. Label join: 100% of RHEA registers labeled and
matched to runout labels on a 30-pair random sample (959/959).

Historical note: the DREGINFO enum (offset +0x20) distinguishes
ceiling (11) from wall (4) registers exactly, but NOT sidewall vs
pass-through — those two are byte-identical everywhere except the
DREGPERF SKU. The 'SB' extra property and the FITNG group-4 codes
("4W"/"4AD"/"4P") were both ruled out as mount signals.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .rup_reader import RupCursor, RupReader

logger = logging.getLogger(__name__)


# Runout lengths beyond this are mis-parses, mirroring the physicality
# guard in rup_duct_drawing_parser (§2b.5).
_MAX_PHYSICAL_LENGTH_FT = 200.0

# Property strings are short codes ("p", "c", "h", "m", "SB"). Cap the
# byte length we will accept when greedily consuming them.
_MAX_PROP_STRING_BYTES = 64

# Rheia boot SKU → mount type, per the DREGPERF table in the module
# docstring. These are the three boot assemblies the Rheia takeoff
# emits (xls lines 10-01-220 / 10-01-200 / 10-01-210).
_MOUNT_BY_SKU = {
    "10-01-220": "ceiling",
    "10-01-200": "sidewall",
    "10-01-210": "pass_through",
}

# CString envelope that precedes the register label inside the CSRegOb
# instance: CD CD BA (MFC field separator) + FF FE FF (CString prefix)
# + u8 char count + UTF-16LE chars.
_REG_LABEL_ENVELOPE = b"\xcd\xcd\xba\xff\xfe\xff"

# How far back (bytes) to scan for the register label envelope from
# the DREGPERF tag. The label sits ~150-400 bytes before the tag in
# the corpus; 3000 gives slack without crossing into the previous
# register object's DREGPERF.
_REG_LABEL_WINDOW = 3000


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
          "mount":      str,    # "ceiling" | "sidewall" |
                                # "pass_through" | "unknown"
        }

    `mount` is joined by label from the register DREGPERF records
    (see module docstring). "unknown" when the register carries no
    Rheia SKU (non-Rheia projects) or the label is missing/ambiguous.

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

    mount_by_label = _mounts_by_label(reader)

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
            "mount":      mount_by_label.get(n["label"], "unknown"),
        })
    logger.info("rup_home_run: %d home-run lengths decoded (%d DUCT nodes)",
                len(out), len(nodes))
    return out


def home_run_total_ft(reader: RupReader) -> float:
    """Total home-run footage — the Rheia 3-in duct (10-00-190)
    takeoff quantity. Rounded to 1 decimal; Richard's exports carry
    whole-foot totals, so callers typically round() this."""
    return round(sum(r["length_ft"] for r in parse_home_run_lengths(reader)), 1)


def parse_register_mounts(reader: RupReader) -> List[dict]:
    """One dict per Rheia supply register, from the DREGPERF records
    in the register drawing objects:

        {
          "label": Optional[str],  # register label ("FOYER-B", ...)
          "mount": str,            # "ceiling"|"sidewall"|"pass_through"
          "sku":   str,            # the literal Rheia boot SKU
        }

    Registers whose DREGPERF has no "RHEA" tag or no boot SKU
    (return grilles, non-Rheia projects) are omitted. This is the
    exact per-register source of the xls boot lines 10-01-2xx.
    """
    buf = reader._buf  # noqa: SLF001 — same-package structural access
    out: List[dict] = []
    for cursor in reader.find_all_tags("DREGPERF"):
        tag_pos = cursor.pos
        try:
            cursor.u32()                      # schema (2)
            cursor.u32()                      # object id
            if cursor.utf16_string() != "RHEA":
                continue                      # return grille / non-Rheia
            for _ in range(3):                # ints 0, 1, 1
                cursor.u32()
            cursor.f64()                      # design number
            sku = cursor.utf16_string()
        except Exception as exc:  # noqa: BLE001
            logger.warning("rup_home_run: DREGPERF decode failed: %s", exc)
            continue
        mount = _MOUNT_BY_SKU.get(sku)
        if mount is None:
            continue
        out.append({
            "label": _register_label_before(buf, tag_pos),
            "mount": mount,
            "sku":   sku,
        })
    logger.info("rup_home_run: %d register mounts decoded", len(out))
    return out


def mount_counts(reader: RupReader) -> Dict[str, int]:
    """Boot-assembly counts by mount type — reproduces the Rheia BOM
    xls quantities for 10-01-220 (ceiling), 10-01-200 (sidewall) and
    10-01-210 (pass_through). Counted directly from the register
    DREGPERF records, so it matches the takeoff even when a runout
    label fails to join."""
    counts = {"ceiling": 0, "sidewall": 0, "pass_through": 0}
    for reg in parse_register_mounts(reader):
        counts[reg["mount"]] += 1
    return counts


# ─── Internals ────────────────────────────────────────────────────

def _mounts_by_label(reader: RupReader) -> Dict[str, str]:
    """label → mount for every labeled Rheia register. A label that
    appears with CONFLICTING mounts maps to "unknown" (never observed
    in the corpus — labels carry per-register suffixes — but cheap to
    guard)."""
    by_label: Dict[str, str] = {}
    for reg in parse_register_mounts(reader):
        label = reg["label"]
        if not label:
            continue
        if label in by_label and by_label[label] != reg["mount"]:
            by_label[label] = "unknown"
        else:
            by_label.setdefault(label, reg["mount"])
    return by_label


def _register_label_before(buf: bytes, tag_pos: int) -> Optional[str]:
    """The register label is the nearest preceding CString envelope
    `CD CD BA FF FE FF <len:u8> <UTF-16LE ×len>` inside the register
    object (see module docstring). Returns None when no printable
    candidate exists in the window."""
    start = max(0, tag_pos - _REG_LABEL_WINDOW)
    hit = buf.rfind(_REG_LABEL_ENVELOPE, start, tag_pos)
    while hit >= 0:
        char_len = buf[hit + 6]
        if 2 <= char_len <= 40:
            raw = buf[hit + 7: hit + 7 + 2 * char_len]
            try:
                text = raw.decode("utf-16-le")
            except UnicodeDecodeError:
                text = ""
            if text and all(0x20 <= ord(ch) < 0x7F for ch in text):
                return text
        if hit == 0:
            break
        hit = buf.rfind(_REG_LABEL_ENVELOPE, start, hit - 1)
    return None

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
