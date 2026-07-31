"""
rup_register_preflight.py — Day-31: register grille-size pre-flight.

Decoded from accumulated data (designer-desktop
docs/rup-dreginfo-decode.md): each DREGINFO block stores the register
grille size as two f64s (width @+12, height @+20, inches) plus a size
MODE u32 @+8 — 1 = auto/default-sized (Wrightsoft stores the literal
default, 12x12), 2 = user-specified. Auto records are exactly the ones
that land in a built BOM as the default SKU (the FRGRMFT-1212 lump).

Ground truth: Jappeloup (Richard's plan count — user-set histogram
matches exactly), cross-validated on SW55 / Irvine / 79th Ct / Clarke /
Enos; corpus sample 120 files: 62% of records auto, 0 files fully
user-set.

The true size of an auto record is genuinely NOT in the file, so this
module only ever FLAGS — it never guesses a size (expert-ratified
flag-don't-guess policy).
"""
from __future__ import annotations

import struct
from collections import Counter

from .rup_reader import RupReader

_MODE_AUTO = 1
_MODE_USER = 2


def extract_register_preflight(file_bytes: bytes) -> dict | None:
    """Auto-vs-user grille-size stats for every DREGINFO record.

    Returns None when the file has no DREGINFO records (nothing to
    pre-flight). Size keys are "WxH" with ints when whole ("12x12").
    """
    reader = RupReader(file_bytes)
    auto: Counter[str] = Counter()
    user: Counter[str] = Counter()
    for cur in reader.find_all_tags("DREGINFO"):
        pos = cur.pos
        try:
            mode = struct.unpack_from("<I", file_bytes, pos + 8)[0]
            w = struct.unpack_from("<d", file_bytes, pos + 12)[0]
            h = struct.unpack_from("<d", file_bytes, pos + 20)[0]
        except struct.error:
            continue
        if not (0 < w < 200 and 0 < h < 200):  # sanity: inches
            continue
        key = f"{w:g}x{h:g}"
        if mode == _MODE_USER:
            user[key] += 1
        elif mode == _MODE_AUTO:
            auto[key] += 1
    total = sum(auto.values()) + sum(user.values())
    if not total:
        return None
    return {
        "auto_count": sum(auto.values()),
        "user_count": sum(user.values()),
        "total": total,
        "auto_sizes": dict(auto.most_common()),
        "user_sizes": dict(user.most_common()),
    }
