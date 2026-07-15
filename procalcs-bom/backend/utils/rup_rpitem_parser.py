"""rup_rpitem_parser.py — decode RPITEM + RPRPART pairs from a
built-BOM .rup file.

Implements RUP_BINARY_FORMAT.md Increment 1 (§1.1-1.6). Every priced
BOM line inside a Wrightsoft `.rup` (once the designer has run "Bill
of Materials → save") is stored as an RPITEM + RPRPART pair. This
module walks those pairs and emits the standard line-item dicts our
BOM pipeline consumes.

The RPITEM record carries quantity + extended prices + units +
category label. The paired RPRPART record carries the catalog
snapshot: category code, part source, part number, description, unit
prices, datasheet refs.

Filter rule (§1.6): a valid BOM line has an RPRPART part_no matching
`^[A-Z]{2,}[A-Za-z]*-?\\d`. Pairs whose RPRPART has no such part_no
are the 9 report/summary rows (section headers, subtotals, tax
footer) — Wrightsoft's BOM report structure, not catalog line items.
On 79th Ct+BOM this drops 9 rows and yields 147 real priced lines.

Consumer contract — one dict per line:

    {
      "part_no":       str,   # "DDVn08", "FTOB-8", ...
      "part_source":   str,   # "WSF" (joins to RPRUWSF.mdb PartSource)
      "category_code": str,   # "WSFDCT", "WSFFTR", or "" (see NOTE)
      "quantity":      float, # 73.0
      "unit_price":    float, # 1.80
      "extended":      float, # 131.40 (may lag qty*unit if line has
                              # discount/margin overrides — trust
                              # extended, not the multiply)
      "units":         str,   # "ea"
      "category_label":str,   # "Duct System Equipment" (always populated)
      "description":   str,   # "Round vinyl duct, D = 8\""
      "cost_unit":     float, # cost basis (may equal unit_price)
      "sell_unit":     float, # sell price (may equal unit_price)
    }

NOTE — empty category_code: Wrightsoft populates category_code only on
part copies that appear across ALL investments in the project. Parts
that only appear in some investments (design variants) get an empty
category_code on those copies. category_label is always populated —
use it for display grouping. Only use category_code when joining back
to RPRUWSF.mdb.ActCateg for pricing rules — which is unnecessary
because RPRPART already carries priced values directly.
"""

from __future__ import annotations

import logging
import re
from typing import Iterator, List, Optional

from .rup_reader import RupCursor, RupReader

logger = logging.getLogger(__name__)


# §1.6 — filter regex. Part numbers look like "DDVn08", "FTOB-8",
# "FRRTR-1806-1006", "FBEC-1210", etc. Report rows have no part_no.
_PART_NO_RE = re.compile(r"^[A-Z]{2,}[A-Za-z]*-?\d")


def has_priced_bom(reader: RupReader) -> bool:
    """Return True when the file contains at least one real priced
    RPITEM/RPRPART pair (post §1.6 filter).

    Un-built .rup files may contain a handful of RPITEM/RPRPART
    tag pairs even without a built BOM — those decode to report
    rows (section headers, subtotals) with empty part_no fields.
    Ally has 9 such tag pairs but zero priced lines. This function
    distinguishes real content ("BOM was built and saved") from
    the empty report scaffold that survives in un-built files."""
    for part_cursor in reader.find_all_tags("RPRPART"):
        part_cursor.u32(); part_cursor.u32()
        part_cursor.utf16_string()  # category
        part_cursor.utf16_string()  # psrc
        part_no = part_cursor.utf16_string()
        if _PART_NO_RE.match(part_no or ""):
            return True
    return False


