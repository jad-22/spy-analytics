"""Regression test: the Strategy Lab's engine must still reproduce docs/PHASE0_FINDINGS.md
exactly, on the real committed 1993+ snapshot (not a synthetic fixture).

Tolerance rationale: SMA rules are identical between a run starting in 1993 and one starting
in 2010 (an SMA has no memory beyond its own window). EMA rules seeded from 1993 instead of
2010 decay to a difference under 1e-3 by October 2010 (exponential decay of the seeding
error over ~4,400 trading days). Buy-and-hold depends only on the ratio of opens/adj_close
within the window, which is basis-independent of the seed date. The 0/24 "beat" counts are
therefore asserted exactly (count_beating(grid) == 0); the headline total-return numbers use
pytest.approx with a small absolute tolerance to allow for this EMA-seeding difference. Never
edit docs/PHASE0_FINDINGS.md or widen the tolerance to force a pass — investigate instead.
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.config import SETTINGS
from core.grid import count_beating, default_pairs, evaluate_strategy, run_ma_grid
from core.indicators import MASpec
from core.signals import MACrossoverStrategy
from core.storage import load_prices, price_basis

WINDOW_START = "2010-10-19"


@pytest.mark.parametrize(
    "end,basis,cost_bps",
    [
        ("2022-12-16", "total_return", 0.0),
        ("2022-12-16", "total_return", 5.0),
        ("2022-12-16", "price_only", 0.0),
        ("2021-12-01", "total_return", 0.0),
        ("2021-12-01", "total_return", 5.0),
        ("2021-12-01", "price_only", 0.0),
    ],
)
def test_zero_of_24_beat_buy_and_hold(end, basis, cost_bps):
    """None of the 24 notebook rules beats buy-and-hold, on any window/basis/cost tested."""
    raw = load_prices(SETTINGS.prices_path)
    prices = price_basis(raw, basis)
    grid = run_ma_grid(prices, default_pairs(), cost_bps=cost_bps, start=WINDOW_START, end=end)
    assert count_beating(grid) == 0


def test_default_window_numbers():
    """The default view's numbers match docs/PHASE0_FINDINGS.md's reported row exactly."""
    raw = load_prices(SETTINGS.prices_path)
    prices = price_basis(raw, "total_return")
    grid = run_ma_grid(prices, default_pairs(), cost_bps=0.0, start=WINDOW_START, end="2022-12-16")
    assert grid.loc["ema10__sma200", "total_return"] == pytest.approx(2.150, abs=0.005)
    assert grid.loc["ema10__sma200", "bh_total_return"] == pytest.approx(3.152, abs=0.005)

    strategy = MACrossoverStrategy(MASpec("ema", 10), MASpec("sma", 200))
    result = evaluate_strategy(
        prices, strategy, cost_bps=0.0, start=WINDOW_START, end="2022-12-16"
    )
    assert result.equity.index[0] == pd.Timestamp(WINDOW_START)
