"""Cached Strategy Lab computations (D-09).

No ttl on purpose — same reasoning as app/components/store.py: each nightly data commit
redeploys the app and restarts the process, which clears this cache (CLAUDE.md). Every
function is keyed on primitives (basis/start/end as ISO date strings, cost_bps, trend_filter)
plus the frozen MACrossoverStrategy dataclass — st.cache_data pickles frozen dataclasses of
hashable primitives without needing a hash_funcs override.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.store import get_prices
from core.backtest import BacktestResult
from core.config import SETTINGS
from core.grid import (
    HeatmapResult,
    count_beating,
    evaluate_strategy,
    heatmap_grid,
    is_oos_split,
    notebook_strategies,
    rolling_start_strategy,
    run_strategy_grid,
)
from core.signals import MACrossoverStrategy, Strategy


@st.cache_data
def headline_grid(basis: str, start: str, end: str, cost_bps: float,
                  trend_filter: bool) -> pd.DataFrame:
    """The 24-notebook-rule grid for the current sidebar settings (D-03, D-10)."""
    prices = get_prices(basis)
    strategies = notebook_strategies(SETTINGS.trend_filter_period if trend_filter else None)
    return run_strategy_grid(prices, strategies, cost_bps=cost_bps, start=start, end=end)


@st.cache_data
def phase0_anchor_count() -> int:
    """Live-computed count on the notebook's own 2010-2022 window (D-02's fixed anchor)."""
    grid = headline_grid(
        "total_return", SETTINGS.lab_default_start, SETTINGS.lab_default_end, 0.0, False
    )
    return count_beating(grid)


@st.cache_data
def selected_backtest(strategy: Strategy, basis: str, start: str, end: str,
                      cost_bps: float) -> BacktestResult:
    """Backtest the currently selected rule against the sidebar settings (LAB-03, LAB-04)."""
    prices = get_prices(basis)
    return evaluate_strategy(prices, strategy, cost_bps=cost_bps, start=start, end=end)


@st.cache_data
def heatmap_for(strategy: Strategy, basis: str, start: str, end: str,
                cost_bps: float) -> HeatmapResult | None:
    """The LAB-05 short x long heatmap for the selected rule's type pair (D-07), sharing
    the sidebar settings (D-10). None for any Strategy that isn't a MACrossoverStrategy —
    the grid only has meaning for an independent short/long MA type pair (LAB-10)."""
    if not isinstance(strategy, MACrossoverStrategy):
        return None
    prices = get_prices(basis)
    return heatmap_grid(
        prices, strategy.short.kind, strategy.long.kind,
        SETTINGS.heatmap_short_range, SETTINGS.heatmap_long_range,
        cost_bps=cost_bps, start=start, end=end, trend_filter_period=strategy.trend_filter_period,
    )


@st.cache_data
def rolling_for(strategy: Strategy, basis: str, cost_bps: float) -> pd.DataFrame:
    """The LAB-06 rolling-start chart: always full history 1993 -> latest (D-11), ignoring
    the sidebar window, but sharing the sidebar's cost/basis/filter."""
    prices = get_prices(basis)
    return rolling_start_strategy(prices, strategy, SETTINGS.rolling_horizon_years,
                                  cost_bps=cost_bps)


@st.cache_data
def is_oos_for(strategy: Strategy, basis: str, start: str, split: str,
              cost_bps: float) -> tuple[BacktestResult, BacktestResult]:
    """The LAB-07 in-sample/out-of-sample split (D-12): out-of-sample always runs to the
    latest data regardless of the sidebar end date."""
    prices = get_prices(basis)
    return is_oos_split(prices, strategy, split, start=start, cost_bps=cost_bps)
