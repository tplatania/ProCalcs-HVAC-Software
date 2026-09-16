"""
model_pricing.py — Anthropic model price table + cost estimation.

Single source of truth for turning logged token counts into a dollar
estimate. The chat route (designer bomChat.ts) logs raw tokens + model
into each `chat_message` usage event's detail; cost is computed HERE at
report time, so a price change re-prices history correctly and TS never
has to carry a price table.

Prices are USD per MILLION tokens, by model FAMILY (matched on a prefix
of the model id). Update the table when Anthropic pricing changes — the
values below are the standard tier rates and are intentionally easy to
edit. cache_read / cache_write follow Anthropic's caching multipliers
(read ≈ 0.1× input, write ≈ 1.25× input).
"""
from __future__ import annotations

from typing import Any, Dict

# family prefix -> {input, output, cache_read, cache_write} $/Mtok
_PRICES: Dict[str, Dict[str, float]] = {
    "claude-opus":   {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "claude-sonnet": {"input": 3.0,  "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku":  {"input": 1.0,  "output": 5.0,  "cache_read": 0.10, "cache_write": 1.25},
    # Fable is priced with the Opus tier until a distinct rate is set.
    "claude-fable":  {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
}

_MILLION = 1_000_000.0


def prices_for(model: str | None) -> Dict[str, float] | None:
    """Return the price row for a model id by longest-prefix match, or
    None when the model is unknown (cost then reported as 0 + flagged)."""
    if not model:
        return None
    m = str(model).lower()
    for prefix in sorted(_PRICES, key=len, reverse=True):
        if m.startswith(prefix):
            return _PRICES[prefix]
    return None


def estimate_cost(detail: Dict[str, Any] | None) -> float:
    """USD estimate for one logged event's token detail. Expects keys
    model, input_tokens, output_tokens, cache_read_input_tokens,
    cache_creation_input_tokens (any missing -> 0). Unknown model -> 0."""
    if not isinstance(detail, dict):
        return 0.0
    p = prices_for(detail.get("model"))
    if p is None:
        return 0.0
    it = float(detail.get("input_tokens") or 0)
    ot = float(detail.get("output_tokens") or 0)
    cr = float(detail.get("cache_read_input_tokens") or 0)
    cw = float(detail.get("cache_creation_input_tokens") or 0)
    cost = (it * p["input"] + ot * p["output"]
            + cr * p["cache_read"] + cw * p["cache_write"]) / _MILLION
    return round(cost, 6)
