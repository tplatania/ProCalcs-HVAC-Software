"""Tests for services.model_pricing (cost-control phase C)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.model_pricing import estimate_cost, prices_for


def test_opus_cost():
    d = {"model": "claude-opus-4-8", "input_tokens": 1000, "output_tokens": 500}
    # 15*.001 + 75*.0005 = 0.015 + 0.0375
    assert estimate_cost(d) == 0.0525


def test_sonnet_is_cheaper_than_opus():
    toks = {"input_tokens": 1000, "output_tokens": 500}
    opus = estimate_cost({"model": "claude-opus-4-8", **toks})
    sonnet = estimate_cost({"model": "claude-sonnet-4-20250514", **toks})
    assert sonnet < opus
    assert round(opus / sonnet, 1) == 5.0  # ~5x cheaper


def test_cache_read_is_cheap():
    read = estimate_cost({"model": "claude-opus-4-8", "cache_read_input_tokens": 1000})
    fresh = estimate_cost({"model": "claude-opus-4-8", "input_tokens": 1000})
    assert read < fresh
    assert round(fresh / read, 0) == 10.0  # cache read ~10% of input


def test_unknown_model_is_zero_not_error():
    assert estimate_cost({"model": "gpt-4", "input_tokens": 1000}) == 0.0
    assert estimate_cost({"input_tokens": 1000}) == 0.0  # no model
    assert estimate_cost(None) == 0.0
    assert prices_for(None) is None
    assert prices_for("gpt-4") is None


def test_family_prefix_match():
    # any opus/sonnet/haiku id resolves by prefix
    assert prices_for("claude-opus-5")["input"] == 15.0
    assert prices_for("claude-sonnet-5")["input"] == 3.0
    assert prices_for("claude-haiku-4-5-20251001")["input"] == 1.0
