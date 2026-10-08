"""Run many MA crossover rules on one common window, and test robustness to start date."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import pandas as pd

from core.backtest import BacktestResult, run_backtest
from core.indicators import MASpec
from core.metrics import summarise
from core.signals import MACrossoverStrategy, Strategy

_INSUFFICIENT_HISTORY = "Not enough price history for these rules in the selected window"
_SPLIT_OUTSIDE_WINDOW = "Split date must fall inside the backtest window"


def default_pairs(short_periods=(10, 20, 50), long_periods=(100, 200),
                  kinds=("sma", "ema")) -> list[tuple[MASpec, MASpec]]:
    """Same 24 combinations as the 2022 notebook."""
    shorts = [MASpec(k, p) for k in kinds for p in short_periods]
    longs = [MASpec(k, p) for k in kinds for p in long_periods]
    return list(product(shorts, longs))


def notebook_strategies(trend_filter_period: int | None = None) -> list[MACrossoverStrategy]:
    """The 24 notebook rules as Strategy objects, optionally AND-ed with a trend filter."""
    return [MACrossoverStrategy(s, lg, trend_filter_period) for s, lg in default_pairs()]


def grid_window(prices: pd.DataFrame, strategies: list[Strategy], start=None,
                end=None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The common window every strategy shares: starts once the slowest target is
    available, respecting an optional `start` override, and ends at the last available bar
    (after an optional `end` slice). Factored out of run_strategy_grid (Plan 05) so the
    heatmap can report the same window without re-running the grid.

    If `end` is not None, prices is first sliced to `prices.loc[:end]` — this matches
    scripts/rerun_notebook_grid.py's `prices.loc[:end]` convention, so PHASE0_FINDINGS
    reproduce exactly. Exposure lags the target by one bar, so the first interval every
    strategy can trade is the bar *after* the slowest target becomes valid.
    """
    if end is not None:
        prices = prices.loc[:end]
    first_valids = [s.target(prices).first_valid_index() for s in strategies]
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
    return common_start, prices.index[-1]


def run_strategy_grid(prices: pd.DataFrame, strategies: list[Strategy], cost_bps: float = 0.0,
                      start=None, end=None) -> pd.DataFrame:
    """All strategies share the window that starts once the slowest target is available.

    See grid_window for the window/end-slicing convention (unchanged by the Plan 05 refactor).
    """
    if end is not None:
        prices = prices.loc[:end]
    common_start, _ = grid_window(prices, strategies, start=start, end=end)
    rows = {}
    for s in strategies:
        res = run_backtest(prices, s.target(prices), cost_bps=cost_bps, start=common_start,
                           end=end)
        rows[s.name] = summarise(res)
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


def heatmap_pairs(short_kind: str, long_kind: str, short_range: tuple[int, int, int],
                  long_range: tuple[int, int, int]) -> list[tuple[MASpec, MASpec]]:
    """Independent-kind heatmap grid (D-06, D-07): short kind/long kind are each fixed,
    periods vary independently over (start, inclusive stop, step). Pairs with
    short >= long are excluded, same shape rule as default_pairs/combine_all's callers."""
    s_start, s_stop, s_step = short_range
    l_start, l_stop, l_step = long_range
    shorts = [MASpec(short_kind, p) for p in range(s_start, s_stop + 1, s_step)]
    longs = [MASpec(long_kind, p) for p in range(l_start, l_stop + 1, l_step)]
    return [(s, lg) for s in shorts for lg in longs if s.period < lg.period]


@dataclass(frozen=True)
class HeatmapResult:
    excess: pd.DataFrame  # index=short period, columns=long period, values=excess_total_return
    start: pd.Timestamp
    end: pd.Timestamp


