"""Overview page: SPY price line chart from the committed snapshot.

Skeleton depth for Plan 01 — Plan 03 adds the KPI strip, MA overlays, candlesticks,
drawdown regime shading and the largest-drawdowns table.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.sidebar import date_range_input, price_basis_input
from app.components.store import get_prices, render_freshness, require_data
from app.components.theme import STRATEGY_BLUE
from core.config import SETTINGS

st.title("Overview")

meta = require_data()
render_freshness(meta)

basis = price_basis_input(key="overview_basis")
prices = get_prices(basis)

default_end = prices.index[-1]
default_start = max(
    default_end - pd.DateOffset(years=SETTINGS.overview_default_years), prices.index[0]
)

start, end = date_range_input(prices.index, default_start, default_end, key="overview_range")
window = prices.loc[start:end]

if len(window) > SETTINGS.scattergl_threshold_bars:
    trace = go.Scattergl(
        x=window.index, y=window["close"], line_color=STRATEGY_BLUE, name="SPY close"
    )
else:
    trace = go.Scatter(
        x=window.index, y=window["close"], line_color=STRATEGY_BLUE, name="SPY close"
    )

fig = go.Figure(data=[trace])
st.plotly_chart(fig, theme="streamlit", width="stretch")

basis_caption = (
    "Total return: dividends reinvested"
    if basis == "total_return"
    else "Price only: no dividends"
)
st.caption(basis_caption)
