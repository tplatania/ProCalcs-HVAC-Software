#!/usr/bin/env python3
"""
rup_diff.py — Day-31: block-aware differ for Wrightsoft .rup pairs.

Purpose: property-sheet reverse engineering. Richard saves a project
(baseline), changes EXACTLY ONE property in Wrightsoft's property
sheet, saves again — this tool reports which blocks and bytes changed,
with typed interpretations (u32/f32/f64/utf16) of the changed values.
One clean pair per property ≈ one decoded field.

Method:
  1. Index every `!BEG=<TAG>` position in both files (same scanner the
     production parsers use — length-prefix verified).
  2. Align tag sequences with difflib on (tag-name) tokens so an
     inserted/removed block doesn't desynchronize everything after it.
  3. For matched segments of equal length: fast XOR scan → changed
     spans. For resized segments: report as structural change with
     both segments' tag context.
  4. For each changed span: enclosing tag, offset inside the segment,
     hex before/after, and decode attempts of the aligned 4/8-byte
     windows as u32 / f32 / f64, plus a UTF-16 readback around the
     span.

Usage:
    python3 rup_diff.py baseline.rup changed.rup [--max-spans 40]

Exit 0 always (analysis tool). Output is meant to be read by a human
or pasted back to the session for decode work.
"""

from __future__ import annotations

import argparse
import difflib
import struct
import sys
from pathlib import Path

UPSTREAM = Path.home() / "Projects/procalcs-hvac-upstream/procalcs-bom/backend"
sys.path.insert(0, str(UPSTREAM))

_BEG = "!BEG=".encode("utf-16-le")


def index_tags(buf: bytes):
    """[(pos, name)] for every verified !BEG=<NAME> in file order."""
    out = []
    i = 0
    while True:
        hit = buf.find(_BEG, i)
        if hit < 0:
            break
        # name = utf16 chars until a non [A-Za-z0-9_] char, max 24 chars
        j = hit + len(_BEG)
        name_chars = []
        while j + 1 < len(buf) and len(name_chars) < 24:
            ch = buf[j:j + 2]
            c = ch.decode("utf-16-le", errors="replace")
            if not (c.isalnum() or c == "_"):
                break
            name_chars.append(c)
            j += 2
        name = "".join(name_chars)
        if name:
            # verify u32 length prefix right before the tag body
            body_len = (len(_BEG) // 2 + len(name)) * 2
            lp = hit - 4
            if lp >= 0 and struct.unpack_from("<I", buf, lp)[0] == body_len:
                out.append((hit, name))
        i = hit + len(_BEG)
    return out


def spans_equal_len(a: bytes, b: bytes, base_off: int):
    """Changed (start, end) spans (absolute in a) for equal-length bufs."""
    spans = []
    i, n = 0, len(a)
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            spans.append((base_off + i, base_off + j))
            i = j
        else:
            i += 1
    return spans


def interpret(a: bytes, b: bytes, off: int, seg_a: int, seg_b: int, width=16):
    """Human-readable interpretation of one changed span."""
    s, e = off, off
    out = []
    ax = a[max(0, off - 4):off + width]
    bx = b[max(0, off - 4 + (seg_b - seg_a)):off + width + (seg_b - seg_a)]
    out.append(f"      hex before: {ax.hex(' ')}")
    out.append(f"      hex after : {bx.hex(' ')}")
    for w, fmt, label in ((4, "<I", "u32"), (4, "<f", "f32"), (8, "<d", "f64")):
        for align in range(-3, 1):
            p = off + align
            if p < 0 or p + w > len(a) or p + w + (seg_b - seg_a) > len(b):
                continue
            try:
                va = struct.unpack_from(fmt, a, p)[0]
                vb = struct.unpack_from(fmt, b, p + (seg_b - seg_a))[0]
            except struct.error:
                continue
            if va != vb:
                if fmt != "<I":
                    if not (abs(va) < 1e12 and abs(vb) < 1e12):
                        continue
                    va, vb = round(float(va), 4), round(float(vb), 4)
                out.append(f"      {label}@{align:+d}: {va} → {vb}")
                break
    # utf16 readback around the span
    lo = max(0, off - 40)
    ta = a[lo:off + 60].decode("utf-16-le", errors="replace")
    tb = b[lo + (seg_b - seg_a) if lo else 0: off + 60 + (seg_b - seg_a)].decode(
        "utf-16-le", errors="replace")
    clean = lambda s: "".join(c for c in s if c.isprintable())[:60]
    if clean(ta) or clean(tb):
        out.append(f"      utf16 ctx: {clean(ta)!r} → {clean(tb)!r}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline"); ap.add_argument("changed")
    ap.add_argument("--max-spans", type=int, default=40)
    args = ap.parse_args()
    A = Path(args.baseline).read_bytes()
    B = Path(args.changed).read_bytes()
    print(f"baseline: {args.baseline} ({len(A):,} bytes)")
    print(f"changed : {args.changed} ({len(B):,} bytes)  Δsize={len(B)-len(A):+d}")

    ta, tb = index_tags(A), index_tags(B)
    print(f"tags: {len(ta)} vs {len(tb)}")

    # align tag sequences by name
    sm = difflib.SequenceMatcher(a=[n for _, n in ta], b=[n for _, n in tb],
                                 autojunk=False)
    shown = 0
    from collections import Counter
    changed_tags = Counter()
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal":
            # compare inter-tag segments pairwise
            for k in range(a2 - a1):
                pa, name = ta[a1 + k]
                pb, _ = tb[b1 + k]
                ea = ta[a1 + k + 1][0] if a1 + k + 1 < len(ta) else len(A)
                eb = tb[b1 + k + 1][0] if b1 + k + 1 < len(tb) else len(B)
                seg_a, seg_b = A[pa:ea], B[pb:eb]
                if seg_a == seg_b:
                    continue
                changed_tags[name] += 1
                if len(seg_a) == len(seg_b):
                    for s, e in spans_equal_len(seg_a, seg_b, 0):
                        if shown >= args.max_spans:
                            break
                        shown += 1
                        print(f"\n  [{name}] @file+0x{pa+s:X} "
                              f"(block+0x{s:X}, {e-s} bytes changed)")
                        print(interpret(A, B, pa + s, pa, pb))
                else:
                    if shown < args.max_spans:
                        shown += 1
                        print(f"\n  [{name}] RESIZED block: "
                              f"{len(seg_a)} → {len(seg_b)} bytes "
                              f"(Δ{len(seg_b)-len(seg_a):+d}) @file+0x{pa:X}")
        else:
            names_a = [n for _, n in ta[a1:a2]]
            names_b = [n for _, n in tb[b1:b2]]
            print(f"\n  STRUCTURAL {op}: -{Counter(names_a)} +{Counter(names_b)}")
            for n in names_a: changed_tags[n] += 1
            for n in names_b: changed_tags[n] += 1

    print(f"\n== summary: changed blocks by tag ==")
    for name, c in changed_tags.most_common(15):
        print(f"  {name}: {c}")
    if not changed_tags:
        print("  (files identical at block level)")


if __name__ == "__main__":
    main()
