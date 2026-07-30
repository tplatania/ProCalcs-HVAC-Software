"""rup_annotations.py — Day-30: equipment-relevant drawing annotations.

Richard (Jappeloup Lane): "Dehumidifiers — not read. These need to be
manually added." Root cause: the dehumidifier exists in that file ONLY
as canvas text the designer typed ("Dehumidifier", "Supply
dehumidified air to Supply Plenum") — no equipment record, no model,
no part number anywhere in the binary. No parser can conjure a BOM
line from a text label, but silently ignoring it is worse: the
reviewer thinks the tool missed equipment.

This module scans the drawing text for equipment-relevant keywords and
surfaces the matching annotations so the BOM can say "the drawing
notes mention a dehumidifier — add the model via the assistant."

Extraction: MFC CStrings use the FF FE FF <len> envelope for UTF-16
strings (same convention the drawing parser decodes). We scan the
whole file for that envelope and keyword-filter the decoded strings —
robust to where the annotation object lives.
"""

from __future__ import annotations

import logging
import re
from typing import List

logger = logging.getLogger("procalcs_bom")

# Keywords that indicate equipment the BOM pipeline can't extract as
# records. Deliberately tight — annotations are noisy.
_KEYWORDS = re.compile(
    r"dehumidif|humidif|\bERV\b|\bHRV\b|ventilator|fresh\s*air|"
    r"UV\s*(?:light|lamp)|air\s*(?:cleaner|purifier)",
    re.IGNORECASE,
)

# FF FE FF <len:u8> then len UTF-16LE chars (Wrightsoft CString long-form).
_CSTRING = re.compile(rb"\xff\xfe\xff([\x05-\x60])")


def extract_equipment_annotations(data: bytes, cap: int = 20) -> List[str]:
    """Return deduped, keyword-matching annotation strings from the
    drawing, order of first appearance, capped."""
    out: List[str] = []
    seen = set()
    for m in _CSTRING.finditer(data):
        n = m.group(1)[0]
        start = m.end()
        raw = data[start:start + n * 2]
        if len(raw) < n * 2:
            continue
        try:
            s = raw.decode("utf-16-le")
        except UnicodeDecodeError:
            continue
        if not s.isprintable():
            continue
        if _KEYWORDS.search(s):
            key = s.strip().lower()
            if key not in seen:
                seen.add(key)
                out.append(s.strip())
                if len(out) >= cap:
                    break
    if out:
        logger.info("rup_annotations: %d equipment-relevant drawing notes", len(out))
    return out
