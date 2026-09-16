"""
review_confidence.py — confidence + materiality review layer.

Turns the engine's binary "verify" flags into the graduated, dollar-
aware review signal that professional takeoff tools use (2026 industry
pattern: surface uncertainty explicitly, auto-trust high-confidence
items, route low-confidence OR high-dollar items to human review —
"the human owns the final number").

Each flagged line already carries verify_reason (+ verify_confidence
from the engine). This adds per-line materiality (the line's dollar
weight) and a BOM-level review_summary the SPA/reviewer uses to work
the riskiest dollars first.
"""
from __future__ import annotations

from typing import Any, Dict, List

_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def _line_value(li: Dict[str, Any]) -> float:
    v = li.get("total_price")
    if v is None:
        v = li.get("total_cost")
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def build_review_summary(bom: Dict[str, Any]) -> Dict[str, Any]:
    """Attach per-line `verify_materiality` and a BOM-level
    `review_summary`. Idempotent; safe on a BOM with no flags."""
    lines: List[Dict[str, Any]] = bom.get("line_items") or []
    bom_total = round(sum(_line_value(li) for li in lines), 2)

    flagged = [li for li in lines if li.get("verify_reason")]
    for li in flagged:
        li["verify_materiality"] = round(_line_value(li), 2)
        # Normalize confidence; default to medium when the engine didn't
        # set one (older flag path).
        if li.get("verify_confidence") not in _CONF_ORDER:
            li["verify_confidence"] = "medium"

    # High-dollar threshold: the professional rule is "verify anything
    # over $X". Scale to the BOM (5% of total) with an absolute floor so
    # small BOMs still catch genuinely material lines.
    high_dollar = round(max(500.0, 0.05 * bom_total), 2)

    by_conf = {"low": 0, "medium": 0, "high": 0}
    flagged_value = 0.0
    priority: List[Dict[str, Any]] = []
    for li in flagged:
        conf = li["verify_confidence"]
        by_conf[conf] = by_conf.get(conf, 0) + 1
        mat = li["verify_materiality"]
        flagged_value += mat
        is_high_dollar = mat >= high_dollar and mat > 0
        # Priority = low confidence OR high dollar (the industry gate).
        if conf == "low" or is_high_dollar:
            priority.append({
                "sku": li.get("sku") or li.get("generic_id"),
                "description": li.get("description"),
                "confidence": conf,
                "materiality": mat,
                "high_dollar": is_high_dollar,
                "reason": (li.get("verify_reason") or "")[:200],
            })

    # Sort priority: lowest confidence first, then highest dollar.
    priority.sort(key=lambda p: (_CONF_ORDER.get(p["confidence"], 1),
                                 -p["materiality"]))

    bom["review_summary"] = {
        "flagged_count": len(flagged),
        "by_confidence": by_conf,
        "flagged_value": round(flagged_value, 2),
        "bom_total": bom_total,
        "high_dollar_threshold": high_dollar,
        "priority_count": len(priority),
        "priority_lines": priority[:25],
    }
    return bom
