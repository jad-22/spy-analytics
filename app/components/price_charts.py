"""Plotly figure builder for the Overview price chart (OVER-01..03).

Pure with respect to Streamlit caching: this module builds a go.Figure from already-sliced
data; it does not read from app.components.store or call st.cache_data itself.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from app.components.theme import BH_GRAY, DRAWDOWN_OPACITY, GAIN_GREEN, LOSS_RED, STRATEGY_BLUE
from core.config import SETTINGS

# Cycled across MA overlays in the same order as .streamlit/config.toml's
# chartCategoricalColors, starting after STRATEGY_BLUE since the close trace already uses it.
OVERLAY_COLORS: tuple[str, ...] = (BH_GRAY, GAIN_GREEN, LOSS_RED, STRATEGY_BLUE)


def price_figure(
    window: pd.DataFrame,
    chart_type: str,
    overlays: dict[str, pd.Series],
    regimes: dict[float, list[tuple[pd.Timestamp, pd.Timestamp]]],
) -> go.Figure:
    """Build the Overview price chart: line or candlestick, MA overlays, drawdown shading.

    window: OHLC DataFrame already sliced to the selected date range.
    overlays: label (e.g. "sma50") to a Series already computed on full history, then sliced.
    regimes: threshold (e.g. -0.10) to a list of (start, end) spans, already clipped to window.
    """
    fig = go.Figure()

    if chart_type == "Candlestick":
        fig.add_trace(
            go.Candlestick(
                x=window.index,
                open=window["open"],
                high=window["high"],
                low=window["low"],
                close=window["close"],
                increasing_line_color=GAIN_GREEN,
                decreasing_line_color=LOSS_RED,
                name="SPY",
            )
        )
        fig.update_layout(xaxis_rangeslider_visible=False)
    else:
        trace_cls = (
            go.Scattergl if len(window) > SETTINGS.scattergl_threshold_bars else go.Scatter
        )
        fig.add_trace(
            trace_cls(
                x=window.index, y=window["close"], line_color=STRATEGY_BLUE, name="SPY close"
            )
        )

    for i, (label, series) in enumerate(overlays.items()):
        color = OVERLAY_COLORS[i % len(OVERLAY_COLORS)]
        kind, period = label[:3], label[3:]
        fig.add_trace(
            go.Scatter(
                x=series.index, y=series, line_color=color, name=f"{kind.upper()} {period}"
            )
        )

    # Shallowest first so the deepest (darkest) band composites on top (nested bands).
    for threshold in sorted(regimes, key=abs):
        opacity = DRAWDOWN_OPACITY[threshold]
        for start, end in regimes[threshold]:
            fig.add_vrect(
                x0=start,
                x1=end,
                fillcolor=LOSS_RED,
                opacity=opacity,
                line_width=0,
                layer="below",
            )

    fig.update_layout(
        hovermode="x unified",
        legend={"orientation": "h"},
        margin={"l": 40, "r": 20, "t": 30, "b": 20},
    )
    return fig
