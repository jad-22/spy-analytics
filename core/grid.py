"""Run many MA crossover rules on one common window, and test robustness to start date."""
from __future__ import annotations

from itertools import product

import pandas as pd

from core.backtest import run_backtest
from core.indicators import MASpec
from core.metrics import summarise
from core.signals import MACrossoverStrategy, Strategy, ma_crossover

_INSUFFICIENT_HISTORY = "Not enough price history for these rules in the selected window"


def default_pairs(short_periods=(10, 20, 50), long_periods=(100, 200),
                  kinds=("sma", "ema")) -> list[tuple[MASpec, MASpec]]:
    """Same 24 combinations as the 2022 notebook."""
    shorts = [MASpec(k, p) for k in kinds for p in short_periods]
    longs = [MASpec(k, p) for k in kinds for p in long_periods]
    return list(product(shorts, longs))


def notebook_strategies(trend_filter_period: int | None = None) -> list[MACrossoverStrategy]:
    """The 24 notebook rules as Strategy objects, optionally AND-ed with a trend filter."""
    return [MACrossoverStrategy(s, lg, trend_filter_period) for s, lg in default_pairs()]


def run_strategy_grid(prices: pd.DataFrame, strategies: list[Strategy], cost_bps: float = 0.0,
                      start=None, end=None) -> pd.DataFrame:
    """All strategies share the window that starts once the slowest target is available.

    If `end` is not None, prices is first sliced to `prices.loc[:end]` — this matches
    scripts/rerun_notebook_grid.py's `prices.loc[:end]` convention, so PHASE0_FINDINGS
    reproduce exactly. Exposure lags the target by one bar, so the first interval every
    strategy can trade is the bar *after* the slowest target becomes valid.
    """
    if end is not None:
        prices = prices.loc[:end]
    targets = {s.name: s.target(prices) for s in strategies}
    first_valids = [t.first_valid_index() for t in targets.values()]
    if any(fv is None for fv in first_valids):
        raise ValueError(_INSUFFICIENT_HISTORY)
    last_first_valid = max(first_valids)
    pos = prices.index.get_loc(last_first_valid) + 1
    if pos >= len(prices.index):
        raise ValueError(_INSUFFICIENT_HISTORY)
    common_start = prices.index[pos]
    if start is not None:
        common_start = max(common_start, pd.Timestamp(start))
    if common_start > prices.index[-1]:
        raise ValueError(_INSUFFICIENT_HISTORY)
    rows = {}
    for name, target in targets.items():
        res = run_backtest(prices, target, cost_bps=cost_bps, start=common_start, end=end)
        rows[name] = summarise(res)
    return pd.DataFrame(rows).T.sort_values("excess_total_return", ascending=False)


def run_ma_grid(prices: pd.DataFrame, pairs: list[tuple[MASpec, MASpec]], cost_bps: float = 0.0,
                start=None, end=None, trend_filter_period: int | None = None) -> pd.DataFrame:
    """Thin wrapper over run_strategy_grid for the MA-crossover pairs shape used by the
    heatmap/picker. Name output stays identical to the pre-Strategy-interface behaviour
    when trend_filter_period is None.
    """
    strategies = [MACrossoverStrategy(s, lg, trend_filter_period) for s, lg in pairs]
    return run_strategy_grid(prices, strategies, cost_bps=cost_bps, start=start, end=end)


def evaluate_strategy(prices: pd.DataFrame, strategy: Strategy, cost_bps: float = 0.0,
                      start=None, end=None):
    """Backtest one strategy with the same end-slicing and warm-up rule as run_strategy_grid."""
    if end is not None:
        prices = prices.loc[:end]
    target = strategy.target(prices)
    first_valid = target.first_valid_index()
    if first_valid is None:
        raise ValueError(_INSUFFICIENT_HISTORY)
    pos = prices.index.get_loc(first_valid) + 1
    if pos >= len(prices.index):
        raise ValueError(_INSUFFICIENT_HISTORY)
    common_start = prices.index[pos]
    if start is not None:
        common_start = max(common_start, pd.Timestamp(start))
    if common_start > prices.index[-1]:
        raise ValueError(_INSUFFICIENT_HISTORY)
    return run_backtest(prices, target, cost_bps=cost_bps, start=common_start, end=end)


def count_beating(grid: pd.DataFrame) -> int:
    """How many rules in the grid beat buy-and-hold (D-03)."""
    return int((grid["excess_total_return"] > 0).sum())


def rolling_start(prices: pd.DataFrame, short: MASpec, long: MASpec, horizon_years: int = 5,
                  freq: str = "YS", cost_bps: float = 0.0) -> pd.DataFrame:
    """Excess return of one rule for every start date (default yearly) over a fixed horizon."""
    target = ma_crossover(prices["close"], short, long)
    first = target.first_valid_index()
    last = prices.index[-1] - pd.DateOffset(years=horizon_years)
    rows = []
    for s in pd.date_range(first, last, freq=freq):
        e = s + pd.DateOffset(years=horizon_years)
        m = summarise(run_backtest(prices, target, cost_bps=cost_bps, start=s, end=e))
        rows.append({"start": s, "end": e, "strategy": m["total_return"],
                     "buy_and_hold": m["bh_total_return"], "excess": m["excess_total_return"]})
    return pd.DataFrame(rows).set_index("start")
