"""
bom_diff.py — Pure helper for diffing two BOM responses.

Phase 11 of the testing harness (May 2026). Server-side mirror of
src/lib/bom-diff.ts in designer-desktop — used by the regression-suite
endpoint to auto-detect drift between a parent run and its
just-generated child, so the SPA can flag "regression" members
without an extra round trip per row.

Strategy mirrors the SPA module exactly so the two stay in sync:
  * key by SKU (case-insensitive) when present, else by
    (description|section|source) tuple.
  * coalesce duplicate keys by summing quantity + cost + price.
  * sub-cent jitter (< 0.005) treated as unchanged.
"""
from __future__ import annotations

from typing import Any


_EPS = 0.005


def _line_key(li: dict[str, Any]) -> str:
    sku = (li.get("sku") or "").strip()
    if sku:
        return f"sku:{sku.upper()}"
    desc    = (li.get("description") or "").strip().lower()
    section = (li.get("section") or "").strip().lower()
    source  = (li.get("source") or "").strip().lower()
    return f"desc:{desc}|{section}|{source}"


def _aggregate(bom: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for li in (bom or {}).get("line_items") or []:
        k = _line_key(li)
        agg = out.get(k)
        qty = float(li.get("quantity") or 0)
        tc  = float(li.get("total_cost") or 0)
        tp  = float(li.get("total_price") or 0)
        if agg:
            agg["qty"] += qty
            agg["total_cost"] += tc
            agg["total_price"] += tp
        else:
            out[k] = {"qty": qty, "total_cost": tc, "total_price": tp, "label": (li.get("sku") or li.get("description") or "")}
    return out


def _approx_eq(a: float, b: float) -> bool:
    return abs(a - b) < _EPS


def diff_summary(left_bom: dict[str, Any] | None, right_bom: dict[str, Any] | None) -> dict[str, Any]:
    """Compact summary: just the totals + bucket counts (no per-line
    payload). What the regression-auto-detect path actually needs."""
    left = _aggregate(left_bom)
    right = _aggregate(right_bom)
    keys = set(left.keys()) | set(right.keys())

    added = removed = unchanged = changed = 0
    for k in keys:
        l = left.get(k); r = right.get(k)
        if l and not r:
            removed += 1
        elif not l and r:
            added += 1
        elif l and r:
            if (
                _approx_eq(l["qty"], r["qty"])
                and _approx_eq(l["total_cost"], r["total_cost"])
                and _approx_eq(l["total_price"], r["total_price"])
            ):
                unchanged += 1
            else:
                changed += 1

    left_items  = len((left_bom or {}).get("line_items") or [])
    right_items = len((right_bom or {}).get("line_items") or [])
    left_cost   = float(((left_bom  or {}).get("totals") or {}).get("total_cost")  or 0)
    right_cost  = float(((right_bom or {}).get("totals") or {}).get("total_cost")  or 0)
    left_price  = float(((left_bom  or {}).get("totals") or {}).get("total_price") or 0)
    right_price = float(((right_bom or {}).get("totals") or {}).get("total_price") or 0)

    return {
        "left_item_count":   left_items,
        "right_item_count":  right_items,
        "item_count_delta":  right_items - left_items,
        "left_total_cost":   round(left_cost, 2),
        "right_total_cost":  round(right_cost, 2),
        "total_cost_delta":  round(right_cost - left_cost, 2),
        "left_total_price":  round(left_price, 2),
        "right_total_price": round(right_price, 2),
        "total_price_delta": round(right_price - left_price, 2),
        "added":     added,
        "removed":   removed,
        "changed":   changed,
        "unchanged": unchanged,
    }


# Threshold for "regression detected" label. Any structural change
# (added / removed / changed) flags it, since the suite is meant to
# catch unintended drift. Caller can post-filter as needed.
def is_regression(summary: dict[str, Any]) -> bool:
    return bool(summary.get("added") or summary.get("removed") or summary.get("changed"))