def heatmap_grid(prices: pd.DataFrame, short_kind: str, long_kind: str,
                 short_range: tuple[int, int, int], long_range: tuple[int, int, int],
                 cost_bps: float = 0.0, start=None, end=None,
                 trend_filter_period: int | None = None) -> HeatmapResult:
    """Excess-return-vs-B&H heatmap for one SMA/EMA type pair (D-06, D-07), sharing the
    sidebar's cost/basis/filter settings (D-10) via run_ma_grid/grid_window."""
    pairs = heatmap_pairs(short_kind, long_kind, short_range, long_range)
    strategies = [MACrossoverStrategy(s, lg, trend_filter_period) for s, lg in pairs]
    win_start, win_end = grid_window(prices, strategies, start=start, end=end)
    grid = run_ma_grid(prices, pairs, cost_bps=cost_bps, start=start, end=end,
                       trend_filter_period=trend_filter_period)
    rows = [
        {"short": s.period, "long": lg.period,
         "excess": grid.loc[MACrossoverStrategy(s, lg, trend_filter_period).name,
                             "excess_total_return"]}
        for s, lg in pairs
    ]
    excess = (
        pd.DataFrame(rows)
        .pivot(index="short", columns="long", values="excess")
        .sort_index(axis=0)
        .sort_index(axis=1)
    )
    return HeatmapResult(excess=excess, start=win_start, end=win_end)


def rolling_start_strategy(prices: pd.DataFrame, strategy: Strategy, horizon_years: int = 5,
                           freq: str = "YS", cost_bps: float = 0.0) -> pd.DataFrame:
    """Excess return of one Strategy for every start date (default yearly) over a fixed
    horizon (D-11). Generalises rolling_start to any Strategy, not just a bare MA pair."""
    target = strategy.target(prices)
    first = target.first_valid_index()
    last = prices.index[-1] - pd.DateOffset(years=horizon_years)
    rows = []
    for s in pd.date_range(first, last, freq=freq):
        e = s + pd.DateOffset(years=horizon_years)
        m = summarise(run_backtest(prices, target, cost_bps=cost_bps, start=s, end=e))
        rows.append({"start": s, "end": e, "strategy": m["total_return"],
                     "buy_and_hold": m["bh_total_return"], "excess": m["excess_total_return"]})
    cols = ["start", "end", "strategy", "buy_and_hold", "excess"]
    return pd.DataFrame(rows, columns=cols).set_index("start")


def rolling_start(prices: pd.DataFrame, short: MASpec, long: MASpec, horizon_years: int = 5,
                  freq: str = "YS", cost_bps: float = 0.0) -> pd.DataFrame:
    """Excess return of one bare MA-crossover rule for every start date, over a fixed
    horizon. Thin wrapper over rolling_start_strategy — output is unchanged (Plan 05), so
    scripts/rerun_notebook_grid.py keeps producing identical numbers."""
    return rolling_start_strategy(prices, MACrossoverStrategy(short, long), horizon_years,
                                  freq, cost_bps)


def is_oos_split(prices: pd.DataFrame, strategy: Strategy, split, start=None,
                 cost_bps: float = 0.0) -> tuple[BacktestResult, BacktestResult]:
    """In-sample (start -> split) vs out-of-sample (split -> latest data) for one strategy
    (D-12, Pattern 4). OOS always runs to the latest bar, regardless of any sidebar end date.

    evaluate_strategy's own end-slicing convention (prices.loc[:end] before computing the
    target) is what keeps the two windows contiguous and non-overlapping: IS's last interval
    is dropped (no next-day open inside the sliced frame) exactly where OOS's first interval
    begins.
    """
    split_ts = pd.Timestamp(split)
    target = strategy.target(prices)
    first_valid = target.first_valid_index()
    if first_valid is None:
        raise ValueError(_INSUFFICIENT_HISTORY)
    pos = prices.index.get_loc(first_valid) + 1
    if pos >= len(prices.index):
        raise ValueError(_INSUFFICIENT_HISTORY)
    effective_start = prices.index[pos]
    if start is not None:
        effective_start = max(effective_start, pd.Timestamp(start))
    if split_ts <= effective_start or split_ts >= prices.index[-1]:
        raise ValueError(_SPLIT_OUTSIDE_WINDOW)
    is_result = evaluate_strategy(prices, strategy, cost_bps=cost_bps, start=start, end=split_ts)
    oos_result = evaluate_strategy(prices, strategy, cost_bps=cost_bps, start=split_ts, end=None)
    return is_result, oos_result