def parse_priced_lines(reader: RupReader) -> List[dict]:
    """Walk every RPITEM/RPRPART pair, apply the §1.6 filter, and
    return the priced line items in file order.

    Pairs are emitted in the order they appear in the file (which is
    the order Wrightsoft groups them in the BOM report). Report rows
    (RPRPART with no valid part_no per _PART_NO_RE) are dropped."""
    lines: List[dict] = []
    skipped = 0
    for item_cursor, part_cursor in zip(
        reader.find_all_tags("RPITEM"),
        reader.find_all_tags("RPRPART"),
    ):
        try:
            line = _decode_pair(item_cursor, part_cursor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rup_rpitem: pair decode failed: %s", exc)
            continue
        if line is None:
            skipped += 1
            continue
        lines.append(line)
    logger.info("rup_rpitem: %d priced lines emitted (%d report rows skipped)",
                len(lines), skipped)
    return lines


# ─── Internals ────────────────────────────────────────────────────

def _decode_pair(item: RupCursor, part: RupCursor) -> Optional[dict]:
    """Decode one RPITEM + RPRPART pair.

    Each cursor arrives positioned AT the end of its tag-body — ready
    to read the first payload field per the block's layout. Returns
    None when the RPRPART has no valid part_no (§1.6 filter — report
    rows). Field order matches RUP_BINARY_FORMAT.md §1.1 and §1.2,
    with the empirical adjustment that intermediate zero-valued u32
    fields between the doc's named fields must be consumed to keep
    the cursor aligned to the stream (CArchive has no alignment
    padding per Increment 4)."""

    # ── RPITEM fields (§1.1) ─────────────────────────────────────
    item_schema = item.u32()     # expect 3
    item_flags  = item.u32()     # sequence number (observed empirically)
    parent_idx  = item.i32()     # expect -1 for top-level lines
    quantity    = item.f64()     # authoritative
    _qty_dup    = item.f64()     # duplicate quantity ("ordered vs actual")
    # 20 bytes of padding / zero-valued u32s per §1.1's "+0x36 mixed" note
    item.skip(20)
    extended_list = item.f64()   # 73 × 1.80 = 131.40 for DDVn08
    extended_sell = item.f64()   # equal to list when no markup
    # Two zero-valued f64s (discount, margin) between ext_sell and
    # units per empirical byte trace on 79th Ct. Doc §1.1 says
    # "discount / margin / tax f64…" without a size, but observed
    # layout is 2 fields = 16 bytes.
    item.skip(16)
    units          = item.utf16_string()   # "ea"
    category_label = item.utf16_string()   # "Duct System Equipment"
    # Some pairs carry a trailing zone label (e.g. "AHU - 1"). Don't
    # consume it — we don't need it, and reaching !END=RPITEM ends
    # the block anyway.

    # ── RPRPART fields (§1.2) ────────────────────────────────────
    part_schema = part.u32()     # expect 6
    part_flags  = part.u32()     # sequence
    category    = part.utf16_string()   # "WSFDCT" / "WSFFTR" / ...
    psrc        = part.utf16_string()   # "WSF"
    part_no     = part.utf16_string()   # "DDVn08"

    # §1.6 filter — report rows have no valid part_no.
    if not _PART_NO_RE.match(part_no or ""):
        return None

    # link/blank + two zero-length strings observed empirically
    _link = part.utf16_string()
    _z1   = part.utf16_string()
    _z2   = part.utf16_string()
    description = part.utf16_string()

    # pkg_mult f64, then 3 u32 zeros, then list_price f64.
    # Layout confirmed against §1.2 offsets (pkg at +0xaa, list at +0xbe).
    _pkg_mult = part.f64()
    part.skip(12)
    list_price = part.f64()
    # 16 bytes of zero fields (4 u32s) between list and sell per §1.2
    # gap layout (+0xd6 - +0xbe = 0x18 - 8 = 16).
    part.skip(16)
    sell_price = part.f64()
    # 8 bytes of zero fields (2 u32s) between sell and cost (+0xe6 -
    # +0xd6 = 0x10 - 8 = 8).
    part.skip(8)
    cost_price = part.f64()

    return {
        "part_no":        part_no,
        "part_source":    psrc,
        "category_code":  category,
        "quantity":       quantity,
        "unit_price":     list_price,
        "extended":       extended_list,
        "units":          units,
        "category_label": category_label,
        "description":    description,
        "cost_unit":      cost_price,
        "sell_unit":      sell_price,
    }
