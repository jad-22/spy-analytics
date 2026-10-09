"""Unit tests for core/news/cost.py (NEWS-07): verified per-unit pricing from
core/config.py, cost math, ledger totals and the pre-spend budget estimate.
"""
from __future__ import annotations

import pytest
from core.news.cost import cost_usd, estimate_backfill_usd, ledger_total_usd, price_for

from core.config import SETTINGS
from core.news.schema import Usage


def test_price_for_known_models():
    assert price_for("claude-haiku-5-5", SETTINGS) == (0.10, 0.50)
    assert price_for("claude-sonnet-5-5", SETTINGS) == (2.0, 10.0)


def test_price_for_unknown_model_raises():
    with pytest.raises(ValueError, match="no verified price"):
        price_for("claude-opus-5-5", SETTINGS)


def test_cost_usd_haiku():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000, web_search_requests=1000)
    assert cost_usd(usage, "claude-haiku-5-5", SETTINGS) == pytest.approx(0.10 + 0.50 + 10.0)


def test_cost_usd_sonnet():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000, web_search_requests=1000)
    assert cost_usd(usage, "claude-sonnet-5-5", SETTINGS) == pytest.approx(2.0 + 10.0 + 10.0)


def test_cost_usd_unknown_model_raises():
    usage = Usage(input_tokens=1, output_tokens=1, web_search_requests=0)
    with pytest.raises(ValueError, match="no verified price"):
        cost_usd(usage, "claude-opus-5-5", SETTINGS)


def test_ledger_total_usd():
    assert ledger_total_usd([{"cost_usd": 1.25}, {"cost_usd": 0.5}]) == 1.75
    assert ledger_total_usd([]) == 0.0


def test_estimate_backfill_usd():
    result = estimate_backfill_usd(142, "claude-haiku-5-5", SETTINGS, 1.5, 5000, 500)
    expected = 142 * (1.5 * 0.01 + 5000 * 0.10e-6 + 500 * 0.50e-6)
    assert result == pytest.approx(expected)
