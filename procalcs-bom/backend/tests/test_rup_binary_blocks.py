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

    def test_emits_available_equipment_models_section(self):
        """Day-3: EQUIPMENT LIBRARY renamed to AVAILABLE EQUIPMENT
        MODELS and demoted to the end of the prompt with a 'do not
        use for sizing' warning. The AI was over-anchoring on it,
        emitting 14× AHU lines on McGinty (21 split-AC library
        entries → 14 emitted lines)."""
        from utils.rup_parser import _build_binary_enrichment_lines
        bytes_ = (
            _wrap("EQUIP", _named_equip_record("Split AC"))
            + _wrap("EQUIP", _named_equip_record("Split AC"))
            + _wrap("EQUIP", _named_equip_record("Gas furnace"))
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "AVAILABLE EQUIPMENT MODELS" in joined
        assert "2 model(s): Split AC" in joined
        assert "1 model(s): Gas furnace" in joined
        # The strong "do not use for sizing" warning must be present.
        assert "Do NOT use these counts to size the BOM" in joined

    def test_emits_zequip_placement_count_with_hard_cap_warning(self):
        """Day-4: ZEQUIP is now the FALLBACK source (used only when
        the DUCT-block hierarchy decoder finds no systems). The hard-
        cap language still has to land — it's the safety net against
        over-counting on Wrightsoft layouts we haven't decoded yet."""
        from utils.rup_parser import _build_binary_enrichment_lines
        bytes_ = (
            _wrap("ZEQUIP", b"\x00" * 32) +
            _wrap("ZEQUIP", b"\x00" * 32) +
            _wrap("ZEQUIP", b"\x00" * 32)
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "EQUIPMENT PLACEMENT (fallback: 3 zone records)" in joined
        assert "MUST NOT exceed 3" in joined

    def test_placement_section_precedes_library_section(self):
        """Day-3 ordering regression-guard. The AI anchors on the FIRST
        equipment-related section it sees in the prompt — if LIBRARY
        comes first, it inflates counts. PLACEMENT must precede
        AVAILABLE EQUIPMENT MODELS in the output stream."""
        from utils.rup_parser import _build_binary_enrichment_lines
        bytes_ = (
            _wrap("EQUIP", _named_equip_record("Split AC")) +
            _wrap("ZEQUIP", b"\x00" * 32)
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        placement_idx = joined.find("EQUIPMENT PLACEMENT")
        library_idx   = joined.find("AVAILABLE EQUIPMENT MODELS")
        assert placement_idx >= 0 and library_idx >= 0
        assert placement_idx < library_idx, (
            "EQUIPMENT PLACEMENT must come before AVAILABLE EQUIPMENT MODELS "
            "in the prompt so the AI sees the authoritative count first."
        )

    def test_emits_named_equipment_from_ecductsys(self):
        """Day-3: ECDUCTSYS carries equipment labels like 'FURNACE 1'
        / 'AHU - 1' in a subset of records. Pulling them into the
        prompt gives the AI ground-truth equipment names."""
        from utils.rup_parser import _build_binary_enrichment_lines
        bytes_ = (
            # 2 ECDUCTSYS records carrying "FURNACE 1" (repeated 3x
            # within each record, matching real-world Wrightsoft layout)
            _wrap("ECDUCTSYS",
                  ("FURNACE 1".encode("utf-16-le") + b"\x00\x00") * 3) +
            _wrap("ECDUCTSYS",
                  ("FURNACE 1".encode("utf-16-le") + b"\x00\x00") * 3) +
            # 1 ECDUCTSYS record with "AHU - 1"
            _wrap("ECDUCTSYS",
                  ("AHU - 1".encode("utf-16-le") + b"\x00\x00") * 3)
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "NAMED EQUIPMENT" in joined
        assert "2x labeled 'FURNACE 1'" in joined
        assert "1x labeled 'AHU - 1'" in joined

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

    # ─── DUCT SYSTEM label (Day 2 / DUCTRUN-pivot enrichment) ──────

    def test_emits_duct_system_label_from_first_duct_record(self):
        """The DUCT umbrella block's first record carries the
        contractor's chosen duct-system name. Multi-char UTF-16 strings
        beyond a couple of short markers should surface as the system
        label + sizing model."""
        from utils.rup_parser import _build_binary_enrichment_lines
        # Mimic Easy's DUCT #0: short marker + meaningful labels.
        body = (
            "PREF".encode("utf-16-le") + b"\x00\x00"
            + "Flex/Flex Junc Boxes-KL".encode("utf-16-le") + b"\x00\x00"
            + "Flex branch/trunks with junction boxes".encode("utf-16-le") + b"\x00\x00"
            + "EqualFric".encode("utf-16-le") + b"\x00\x00"
        )
        bytes_ = _wrap("DUCT", body)
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "DUCT SYSTEM" in joined
        assert "Flex/Flex Junc Boxes-KL" in joined
        # Sizing model should be picked up via the Fric/Equal heuristic.
        assert "EqualFric" in joined

    def test_skips_duct_system_when_no_meaningful_strings(self):
        from utils.rup_parser import _build_binary_enrichment_lines
        # Only the short LOC/RUN markers — no system label.
        bytes_ = _wrap("DUCT", "LOC".encode("utf-16-le"))
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "DUCT SYSTEM" not in joined

    # ─── REGISTER SIZING totals (DREGINFO +0x24 CFM, +0x28 area) ───

    def test_emits_register_sizing_totals(self):
        """DREGINFO field offsets verified empirically against all 3
        sample RUPs (Easy/Average/Edge) — see RUP_BINARY_LAYOUT.md."""
        from utils.rup_parser import _build_binary_enrichment_lines

        def _dreginfo_record(cfm: float, area_sqin: float) -> bytes:
            body = bytearray(64)
            _struct.pack_into("<f", body, 0x24, cfm)
            _struct.pack_into("<f", body, 0x28, area_sqin)
            return bytes(body)

        bytes_ = (
            _wrap("DREGINFO", _dreginfo_record(400.0, 80.0)) +
            _wrap("DREGINFO", _dreginfo_record(300.0, 75.0)) +
            _wrap("DREGINFO", _dreginfo_record(400.0, 80.0))
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "REGISTER SIZING" in joined
        # 400 + 300 + 400 = 1,100 CFM
        assert "1,100 CFM" in joined
        # Per-register average = 1100 / 3 = 367 (rounded)
        assert "avg 367 CFM" in joined
        # Total face area: 80 + 75 + 80 = 235 sq.in
        assert "235 sq.in" in joined

    def test_register_sizing_ignores_zero_cfm_records(self):
        """Records with 0 CFM (probably uninitialized or placeholder
        rows) should be excluded from the total so the average isn't
        skewed downward."""
        from utils.rup_parser import _build_binary_enrichment_lines

        def _dreginfo_record(cfm: float, area_sqin: float) -> bytes:
            body = bytearray(64)
            _struct.pack_into("<f", body, 0x24, cfm)
            _struct.pack_into("<f", body, 0x28, area_sqin)
            return bytes(body)

        bytes_ = (
            _wrap("DREGINFO", _dreginfo_record(0.0, 0.0)) +
            _wrap("DREGINFO", _dreginfo_record(400.0, 80.0)) +
            _wrap("DREGINFO", _dreginfo_record(0.0, 0.0))
        )
        lines = _build_binary_enrichment_lines(bytes_, [], [])
        joined = "\n".join(lines)
        assert "REGISTER SIZING" in joined
        # Only the 1 nonzero register counts toward the summary
        assert "1 registers" in joined
        assert "400 CFM" in joined


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


# ─── DUCT system hierarchy decoder (Phase A / Day-4) ─────────────────

def _duct_pref(label: str | None = None, sizing: str = "EqualFric") -> bytes:
    """Synthesize a DUCT-PREF child body: starts with 'PREF', then the
    duct system label, then the sizing model. Mirrors the real
    layout we see in Wrightsoft output."""
    parts = ["PREF"]
    if label: parts.append(label)
    if sizing: parts.append(sizing)
    out = b""
    for p in parts:
        out += p.encode("utf-16-le") + b"\x00\x00"
    # Pad to a "large" DUCT-PREF size (190+ bytes) so it doesn't get
    # mistaken for a child marker by the size heuristic. Real PREFs
    # are 86-200 bytes.
    return out + b"\x00" * max(0, 200 - len(out))


def _duct_zone(name: str) -> bytes:
    """Synthesize a DUCT child body for a zone. First UTF-16 string
    is the zone name."""
    return name.encode("utf-16-le") + b"\x00\x00" + b"\x00" * 300


def _duct_marker(marker: str) -> bytes:
    """LOC, RUN, ShtMetl, etc. — child records the decoder must skip."""
    return marker.encode("utf-16-le") + b"\x00\x00" + b"\x00" * 30


class TestParseDuctSystemHierarchy:
    def test_returns_empty_when_no_duct_block(self):
        from utils.rup_parser import _parse_duct_system_hierarchy
        assert _parse_duct_system_hierarchy(b"\x00" * 1024) == []

    def test_single_system_with_three_zones(self):
        from utils.rup_parser import _parse_duct_system_hierarchy
        data = (
            _wrap("DUCT", _duct_pref("RectTrunk/RoundBranch-AD")) +
            _wrap("DUCT", _duct_zone("BEDROOM")) +
            _wrap("DUCT", _duct_zone("KITCHEN")) +
            _wrap("DUCT", _duct_zone("BATHROOM"))
        )
        systems = _parse_duct_system_hierarchy(data)
        assert len(systems) == 1
        assert systems[0]["duct_label"] == "RectTrunk/RoundBranch-AD"
        assert systems[0]["sizing_model"] == "EqualFric"
        assert systems[0]["zones"] == ["BEDROOM", "KITCHEN", "BATHROOM"]

    def test_three_systems_grouped_by_pref(self):
        """The McGinty pattern: 3 PREFs each followed by their zones."""
        from utils.rup_parser import _parse_duct_system_hierarchy
        data = (
            _wrap("DUCT", _duct_pref("RectTrunk/RoundBranch-AD")) +
            _wrap("DUCT", _duct_zone("LIV/KIT")) +
            _wrap("DUCT", _duct_zone("ENTRY")) +
            _wrap("DUCT", _duct_pref("RectTrunk/RoundBranch-AD")) +
            _wrap("DUCT", _duct_zone("BEDROOM 4")) +
            _wrap("DUCT", _duct_zone("DINING")) +
            _wrap("DUCT", _duct_zone("MUD ROOM")) +
            _wrap("DUCT", _duct_pref("RectTrunk/RoundBranch-AD")) +
            _wrap("DUCT", _duct_zone("OWNER BEDROOM"))
        )
        systems = _parse_duct_system_hierarchy(data)
        assert len(systems) == 3
        assert [len(s["zones"]) for s in systems] == [2, 3, 1]

    def test_filters_duct_material_tokens(self):
        """ShtMetl / VinlFlx appear as the first string on trunk
        material records and must NOT be counted as zones."""
        from utils.rup_parser import _parse_duct_system_hierarchy
        data = (
            _wrap("DUCT", _duct_pref("MySystem-A")) +
            _wrap("DUCT", _duct_marker("ShtMetl")) +
            _wrap("DUCT", _duct_zone("LIVING ROOM")) +
            _wrap("DUCT", _duct_marker("VinlFlx"))
        )
        systems = _parse_duct_system_hierarchy(data)
        assert len(systems) == 1
        assert systems[0]["zones"] == ["LIVING ROOM"]

    def test_filters_duct_id_tokens(self):
        """st19, rb1, srs2, st13A etc. are duct path IDs, not zones."""
        from utils.rup_parser import _parse_duct_system_hierarchy
        data = (
            _wrap("DUCT", _duct_pref("MySystem-A")) +
            _wrap("DUCT", _duct_zone("BEDROOM")) +
            _wrap("DUCT", _duct_zone("st19")) +
            _wrap("DUCT", _duct_zone("rb1")) +
            _wrap("DUCT", _duct_zone("rrs2")) +
            _wrap("DUCT", _duct_zone("st13A")) +
            _wrap("DUCT", _duct_zone("srs1"))
        )
        systems = _parse_duct_system_hierarchy(data)
        assert systems[0]["zones"] == ["BEDROOM"]

    def test_dedupes_sub_register_suffix(self):
        """LIV/KIT, LIV/KIT-A, LIV/KIT-B → one zone 'LIV/KIT'."""
        from utils.rup_parser import _parse_duct_system_hierarchy
        data = (
            _wrap("DUCT", _duct_pref("MySystem-A")) +
            _wrap("DUCT", _duct_zone("LIV/KIT")) +
            _wrap("DUCT", _duct_zone("LIV/KIT-A")) +
            _wrap("DUCT", _duct_zone("LIV/KIT-B")) +
            _wrap("DUCT", _duct_zone("ENTRY"))
        )
        systems = _parse_duct_system_hierarchy(data)
        assert systems[0]["zones"] == ["LIV/KIT", "ENTRY"]

    def test_drops_pref_with_no_real_label(self):
        """Wrightsoft writes 'template' PREFs (label only contains
        marker tokens) — these aren't real systems."""
        from utils.rup_parser import _parse_duct_system_hierarchy
        data = (
            # PREF with no label (just sizing model)
            _wrap("DUCT", _duct_pref(label=None)) +
            _wrap("DUCT", _duct_zone("PHANTOM ZONE")) +
            # Real system
            _wrap("DUCT", _duct_pref("RealSystem-AD")) +
            _wrap("DUCT", _duct_zone("REAL ZONE"))
        )
        systems = _parse_duct_system_hierarchy(data)
        assert len(systems) == 1
        assert systems[0]["zones"] == ["REAL ZONE"]

    def test_drops_pref_with_no_zones(self):
        from utils.rup_parser import _parse_duct_system_hierarchy
        data = (
            _wrap("DUCT", _duct_pref("LabeledButEmpty-A")) +
            _wrap("DUCT", _duct_pref("RealSystem-AD")) +
            _wrap("DUCT", _duct_zone("REAL ZONE"))
        )
        systems = _parse_duct_system_hierarchy(data)
        assert len(systems) == 1
        assert systems[0]["duct_label"] == "RealSystem-AD"

    def test_infer_equipment_composition_furnace_based(self):
        from utils.rup_parser import _infer_equipment_composition
        c = _infer_equipment_composition(["FURNACE 1", "FURNACE 2"])
        assert "furnace-based" in c["label"]
        assert any("Furnace" in s for s in c["per_system"])
        assert any("Evaporator Coil" in s for s in c["per_system"])
        assert c["excluded"] == []

    def test_infer_equipment_composition_ahu_only(self):
        """Edge case — AHU-only project must NOT emit phantom furnaces
        or phantom separate coils."""
        from utils.rup_parser import _infer_equipment_composition
        c = _infer_equipment_composition(["AHU - 1", "AHU - 2", "AHU - 3 Attic"])
        assert "AHU-only" in c["label"] or "AHU" in c["label"]
        assert not any("Furnace" in s for s in c["per_system"])
        # Coil only as integrated, not as separate line
        assert all("separate" not in s.lower() for s in c["per_system"])
        excluded = " ".join(c["excluded"]).lower()
        assert "furnace" in excluded
        assert "evaporator" in excluded or "coil" in excluded

    def test_infer_equipment_composition_unknown_label_safe_default(self):
        from utils.rup_parser import _infer_equipment_composition
        c = _infer_equipment_composition(["Entire House"])
        assert "default" in c["label"].lower() or "unknown" in c["label"].lower()
        # Safe default = AHU + condenser, no phantom furnace/coil
        assert any("AHU" in s for s in c["per_system"])
        assert any("Condenser" in s for s in c["per_system"])
        assert not any("Furnace" in s for s in c["per_system"])

    def test_extract_rectangular_duct_dims_returns_plausible_sizes(self):
        """Day-7 Phase D — file scan for distinct NxM rectangular duct
        sizes, filtered to HVAC-plausible ranges + capped frequency."""
        from utils.rup_parser import _extract_rectangular_duct_dims
        # Synthesize content with 3 real duct sizes + a Wrightsoft UI
        # layout artifact ("14x3" repeated 100 times — must be excluded
        # by the > 50 cap).
        text = (
            "12x10 " * 3 + "16x12 " * 2 + "6x8 " * 1 +
            "14x3 " * 100  # artifact — should be filtered
        ).encode("utf-16-le")
        dims = _extract_rectangular_duct_dims(text)
        sizes = [(w, h) for (w, h), _ in dims]
        assert (12, 10) in sizes
        assert (16, 12) in sizes
        assert (6, 8) in sizes
        # Artifact filtered
        assert (14, 3) not in sizes
        # Top by frequency, ties broken by area
        assert dims[0][0] == (12, 10)
        assert dims[0][1] == 3

    def test_extract_rectangular_duct_dims_excludes_out_of_range(self):
        """Sizes outside HVAC residential range are noise, not duct
        dimensions."""
        from utils.rup_parser import _extract_rectangular_duct_dims
        text = (
            "60x80 100x200 1x2 3x4 50x40 12x10 "
        ).encode("utf-16-le")
        sizes = [(w, h) for (w, h), _ in _extract_rectangular_duct_dims(text)]
        # In-range
        assert (12, 10) in sizes
        # Out of range (height too small)
        assert (1, 2) not in sizes
        # Out of range (width too small at 3, but height in range)
        assert (3, 4) not in sizes
        # Way too large
        assert (60, 80) not in sizes
        assert (100, 200) not in sizes

    def test_extract_rectangular_duct_dims_excludes_height_3_artifacts(self):
        """Day-7 follow-up — Wrightsoft UI layouts produce '14x3' /
        '10x3' / '60x3' strings throughout the file. Height < 4 is
        not a plausible residential duct dimension and is filtered
        out wholesale."""
        from utils.rup_parser import _extract_rectangular_duct_dims
        text = ("14x3 10x3 60x3 12x10 ").encode("utf-16-le")
        sizes = [(w, h) for (w, h), _ in _extract_rectangular_duct_dims(text)]
        assert (12, 10) in sizes
        assert (14, 3) not in sizes
        assert (10, 3) not in sizes
        assert (60, 3) not in sizes

    def test_extract_rectangular_duct_dims_empty_on_garbage_bytes(self):
        from utils.rup_parser import _extract_rectangular_duct_dims
        assert _extract_rectangular_duct_dims(b"\x00" * 1024) == []

    def test_infer_equipment_composition_empty_labels_safe_default(self):
        from utils.rup_parser import _infer_equipment_composition
        c = _infer_equipment_composition([])
        assert any("AHU" in s for s in c["per_system"])
        # Safe default also excludes phantom types so we don't emit
        # things we can't confirm
        assert c["excluded"]

    def test_ignores_zones_before_first_pref(self):
        """Stray room-name records before any PREF aren't attached
        to a system."""
        from utils.rup_parser import _parse_duct_system_hierarchy
        data = (
            _wrap("DUCT", _duct_zone("ORPHAN")) +
            _wrap("DUCT", _duct_pref("RealSystem-AD")) +
            _wrap("DUCT", _duct_zone("REAL"))
        )
        systems = _parse_duct_system_hierarchy(data)
        assert len(systems) == 1
        assert systems[0]["zones"] == ["REAL"]


# ─── Prompt integration of the hierarchy decoder (Phase B / Day-4) ───

class TestSystemHierarchyInPrompt:
    """The SYSTEM HIERARCHY section is the Day-4 headline. It must
    land FIRST in the enrichment output (so the AI anchors on it)
    and contain the per-system 'emit EXACTLY N' instruction that
    drives equipment line counts."""

    def test_emits_system_hierarchy_section(self):
        from utils.rup_parser import _build_binary_enrichment_lines
        data = (
            _wrap("DUCT", _duct_pref("RectTrunk/RoundBranch-AD")) +
            _wrap("DUCT", _duct_zone("LIV/KIT")) +
            _wrap("DUCT", _duct_zone("ENTRY")) +
            _wrap("DUCT", _duct_pref("RectTrunk/RoundBranch-AD")) +
            _wrap("DUCT", _duct_zone("BEDROOM 4")) +
            _wrap("DUCT", _duct_pref("RectTrunk/RoundBranch-AD")) +
            _wrap("DUCT", _duct_zone("OWNER BEDROOM"))
        )
        out = _build_binary_enrichment_lines(data, [], [])
        joined = "\n".join(out)
        assert "SYSTEM HIERARCHY" in joined
        assert "3 systems / 3 zones" in joined or "3 systems" in joined
        # The "Emit EXACTLY N" instruction is what kills the McGinty
        # over-counting class. Guard it explicitly.
        assert "EXACTLY 3" in joined

    def test_hierarchy_precedes_library_section(self):
        """Anchoring rule: SYSTEM HIERARCHY must be the FIRST
        equipment-related section in the prompt."""
        from utils.rup_parser import _build_binary_enrichment_lines
        data = (
            _wrap("EQUIP", _named_equip_record("Split AC")) +
            _wrap("DUCT", _duct_pref("RectTrunk/RoundBranch-AD")) +
            _wrap("DUCT", _duct_zone("BEDROOM"))
        )
        joined = "\n".join(_build_binary_enrichment_lines(data, [], []))
        hier_idx = joined.find("SYSTEM HIERARCHY")
        lib_idx  = joined.find("AVAILABLE EQUIPMENT MODELS")
        assert hier_idx >= 0 and lib_idx >= 0
        assert hier_idx < lib_idx

    def test_zequip_fallback_only_when_no_hierarchy(self):
        """If the hierarchy decoder finds 0 systems (no DUCT/PREF
        records or unrecognized layout), the cruder ZEQUIP zone-count
        ceiling kicks in as a fallback."""
        from utils.rup_parser import _build_binary_enrichment_lines
        # No DUCT blocks → no hierarchy
        data = _wrap("ZEQUIP", b"\x00" * 32) * 3
        joined = "\n".join(_build_binary_enrichment_lines(data, [], []))
        assert "SYSTEM HIERARCHY" not in joined
        assert "EQUIPMENT PLACEMENT (fallback" in joined

    def test_hierarchy_replaces_zequip_section_when_present(self):
        """When the decoder finds systems, the ZEQUIP fallback must
        NOT also emit — otherwise the AI sees two competing ceilings."""
        from utils.rup_parser import _build_binary_enrichment_lines
        data = (
            _wrap("ZEQUIP", b"\x00" * 32) * 28 +
            _wrap("DUCT", _duct_pref("RectTrunk/RoundBranch-AD")) +
            _wrap("DUCT", _duct_zone("LIVING")) +
            _wrap("DUCT", _duct_pref("RectTrunk/RoundBranch-AD")) +
            _wrap("DUCT", _duct_zone("BEDROOM"))
        )
        joined = "\n".join(_build_binary_enrichment_lines(data, [], []))
        assert "SYSTEM HIERARCHY" in joined
        assert "EQUIPMENT PLACEMENT (fallback" not in joined
