"""Tests for the RE-revision filename conventions in zoho_sync.

Run: python3 scripts/zoho-sync/test_re_filter.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


def _is_re(name: str) -> bool:
    stem = os.path.splitext(name)[0].lower().rstrip()
    return stem.endswith(" re") or stem.endswith("-re")


def _canonical_stem(name: str) -> str:
    stem = os.path.splitext(name)[0].rstrip()
    low = stem.lower()
    if low.endswith(" re") or low.endswith("-re"):
        stem = stem[:-3].rstrip().rstrip("-").rstrip()
    return stem


CASES_IS_RE = [
    # (filename, expected)
    ("Lot 14 T331 FHL RE.rup", True),           # space RE
    ("Lot 2028 V116 Hampton TUL-RE.rup", True),  # hyphen RE (Park View)
    ("Lot 78 E478 Somerset TUN -RE.rup", True),  # space-hyphen RE (Pennyroyal)
    ("Lot 14 T331 FHL.rup", False),
    ("T034 Master.rup", False),
    ("Recreation Center.rup", False),            # 're' inside a word
    ("Solaire.rup", False),                      # ends in 're' but no separator
]

CASES_CANONICAL = [
    ("Lot 14 T331 FHL RE.rup", "Lot 14 T331 FHL"),
    ("Lot 2028 V116 Hampton TUL-RE.rup", "Lot 2028 V116 Hampton TUL"),
    ("Lot 78 E478 Somerset TUN -RE.rup", "Lot 78 E478 Somerset TUN"),
    ("Lot 14 T331 FHL.rup", "Lot 14 T331 FHL"),
]

failures = 0
for name, expected in CASES_IS_RE:
    got = _is_re(name)
    status = "ok" if got == expected else "FAIL"
    if got != expected:
        failures += 1
    print(f"  [{status}] _is_re({name!r}) = {got} (want {expected})")

for name, expected in CASES_CANONICAL:
    got = _canonical_stem(name)
    status = "ok" if got == expected else "FAIL"
    if got != expected:
        failures += 1
    print(f"  [{status}] _canonical_stem({name!r}) = {got!r} (want {expected!r})")

print()
if failures:
    print(f"{failures} FAILURES")
    sys.exit(1)
print("all passed")
