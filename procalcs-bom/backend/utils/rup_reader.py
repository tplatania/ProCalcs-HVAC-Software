"""rup_reader.py — cursor-based reader for Wrightsoft `.rup` binary.

Implements the CArchive walker rule from RUP_BINARY_FORMAT.md §0.3 + §4:
MFC's `CArchive::operator<<` packs fields back-to-back with NO alignment
padding. A reader must advance the cursor by exact field width, never
seek to an alignment boundary. A field's absolute parity is arbitrary —
in the worked corpus, string bodies start at odd offsets 200× more
often than even.

This module is the shared foundation for every structural parser:
`RPITEM`/`RPRPART` (Increment 1), `EQUIP` placed-instance (Increment 3),
`DUCTRUN`/`BALDUCT`/`DTYPREF` (Increment 2). Each higher-level parser
uses these primitives instead of re-implementing the walk.

Design:

  reader = RupReader(mmap_or_bytes)
  for cursor in reader.find_all_tags("RPITEM"):
      # cursor sits AFTER the `!BEG=RPITEM` tag string. Field-order
      # per §1.1: u32 schema, u32 flags, i32 group_idx, f64 quantity,
      # f64 quantity_dup, 20 bytes padding/int, f64 ext_list, f64
      # ext_sell, ..., then u32-len units, u32-len category.
      schema  = cursor.u32()
      flags   = cursor.u32()
      parent  = cursor.i32()
      qty     = cursor.f64()

Two lookup modes provided:

  find_all_tags(name)     — iterate every `!BEG=<name>` position in
                            file order. Suitable for block-counted
                            scans (RPITEM×156, EQUIP×368, etc.).
  find_first_tag(name)    — return the first hit, or None.

Cursor operations: u32/i32/f32/f64/utf16_string and skip(n). Never
seek to alignment. The higher-level parser is responsible for knowing
the field order — this module only advances by exact widths.
"""

from __future__ import annotations

import struct
from typing import Iterator, Optional


# ─── Constants ─────────────────────────────────────────────────────

# UTF-16LE encoding of "!BEG=" and "!END=" — 10 bytes each (5 ASCII
# chars × 2 bytes). Used by the tag scanner. The prefix 5 chars are
# constant across all block names; suffixes vary.
_UTF16_BEG_PREFIX = "!BEG=".encode("utf-16-le")
_UTF16_END_PREFIX = "!END=".encode("utf-16-le")


# ─── Primitive struct formats (little-endian, no alignment) ────────

_U32 = struct.Struct("<I")
_I32 = struct.Struct("<i")
_F32 = struct.Struct("<f")
_F64 = struct.Struct("<d")


class RupCursor:
    """Position-tracked reader over a bytes buffer. All operations
    advance by exact field width per Increment 4's rule."""

    __slots__ = ("_buf", "pos")

    def __init__(self, buf: bytes, pos: int = 0):
        self._buf = buf
        self.pos = pos

    def __repr__(self) -> str:
        return f"RupCursor(pos=0x{self.pos:X})"

    def remaining(self) -> int:
        return len(self._buf) - self.pos

    def eof(self) -> bool:
        return self.pos >= len(self._buf)

    # ── Primitive reads ──────────────────────────────────────────

    def u32(self) -> int:
        v = _U32.unpack_from(self._buf, self.pos)[0]
        self.pos += 4
        return v

    def i32(self) -> int:
        v = _I32.unpack_from(self._buf, self.pos)[0]
        self.pos += 4
        return v

    def f32(self) -> float:
        v = _F32.unpack_from(self._buf, self.pos)[0]
        self.pos += 4
        return v

    def f64(self) -> float:
        v = _F64.unpack_from(self._buf, self.pos)[0]
        self.pos += 8
        return v

    def skip(self, n: int) -> None:
        """Advance cursor by n bytes without decoding. Used to step
        past known-shape padding described in the byte-offset tables
        (e.g. RPITEM's 20-byte int/zero-pad region at +0x36)."""
        self.pos += n

    def utf16_string(self) -> str:
        """Read a length-prefixed UTF-16LE string.

        Wire format (per §0.3):
            <u32 byte_len><UTF-16LE bytes>
        The byte_len is the count of BYTES that follow (not chars).
        Char count is byte_len // 2.

        Empty strings (byte_len == 0) return "". Well-formed CArchive
        writes complete pairs, so an odd byte_len is treated as a
        soft error — we still advance by byte_len bytes and decode
        best-effort so the cursor stays aligned to the field stream.
        """
        byte_len = self.u32()
        if byte_len == 0:
            return ""
        raw = self._buf[self.pos:self.pos + byte_len]
        self.pos += byte_len
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError:
            # Odd byte_len or invalid surrogates — return partial text,
            # keep cursor advancement consistent.
            return raw.decode("utf-16-le", errors="replace")

    # ── Bookmark / rewind ────────────────────────────────────────

    def snapshot(self) -> int:
        return self.pos

    def restore(self, pos: int) -> None:
        self.pos = pos


