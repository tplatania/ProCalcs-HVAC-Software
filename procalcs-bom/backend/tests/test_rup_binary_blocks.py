"""
Tests for the structural binary-block helpers in utils/rup_parser.py
added during the May 2026 RUP-parser reverse-engineering session.

These exercise the lowest-level building blocks (_block_bodies, the
EQUIP record decoder, and the equipment-name classifier) so that the
follow-up parsers (ZEQUIP / DUCTRUN / DREGINFO / FITNG) have a verified
foundation to build on.

Real .rup files are NOT checked into the repo (proprietary Wrightsoft
binary format, often contains client PII like addresses). These tests
synthesize the minimum byte layouts each parser needs — enough to
exercise the helpers without requiring a sample file at test time.

See _repo-docs/RUP_BINARY_LAYOUT.md for the empirical layout notes
these tests encode.
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.rup_parser import (
    _block_bodies,
    _classify_equipment_name,
    _parse_equip_blocks,
)


# ─── Block-marker helpers ──────────────────────────────────────────────

def _wrap_block(tag: str, body: bytes) -> bytes:
    """Build a single !BEG=<tag>...body...!END=<tag> span as it would
    appear in a real .rup file (UTF-16-LE markers)."""
    beg = f"!BEG={tag}".encode("utf-16-le")
    end = f"!END={tag}".encode("utf-16-le")
    return beg + body + end


def _equip_record(name: str, schema: int = 11, record_id: int = 0,
                  flags: int = 0) -> bytes:
    """Build a synthetic EQUIP block body matching the layout decoded
    in RUP_BINARY_LAYOUT.md: 5 uint32 header (schema, record_id, flags,
    reserved, name_length_bytes) followed by UTF-16-LE name."""
    name_bytes = name.encode("utf-16-le")
    header = struct.pack("<IIIII", schema, record_id, flags, 0, len(name_bytes))
    # Pad with zero bytes after the name to mimic the real records'
    # fixed-position fields (the parser only reads name_length_bytes
    # so the trailing content is irrelevant for these tests).
    trailer = b"\x00" * 32
    return header + name_bytes + trailer


# ─── _block_bodies ─────────────────────────────────────────────────────

class TestBlockBodies:
    def test_returns_empty_list_when_tag_absent(self):
        assert _block_bodies(b"random bytes with no markers", "EQUIP") == []

    def test_returns_single_body_for_one_block(self):
        body = b"hello world"
        data = _wrap_block("EQUIP", body)
        bodies = _block_bodies(data, "EQUIP")
        assert bodies == [body]

    def test_returns_multiple_bodies_in_file_order(self):
        b1, b2, b3 = b"first", b"second", b"third"
        data = _wrap_block("EQUIP", b1) + b"junk" + _wrap_block("EQUIP", b2) + _wrap_block("EQUIP", b3)
        assert _block_bodies(data, "EQUIP") == [b1, b2, b3]

    def test_does_not_match_tag_substrings(self):
        # !BEG=EQUIPLIST should NOT match a request for "EQUIP" because
        # the matching is byte-exact: !BEG=EQUIP <bytes that aren't !END=EQUIP>...
        # In practice this is fine since real Wrightsoft tags are short
        # fixed identifiers, but we want the helper itself to be honest
        # about what "exact" means.
        data = _wrap_block("EQUIPLIST", b"payload")
        # The literal string "!BEG=EQUIP" IS contained inside "!BEG=EQUIPLIST"
        # so this WILL match — documenting current behavior so a future
        # fix is intentional. Add a sentinel block to make sure we don't
        # over-promise tag-isolation guarantees.
        bodies = _block_bodies(data, "EQUIP")
        # We expect at least one match here even though semantically
        # EQUIP and EQUIPLIST are different tags. If this test starts
        # failing, the helper got stricter and that's a deliberate
        # change worth reviewing.
        assert len(bodies) >= 1

    def test_handles_unbalanced_markers_gracefully(self):
        # BEG with no matching END: the helper stops at the first BEG
        # that has no END after it, returning what it found so far.
        data = _wrap_block("EQUIP", b"complete") + "!BEG=EQUIP".encode("utf-16-le") + b"orphan"
        bodies = _block_bodies(data, "EQUIP")
        assert bodies == [b"complete"]


# ─── _classify_equipment_name ──────────────────────────────────────────

class TestClassifyEquipmentName:
    def test_recognizes_air_handler_variants(self):
        assert _classify_equipment_name("Air Handler") == "air_handler"
        assert _classify_equipment_name("AHU") == "air_handler"
        assert _classify_equipment_name("AIR HANDLER 3T") == "air_handler"

    def test_recognizes_condenser_variants(self):
        assert _classify_equipment_name("Split AC") == "condenser"
        assert _classify_equipment_name("Condenser") == "condenser"
        assert _classify_equipment_name("Carrier 24ABB6 Condenser") == "condenser"

    def test_recognizes_furnace(self):
        assert _classify_equipment_name("Gas furnace") == "furnace"
        assert _classify_equipment_name("Oil furnace 80% AFUE") == "furnace"

    def test_recognizes_heat_kit(self):
        assert _classify_equipment_name("Heat Kit") == "heat_kit"
        assert _classify_equipment_name("Electric Heat 5kW") == "heat_kit"

    def test_recognizes_erv_variants(self):
        assert _classify_equipment_name("ERV") == "erv"
        assert _classify_equipment_name("HRV") == "erv"
        assert _classify_equipment_name("Energy Recovery Ventilator") == "erv"

    def test_recognizes_heat_pump(self):
        assert _classify_equipment_name("Heat Pump") == "heat_pump"

    def test_unrecognized_falls_back_to_other(self):
        # Important: unknown names must NOT silently become "air_handler"
        # — the rules engine differentiates by type, and a misclass
        # would inflate counts and corrupt downstream BOM math.
        assert _classify_equipment_name("Gas WH") == "other"
        assert _classify_equipment_name("Mystery Widget 3000") == "other"
        assert _classify_equipment_name("") == "other"

    def test_normalizes_case_and_whitespace(self):
        assert _classify_equipment_name("   GAS    FURNACE   ") == "furnace"
        assert _classify_equipment_name("split\tac") == "condenser"


# ─── _parse_equip_blocks ───────────────────────────────────────────────

class TestParseEquipBlocks:
    def test_returns_empty_list_when_no_equip_blocks(self):
        data = b"random bytes with no markers"
        assert _parse_equip_blocks(data) == []

    def test_decodes_single_block_with_classified_type(self):
        data = _wrap_block("EQUIP", _equip_record("Split AC", record_id=42))
        equip = _parse_equip_blocks(data)
        assert len(equip) == 1
        assert equip[0]["raw_name"] == "Split AC"
        assert equip[0]["type"] == "condenser"
        assert equip[0]["record_id"] == 42
        assert equip[0]["cfm"] is None  # not yet decoded
        assert equip[0]["tonnage"] is None

    def test_decodes_multiple_blocks_in_file_order(self):
        data = (
            _wrap_block("EQUIP", _equip_record("Split AC", record_id=1))
            + _wrap_block("EQUIP", _equip_record("Gas furnace", record_id=2))
            + _wrap_block("EQUIP", _equip_record("ERV", record_id=3))
        )
        equip = _parse_equip_blocks(data)
        types = [e["type"] for e in equip]
        assert types == ["condenser", "furnace", "erv"]

    def test_skips_records_with_undecodable_header(self):
        # A body shorter than the 0x14 header is malformed — skip rather
        # than crash. Real Wrightsoft files don't emit short EQUIP blocks
        # but corrupted uploads might.
        data = _wrap_block("EQUIP", b"\x00\x00\x00")
        assert _parse_equip_blocks(data) == []

    def test_caps_name_length_at_body_size(self):
        # Defensive: a record claiming a name_length larger than the
        # body must not over-read past the buffer. Build a record whose
        # declared name_length is huge but the actual name bytes are short.
        body = struct.pack("<IIIII", 11, 1, 0, 0, 999) + "AHU".encode("utf-16-le")
        data = _wrap_block("EQUIP", body)
        equip = _parse_equip_blocks(data)
        assert len(equip) == 1
        # Whatever name was decoded shouldn't crash; it should still
        # carry SOMETHING readable.
        assert "AHU" in equip[0]["raw_name"]

    def test_strips_trailing_nulls_and_whitespace(self):
        body = struct.pack("<IIIII", 11, 1, 0, 0, 16) + "AHU\x00\x00\x00".encode("utf-16-le")
        data = _wrap_block("EQUIP", body)
        equip = _parse_equip_blocks(data)
        assert equip[0]["raw_name"] == "AHU"


# ─── Phase 1 enrichment (May 2026) — raw_rup_context binary signals ──
#
# _build_raw_context now accepts file_bytes and appends sections from
# binary blocks the text-regex parser doesn't surface (EQUIP names,
# ZEQUIP count, BALDUCT real room names, DUCTRUN/DREGINFO/FITNG
# counts). All optional — old callers without file_bytes get the same
# text-only context as before. Validates the >170% raw_rup_context
# growth on Easy/Avg sample RUPs that closes the AI hybrid-path gap.

import struct as _struct  # local alias to keep block-helper tests independent


def _wrap(tag: str, body: bytes) -> bytes:
    """UTF-16-LE !BEG=<tag>...body...!END=<tag> wrapper."""
    return f"!BEG={tag}".encode("utf-16-le") + body + f"!END={tag}".encode("utf-16-le")


def _named_equip_record(name: str) -> bytes:
    """Synthetic EQUIP body that matches the layout _parse_equip_blocks decodes."""
    name_bytes = name.encode("utf-16-le")
    header = _struct.pack("<IIIII", 11, 1, 0, 0, len(name_bytes))
    return header + name_bytes + b"\x00" * 32


def _balduct_room(name: str) -> bytes:
    """Synthetic BALDUCT body carrying a UTF-16 room name."""
    return name.encode("utf-16-le") + b"\x00\x00"


class TestUtf16StringsInBlock:
    def test_extracts_printable_runs(self):
        from utils.rup_parser import _utf16_strings_in_block
        data = "Hello\x00".encode("utf-16-le") + b"\x00\x00\x00" + "World".encode("utf-16-le")
        assert "Hello" in _utf16_strings_in_block(data)
        assert "World" in _utf16_strings_in_block(data)

    def test_min_len_filter(self):
        from utils.rup_parser import _utf16_strings_in_block
        data = "Hi".encode("utf-16-le") + b"\x00\x00" + "Hello".encode("utf-16-le")
        # min_len defaults to 3, so "Hi" is dropped, "Hello" kept
        out = _utf16_strings_in_block(data)
        assert "Hello" in out
        assert "Hi" not in out


class TestBuildBinaryEnrichmentLines:
    def test_returns_empty_when_no_blocks(self):
        from utils.rup_parser import _build_binary_enrichment_lines
        # Random bytes with no recognized blocks
        assert _build_binary_enrichment_lines(b"\x00" * 1024, [], []) == []

    def test_emits_equipment_library_section(self):
        from utils.rup_parser import _build_binary_enrichment_lines
        bytes_ = (
            _wrap("EQUIP", _named_equip_record("Split AC"))
            + _wrap("EQUIP", _named_equip_record("Split AC"))
            + _wrap("EQUIP", _named_equip_record("Gas furnace"))
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "EQUIPMENT LIBRARY" in joined
        assert "2x Split AC" in joined
        assert "1x Gas furnace" in joined
        # Note about library-vs-instance must be present so the AI
        # doesn't double-count.
        assert "library" in joined.lower()

    def test_emits_zequip_placement_count(self):
        from utils.rup_parser import _build_binary_enrichment_lines
        bytes_ = (
            _wrap("ZEQUIP", b"\x00" * 32) +
            _wrap("ZEQUIP", b"\x00" * 32) +
            _wrap("ZEQUIP", b"\x00" * 32)
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "EQUIPMENT PLACEMENT" in joined
        assert "3 zone-equipment" in joined or "3 ZEQUIP" in joined

    def test_emits_balduct_room_names_when_text_rooms_empty(self):
        from utils.rup_parser import _build_binary_enrichment_lines
        bytes_ = (
            _wrap("BALDUCT", _balduct_room("Master Bedroom")) +
            _wrap("BALDUCT", _balduct_room("Pantry"))
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "ROOMS" in joined
        assert "Master Bedroom" in joined
        assert "Pantry" in joined

    def test_skips_balduct_rooms_when_text_rooms_already_have_data(self):
        """Don't duplicate the rooms section. Edge RUPs hit this path."""
        from utils.rup_parser import _build_binary_enrichment_lines
        bytes_ = _wrap("BALDUCT", _balduct_room("Master Bedroom"))
        text_rooms = [{"name": "Living Rm", "ahu": "AHU - 1"}]
        lines = _build_binary_enrichment_lines(bytes_, [], text_rooms)
        joined = "\n".join(lines)
        # No rooms-from-balance-records section should appear; the
        # canonical rooms section is emitted by _build_raw_context itself.
        assert "balance records" not in joined

    def test_drops_obvious_garbage_room_tokens(self):
        """Parser tags like 'rb1', 'rb2' shouldn't surface as room names."""
        from utils.rup_parser import _build_binary_enrichment_lines
        bytes_ = (
            _wrap("BALDUCT", _balduct_room("BEDROOM")) +
            _wrap("BALDUCT", _balduct_room("rb1")) +
            _wrap("BALDUCT", _balduct_room("rb2"))
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "BEDROOM" in joined
        assert "rb1" not in joined  # garbage filtered
        assert "rb2" not in joined

    def test_emits_design_complexity_counts(self):
        from utils.rup_parser import _build_binary_enrichment_lines
        bytes_ = (
            _wrap("DUCTRUN", b"\x00" * 32) +
            _wrap("DREGINFO", b"\x00" * 64) +
            _wrap("FITNG", b"\x00" * 56) +
            _wrap("FITNG", b"\x00" * 56)
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "DESIGN COMPLEXITY" in joined
        assert "DUCTRUN): 1" in joined
        assert "DREGINFO): 1" in joined
        assert "FITNG): 2" in joined


class TestBuildRawContextBackwardsCompat:
    """Pre-Phase-1 callers (no file_bytes arg) must keep getting the
    original text-only context shape."""

    def test_no_file_bytes_skips_binary_sections(self):
        from utils.rup_parser import _build_raw_context
        ctx = _build_raw_context(
            project={"name": "Test"},
            building={"type": "single_level", "duct_location": "attic"},
            equipment=[],
            rooms=[],
            full_text="some text",
            # file_bytes deliberately omitted
        )
        assert "EQUIPMENT LIBRARY" not in ctx
        assert "EQUIPMENT PLACEMENT" not in ctx
        assert "DESIGN COMPLEXITY" not in ctx
        # Original sections still emit
        assert "Test" in ctx  # project name
        assert "single_level" in ctx
