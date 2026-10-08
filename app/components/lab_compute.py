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
from core.grid import count_beating, evaluate_strategy, notebook_strategies, run_strategy_grid
from core.signals import Strategy


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
