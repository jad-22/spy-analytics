"""Strategy Lab sidebar controls: window/basis/cost/filter settings and the rule picker.

This is the ONLY place that knows about MA rule construction (LAB-10) — the view never
calls ma_crossover/trend_filter/combine_all/MASpec directly, only this module and
core.grid/core.signals do.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from app.components.sidebar import date_range_input, price_basis_input
from core.config import SETTINGS
from core.indicators import MASpec
from core.signals import MACrossoverStrategy, Strategy

_KIND_OPTIONS = ("sma", "ema")


@dataclass(frozen=True)
class LabSettings:
    basis: str
    start: pd.Timestamp
    end: pd.Timestamp
    cost_bps: float
    trend_filter: bool


def lab_settings(index: pd.DatetimeIndex) -> LabSettings:
    """Render the shared sidebar controls (D-10) and return the current settings."""
    basis = price_basis_input(key="lab_basis")
    start, end = date_range_input(
        index,
        pd.Timestamp(SETTINGS.lab_default_start),
        pd.Timestamp(SETTINGS.lab_default_end),
        key="lab_range",
    )
    cost_bps = st.sidebar.slider(
        "Trading cost (bps)", 0.0, SETTINGS.cost_bps_max, 0.0, 0.5, key="lab_cost"
    )
    trend_filter = st.sidebar.toggle("200D trend filter", value=False, key="lab_trend_filter")
    return LabSettings(basis=basis, start=start, end=end, cost_bps=cost_bps,
                       trend_filter=trend_filter)


def rule_input(settings: LabSettings) -> Strategy:
    """Render the MA rule picker and return the selected Strategy (LAB-01, LAB-05, LAB-10).

    Short must be strictly less than long (D-05): enforced with a st.warning + st.stop()
    rather than a dynamic min_value, since Streamlit raises when a stored widget value
    falls below a newly-tightened min_value.
    """
    short_kind = st.sidebar.selectbox(
        "Short MA",
        _KIND_OPTIONS,
        index=_KIND_OPTIONS.index(SETTINGS.lab_default_short[0]),
        format_func=str.upper,
        key="lab_short_kind",
    )
    short_period = st.sidebar.number_input(
        "Short MA period",
        min_value=SETTINGS.short_period_bounds[0],
        max_value=SETTINGS.short_period_bounds[1],
        value=SETTINGS.lab_default_short[1],
        step=1,
        key="lab_short_period",
    )
    long_kind = st.sidebar.selectbox(
        "Long MA",
        _KIND_OPTIONS,
        index=_KIND_OPTIONS.index(SETTINGS.lab_default_long[0]),
        format_func=str.upper,
        key="lab_long_kind",
    )
    long_period = st.sidebar.number_input(
        "Long MA period",
        min_value=SETTINGS.long_period_bounds[0],
        max_value=SETTINGS.long_period_bounds[1],
        value=SETTINGS.lab_default_long[1],
        step=1,
        key="lab_long_period",
    )

    if short_period >= long_period:
        st.warning("Short MA period must be shorter than the long MA period.")
        st.stop()

    trend_filter_period = SETTINGS.trend_filter_period if settings.trend_filter else None
    return MACrossoverStrategy(
        MASpec(short_kind, short_period), MASpec(long_kind, long_period), trend_filter_period
    )


def split_input(settings: LabSettings, last_date: pd.Timestamp) -> pd.Timestamp:
    """Render the IS/OOS split date (LAB-07, D-12), bounded so in-sample is at least
    split_min_years after the sidebar start and out-of-sample is at least
    split_min_oos_months before the latest committed data (not the sidebar end — D-12's
    out-of-sample window always runs to the latest data)."""
    min_date = settings.start + pd.DateOffset(years=SETTINGS.split_min_years)
    max_date = last_date - pd.DateOffset(months=SETTINGS.split_min_oos_months)
    min_date = min(min_date, max_date)
    default = min(max(pd.Timestamp(SETTINGS.default_split), min_date), max_date)
    value = st.sidebar.date_input(
        "Split date", value=default.date(), min_value=min_date.date(),
        max_value=max_date.date(), key="lab_split",
    )
    return pd.Timestamp(value)
