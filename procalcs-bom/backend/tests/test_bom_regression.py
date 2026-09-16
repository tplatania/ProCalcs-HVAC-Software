"""
test_bom_regression.py — golden-signature regression lock for the
deterministic .rup → line-item engine (BETA gate A2 groundwork).

Motivated by the 2026-09 stale-test episode: the parser's output had
drifted from what the tests asserted, and there was no systematic way
to catch drift. This harness snapshots a STRUCTURAL SIGNATURE of the
engine's output for each local fixture and fails if it changes.

Corpus safety: the committed golden file stores ONLY signatures —
counts, the set of section/category names, a SHA-256 of the sorted
generic-id list, and rounded quantity totals. It never stores raw
line items, descriptions, prices, or project contents. The .rup
fixtures themselves are local-only (never committed).

Fixtures absent (CI / another machine) → the test skips. To refresh
after an intended engine change:  UPDATE_BOM_GOLDENS=1 pytest -k regression
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.bom_from_rup import build_lines_from_rup  # noqa: E402

_GOLDEN = Path(__file__).parent / "golden" / "bom_signatures.json"

# Neutral id -> local fixture path. Filenames already appear in
# committed scripts; the goldens key on the neutral id only.
_FIXTURES = {
    "fixture_jappeloup": Path.home() / "Procalcs/Jappeloup Lane Residence_duct.rup",
    "fixture_sw55":      Path.home() / "Procalcs/SW 55th Ave Residence_duct2.rup",
    "fixture_irvine":    Path.home() / "Procalcs/1257 Irvine Rd Residence.rup",
    "fixture_79th":      Path.home() / "Procalcs/RUPs/79th Ct Residence Load Calcs.rup",
    "fixture_clarke":    Path.home() / "Procalcs/BOM Samples/Clarke Residence Load Calcs.rup",
}


def _signature(lines: list[dict]) -> dict:
    """Structural signature of engine output — no raw customer content."""
    sections: dict[str, int] = {}
    qty_by_section: dict[str, float] = {}
    gids = []
    for li in lines:
        sec = str(li.get("section_hint") or li.get("section") or "?")
        sections[sec] = sections.get(sec, 0) + 1
        qty_by_section[sec] = round(
            qty_by_section.get(sec, 0.0) + float(li.get("quantity") or 0), 2)
        g = li.get("generic_id")
        if g:
            gids.append(str(g))
    sku_hash = hashlib.sha256("\n".join(sorted(gids)).encode()).hexdigest()[:16]
    return {
        "line_count": len(lines),
        "distinct_generic_ids": len(set(gids)),
        "sections": dict(sorted(sections.items())),
        "qty_by_section": dict(sorted(qty_by_section.items())),
        "sku_hash": sku_hash,
    }


def _current() -> dict:
    out = {}
    for fid, path in _FIXTURES.items():
        if not path.exists():
            continue
        lines = build_lines_from_rup(path.read_bytes(),
                                     source_name=fid, rheia_takeoff=False)
        out[fid] = _signature(lines)
    return out


def _load_golden() -> dict:
    if _GOLDEN.exists():
        return json.loads(_GOLDEN.read_text())
    return {}


def test_bom_engine_signatures_match_golden():
    current = _current()
    if not current:
        pytest.skip("no local .rup fixtures present")

    if os.environ.get("UPDATE_BOM_GOLDENS") == "1":
        _GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        _GOLDEN.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        pytest.skip(f"goldens refreshed → {_GOLDEN}")

    golden = _load_golden()
    if not golden:
        pytest.skip("no golden baseline yet — run UPDATE_BOM_GOLDENS=1 to seed")

    mismatches = []
    for fid, sig in current.items():
        if fid not in golden:
            mismatches.append(f"{fid}: new fixture not in golden (seed goldens)")
        elif golden[fid] != sig:
            mismatches.append(
                f"{fid} drift:\n  golden={json.dumps(golden[fid], sort_keys=True)}"
                f"\n  now   ={json.dumps(sig, sort_keys=True)}")
    assert not mismatches, (
        "BOM engine output drifted from golden signatures. If intended, "
        "refresh with UPDATE_BOM_GOLDENS=1.\n\n" + "\n\n".join(mismatches))
