"""
Day-31 synthetic tests (Tom's 2026-07-31 review asks).

Covers, with NO corpus/local-file dependency:
  1. The 17-family Rheia-gate threshold (count_conventional_duct_skus
     + CONV_SKU_THRESHOLD) on synthetic priced lines, both sides.
  2. Register pre-flight DREGINFO decoding — auto vs user mode — on
     synthetic .rup bytes built to the RupReader tag contract.
  3. Malformed-record handling: truncated blocks, out-of-range sizes,
     files with no DREGINFO at all.
  4. Regeneration structural-extras carry-forward
     (carry_structural_extras), including None/non-dict parents and
     the never-overwrite rule.

The empirical calibration behind the threshold (50 known-Rheia pairs
max 7 vs six conventional projects min 27) lives in the designer
repo's scripts/corpus-analysis/validate_day28_engine_fixes.py — rups
cannot be committed, so its run log is the committed artifact
(designer docs/validation-2026-07-31-rheia-gate.md).
"""
from __future__ import annotations

import struct

from services.bom_from_rup import (
    CONV_DUCT_FAMILIES,
    CONV_SKU_THRESHOLD,
    count_conventional_duct_skus,
)
from services.bom_patches import (
    STRUCTURAL_EXTRA_KEYS,
    carry_structural_extras,
)
from utils.rup_register_preflight import extract_register_preflight


# ─── 1. Rheia gate threshold ────────────────────────────────────────

def _lines(generic_ids):
    return [{"generic_id": g} for g in generic_ids]


def test_gate_counts_distinct_skus_across_all_17_families():
    # one SKU per family — every family must be recognized
    ids = [f"{fam}-TEST" for fam in CONV_DUCT_FAMILIES]
    assert len(CONV_DUCT_FAMILIES) == 17
    assert count_conventional_duct_skus(_lines(ids)) == 17


def test_gate_ignores_non_conventional_and_dedupes():
    ids = ["DDVn04", "DDVn04", "DDVn04",          # duplicates → 1
           "10-01-220", "B150E", "EQUIP-X", ""]   # Rheia/equipment → 0
    assert count_conventional_duct_skus(_lines(ids)) == 1


def test_gate_threshold_boundary():
    # 14 distinct conventional SKUs → below threshold (Rheia stub side)
    below = _lines([f"FBTI-{i:02d}" for i in range(14)])
    assert count_conventional_duct_skus(below) == CONV_SKU_THRESHOLD - 1
    # 15 distinct → at threshold (conventional side, gate fires)
    at = _lines([f"FBTI-{i:02d}" for i in range(15)])
    assert count_conventional_duct_skus(at) >= CONV_SKU_THRESHOLD


def test_gate_calibration_margins_hold_around_threshold():
    # Empirical anchors from the day-31 calibration: known-Rheia max 7,
    # conventional min 27. Both must stay on their side of the
    # threshold — if someone edits CONV_SKU_THRESHOLD out of the gap,
    # this fails.
    assert 7 < CONV_SKU_THRESHOLD <= 27


# ─── 2 + 3. Register pre-flight decode ──────────────────────────────

def _dreginfo_block(mode: int, w: float, h: float) -> bytes:
    """One DREGINFO block matching the RupReader tag contract: a u32
    length prefix + '!BEG=DREGINFO' UTF-16LE, then the payload the
    decoder reads (u32 ver, u32 id, u32 mode, f64 w, f64 h)."""
    tag = "!BEG=DREGINFO".encode("utf-16-le")
    payload = struct.pack("<III", 5, 358, mode) + struct.pack("<dd", w, h)
    return struct.pack("<I", len(tag)) + tag + payload


def _rup(*blocks: bytes) -> bytes:
    # Minimal synthetic file: UTF-16 header + terminator, then blocks.
    header = "Synthetic\r\n\r\n".encode("utf-16-le")
    return header + b"".join(blocks)


def test_preflight_decodes_auto_and_user_modes():
    data = _rup(
        _dreginfo_block(1, 12.0, 12.0),   # auto default
        _dreginfo_block(1, 12.0, 12.0),
        _dreginfo_block(2, 14.0, 14.0),   # user-set
        _dreginfo_block(2, 30.0, 20.0),
    )
    pf = extract_register_preflight(data)
    assert pf == {
        "auto_count": 2,
        "user_count": 2,
        "total": 4,
        "auto_sizes": {"12x12": 2},
        "user_sizes": {"14x14": 1, "30x20": 1},
    }


def test_preflight_no_dreginfo_returns_none():
    assert extract_register_preflight(_rup()) is None
    assert extract_register_preflight(b"") is None


def test_preflight_truncated_record_is_skipped_not_fatal():
    good = _dreginfo_block(2, 10.0, 10.0)
    truncated = good[:len(good) - 20]  # cut into the f64s
    pf = extract_register_preflight(_rup(good, truncated))
    assert pf is not None
    assert pf["total"] == 1
    assert pf["user_sizes"] == {"10x10": 1}


def test_preflight_out_of_range_sizes_are_skipped():
    data = _rup(
        _dreginfo_block(2, 0.0, 12.0),      # zero width — garbage
        _dreginfo_block(2, 500.0, 12.0),    # 500 inches — garbage
        _dreginfo_block(1, 12.0, 12.0),     # valid
    )
    pf = extract_register_preflight(data)
    assert pf == {
        "auto_count": 1, "user_count": 0, "total": 1,
        "auto_sizes": {"12x12": 1}, "user_sizes": {},
    }


def test_preflight_unknown_mode_values_are_ignored():
    data = _rup(_dreginfo_block(7, 12.0, 12.0),
                _dreginfo_block(2, 8.0, 4.0))
    pf = extract_register_preflight(data)
    assert pf["total"] == 1
    assert pf["user_sizes"] == {"8x4": 1}


# ─── 4. Regeneration carry-forward ──────────────────────────────────

def test_carry_copies_all_structural_keys():
    parent = {k: f"parent-{k}" for k in STRUCTURAL_EXTRA_KEYS}
    parent["line_items"] = ["must-not-copy"]
    child: dict = {}
    carry_structural_extras(child, parent)
    assert child == {k: f"parent-{k}" for k in STRUCTURAL_EXTRA_KEYS}


def test_carry_never_overwrites_child_values():
    parent = {"register_preflight": {"auto_count": 9}}
    child = {"register_preflight": {"auto_count": 1}}
    carry_structural_extras(child, parent)
    assert child["register_preflight"] == {"auto_count": 1}


def test_carry_tolerates_missing_or_invalid_parent():
    child = {"line_items": []}
    assert carry_structural_extras(dict(child), None) == child
    assert carry_structural_extras(dict(child), "not-a-dict") == child
    assert carry_structural_extras(dict(child), {}) == child


def test_carry_key_set_includes_register_preflight():
    # Guard: adding a new structural extra to the engine without
    # adding it here means regenerated runs silently lose it again.
    assert "register_preflight" in STRUCTURAL_EXTRA_KEYS
