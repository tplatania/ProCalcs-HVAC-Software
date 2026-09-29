"""
Grille auto-exclude (Richard, NE 132nd 2026-09-24): drop grille lines
confirmed as auto-sized 12x12 defaults ("not in the actual duct layout"),
recording what was removed so it's transparent + reversible.

These lock the exclusion MECHANICS on the `auto_sized_grille_artifact`
marker (set upstream only when the lump smell AND the DREGINFO auto-sized
check both fire). Detection firing on a real file is the existing
heuristic and is verified on staging (needs the catalog mount).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.bom_from_rup import apply_grille_auto_exclude  # noqa: E402


def _lines():
    return [
        {"generic_id": "26SPA642WC0300", "section_hint": "Equipment", "quantity": 1},
        {"generic_id": "FRGRMFT-1212", "description": "Floor grille 12x12",
         "quantity": 12, "auto_sized_grille_artifact": True},
        {"generic_id": "FRGRMCG-0808", "description": "Ceiling grille 8x8",
         "quantity": 3},
    ]


def test_marked_artifact_excluded_and_recorded():
    lines = _lines()
    apply_grille_auto_exclude(lines)
    ids = [li["generic_id"] for li in lines]
    assert "FRGRMFT-1212" not in ids          # the auto-sized lump is gone
    assert "FRGRMCG-0808" in ids               # the real, sized grille stays
    assert "26SPA642WC0300" in ids
    rec = lines[0].get("excluded_auto_sized_grilles")
    assert rec and rec[0]["generic_id"] == "FRGRMFT-1212"
    assert rec[0]["quantity"] == 12
    assert "not a real placement" in rec[0]["reason"]


def test_no_marked_lines_is_noop():
    lines = [{"generic_id": "FRGRMCG-0808", "quantity": 3},
             {"generic_id": "FRGRMCG-1010", "quantity": 2}]
    before = [dict(li) for li in lines]
    apply_grille_auto_exclude(lines)
    assert lines == before
    assert "excluded_auto_sized_grilles" not in lines[0]


def test_never_blanks_the_bom():
    # If somehow every line were marked, keep the BOM rather than empty it.
    lines = [{"generic_id": "FRGRMFT-1212", "quantity": 12,
              "auto_sized_grille_artifact": True}]
    apply_grille_auto_exclude(lines)
    assert len(lines) == 1
    assert "excluded_auto_sized_grilles" not in lines[0]


def test_empty_lines_is_safe():
    lines = []
    apply_grille_auto_exclude(lines)      # must not raise
    assert lines == []