class RupReader:
    """High-level facade over the full .rup bytes.

    Handles header skip and provides tag-scan iterators. Higher-level
    parsers construct one RupReader per file, iterate the tags they
    care about, and pass each returned cursor down to their record
    decoder."""

    def __init__(self, data: bytes):
        self._buf = data
        self._body_start = _find_body_start(data)

    @property
    def body_start(self) -> int:
        """Byte offset where the CArchive binary body begins — right
        after the plain-text UTF-16LE header (per §0.1). 79th Ct: 0x0E9."""
        return self._body_start

    def find_all_tags(self, block_name: str,
                      kind: str = "BEG") -> Iterator[RupCursor]:
        """Yield one cursor per `!BEG=<block_name>` (or `!END=`) occurrence
        in file order. Cursor sits AT the u32 length prefix of the NEXT
        field after the tag string — i.e., ready to read the first
        payload field per the block's byte-offset table."""
        tag_body_utf16 = f"!{kind}={block_name}".encode("utf-16-le")
        expected_byte_len = len(tag_body_utf16)
        expected_byte_len_bytes = _U32.pack(expected_byte_len)

        # Scan for the tag body directly; back up 4 to verify the
        # length prefix. A false-positive at this level would require
        # the tag string to appear as data — unlikely because "!BEG="
        # and "!END=" are Wrightsoft-reserved control tokens.
        scan_pos = self._body_start
        while True:
            hit = self._buf.find(tag_body_utf16, scan_pos)
            if hit < 0:
                return
            len_prefix_pos = hit - 4
            if (len_prefix_pos >= self._body_start
                    and self._buf[len_prefix_pos:hit] == expected_byte_len_bytes):
                # Cursor points at the byte immediately after the
                # tag body — ready for the block's first field.
                yield RupCursor(self._buf, hit + expected_byte_len)
                # Advance past this hit so we don't re-match it. Use
                # end-of-tag; the next tag can't overlap with the
                # length prefix we just verified.
                scan_pos = hit + expected_byte_len
            else:
                # False positive on the string content — advance by 2
                # (UTF-16 char width) and keep looking.
                scan_pos = hit + 2

    def find_first_tag(self, block_name: str,
                       kind: str = "BEG") -> Optional[RupCursor]:
        for cursor in self.find_all_tags(block_name, kind):
            return cursor
        return None

    def count_tags(self, block_name: str, kind: str = "BEG") -> int:
        return sum(1 for _ in self.find_all_tags(block_name, kind))

    def cursor_at(self, pos: int) -> RupCursor:
        """Get a cursor positioned at an absolute file offset. Used by
        tests and by parsers that already know a specific record
        offset (§1.1 worked example: RPITEM 'DDVn08' at 0x552E79)."""
        return RupCursor(self._buf, pos)


# ─── Header handling ───────────────────────────────────────────────

def _find_body_start(buf: bytes) -> int:
    """Return the byte offset where the CArchive body begins.

    §0.1: the file starts with a plain-text UTF-16LE header terminated
    by `\\r\\n\\r\\n`. 79th Ct puts the body at 0x0E9. Fall back to 0 if
    the header terminator isn't found (defensive — every real file
    should have one).

    Day-22: the search is bounded to the first 8 KiB and the hit must
    be UTF-16 aligned. Reliable's archive has files with NO double-CRLF
    header terminator at all, where the byte pattern first appears as
    unaligned binary data megabytes in (Pennyroyal: 0x1967f4) — the
    unbounded search then skipped half the file and every block parser
    (BALDUCT, DTYPREF, ...) silently returned empty. Scanning from 0 is
    always safe: find_all_tags verifies each hit's length prefix.
    """
    terminator = "\r\n\r\n".encode("utf-16-le")
    search_limit = 8192
    idx = buf.find(terminator, 0, search_limit)
    while idx >= 0 and idx % 2 != 0:
        idx = buf.find(terminator, idx + 1, search_limit)
    if idx < 0:
        return 0
    return idx + len(terminator)
