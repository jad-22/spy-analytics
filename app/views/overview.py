"""Overview page: SPY price chart, MA overlays, drawdown regimes, KPI strip, drawdown table.

Reads data only through app.components.store; computes only through core.regimes and
core.indicators (both pure, no Streamlit import) per CLAUDE.md's purity rule.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.price_charts import price_figure
from app.components.sidebar import date_range_input, price_basis_input
from app.components.store import get_prices, render_freshness, require_data
from core.config import SETTINGS
from core.indicators import MASpec
from core.regimes import drawdown_series, drawdown_table, overview_kpis, regime_spans


def _regime_label(threshold: float) -> str:
    return f"−{abs(round(threshold * 100))}%"


def _ma_label(label: str) -> str:
    return f"{label[:3].upper()} {label[3:]}"


st.title("Overview")

meta = require_data()
render_freshness(meta)

basis = price_basis_input(key="overview_basis")
prices = get_prices(basis)
full_close = prices["close"]

default_end = prices.index[-1]
default_start = max(
    default_end - pd.DateOffset(years=SETTINGS.overview_default_years), prices.index[0]
)

start, end = date_range_input(prices.index, default_start, default_end, key="overview_range")
window = prices.loc[start:end]

chart_type = st.sidebar.radio(
    "Chart type", ["Line", "Candlestick"], key="overview_chart_type", horizontal=True
)

selected_mas = st.sidebar.multiselect(
    "Moving averages",
    options=list(SETTINGS.overview_ma_options),
    default=list(SETTINGS.overview_default_mas),
    format_func=_ma_label,
    key="overview_mas",
)

if hasattr(st.sidebar, "pills"):
    selected_regimes = st.sidebar.pills(
        "Drawdown regimes",
        options=list(SETTINGS.drawdown_regimes),
        selection_mode="multi",
        default=list(SETTINGS.default_regimes_on),
        format_func=_regime_label,
        key="overview_regimes",
    )
else:
    selected_regimes = st.sidebar.multiselect(
        "Drawdown regimes",
        options=list(SETTINGS.drawdown_regimes),
        default=list(SETTINGS.default_regimes_on),
        format_func=_regime_label,
        key="overview_regimes",
    )
selected_regimes = selected_regimes or []

# KPI strip (OVER-04): computed on the full history, not the selected window.
kpis = overview_kpis(full_close, SETTINGS.realised_vol_window)
kpi_cols = st.columns(4, gap="medium")
kpi_values = [
    ("YTD return", kpis["ytd_return"]),
    ("Distance from ATH", kpis["distance_from_ath"]),
    ("Current drawdown", kpis["current_drawdown"]),
    ("20D realised vol", kpis["realised_vol"]),
]
for col, (label, value) in zip(kpi_cols, kpi_values, strict=True):
    with col, st.container(border=True):
        st.metric(label, f"{value * 100:.1f}%")

st.caption(
    f"KPIs use the full history to the latest close ({full_close.index[-1].date()}) on the "
    f"selected price basis; all-time high {kpis['ath_date'].date()}."
)

# MA overlays computed on full history then sliced (OVER-02: no warm-up gap at window start).
overlays = {label: MASpec.from_label(label).compute(full_close).loc[start:end] for label in selected_mas}

# Regime spans computed on full-history drawdown, then clipped to the selected window.
full_drawdown = drawdown_series(full_close)
regimes: dict[float, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
for threshold in selected_regimes:
    spans = regime_spans(full_drawdown, threshold)
    regimes[threshold] = [
        (max(span_start, start), min(span_end, end))
        for span_start, span_end in spans
        if span_end >= start and span_start <= end
    ]

fig = price_figure(window, chart_type, overlays, regimes)
st.plotly_chart(fig, theme="streamlit", width="stretch")

if chart_type == "Candlestick" and len(window) > SETTINGS.candlestick_warn_bars:
    st.caption("Long candlestick ranges render slowly; narrow the date range or switch to Line.")

basis_caption = (
    "Total return: dividends reinvested"
    if basis == "total_return"
    else "Price only: no dividends"
)
st.caption(basis_caption)

st.subheader("Largest drawdowns")
with st.container(border=True):
    table = drawdown_table(window["close"], SETTINGS.top_drawdowns)
    display_table = table.copy()
    display_table["depth"] = display_table["depth"] * 100
    display_table["recovery"] = display_table["recovery"].apply(
        lambda v: "Not recovered" if pd.isna(v) else v
    )
    st.dataframe(
        display_table,
        column_config={
            "peak": st.column_config.DateColumn("Peak"),
            "trough": st.column_config.DateColumn("Trough"),
            "recovery": st.column_config.Column("Recovery"),
            "depth": st.column_config.NumberColumn("Depth", format="%.1f%%"),
            "days_underwater": st.column_config.NumberColumn("Days underwater"),
        },
        hide_index=True,
    )
st.caption("Drawdowns measured within the selected date range, peak to recovery; days are trading days.")
