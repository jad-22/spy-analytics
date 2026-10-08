"""Plotly figure builder and metrics formatting for the Strategy Lab (LAB-03, LAB-04)."""
from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from app.components.theme import BH_GRAY, DIVERGING_COLORSCALE, GAIN_GREEN, LOSS_RED, STRATEGY_BLUE
from core.backtest import BacktestResult
from core.grid import HeatmapResult

_PERCENT_ROWS = ("CAGR", "Max drawdown", "Time in market")
_RATIO_ROWS = ("Sharpe", "Sortino", "Calmar")
_SELECTED_MARKER_SIZE = 14
_RULE_MARKER_SIZE = 9


def equity_figure(result: BacktestResult, label: str) -> go.Figure:
    """Selected rule's equity curve against buy-and-hold, with buy/sell fills marked."""
    buys = result.trades[result.trades["side"] == "buy"]
    sells = result.trades[result.trades["side"] == "sell"]

    traces = [
        go.Scatter(
            x=result.equity.index, y=result.equity.values, name=label,
            line={"color": STRATEGY_BLUE, "width": 2},
        ),
        go.Scatter(
            x=result.benchmark.index, y=result.benchmark.values, name="Buy and hold",
            line={"color": BH_GRAY, "width": 2},
        ),
        go.Scatter(
            x=buys.index, y=result.equity.reindex(buys.index), mode="markers",
            name="Buy (next open)",
            marker={"symbol": "triangle-up", "color": GAIN_GREEN, "size": 10},
        ),
        go.Scatter(
            x=sells.index, y=result.equity.reindex(sells.index), mode="markers",
            name="Sell (next open)",
            marker={"symbol": "triangle-down", "color": LOSS_RED, "size": 10},
        ),
    ]
    fig = go.Figure(data=traces)
    fig.update_layout(yaxis_title="Growth of $1", hovermode="x unified")
    return fig


def heatmap_figure(hm: HeatmapResult, selected_short: int, selected_long: int) -> go.Figure:
    """The LAB-05 short x long excess-return heatmap (D-06, D-07). No click-to-select — the
    selected rule is a static marker overlay driven by the sidebar picker, not a chart
    click handler (RESEARCH Pitfall 2)."""
    traces = [
        go.Heatmap(
            z=(hm.excess * 100).to_numpy(),
            x=list(hm.excess.columns),
            y=list(hm.excess.index),
            colorscale=DIVERGING_COLORSCALE,
            zmid=0,
            colorbar={"title": "Excess vs B&H (pp)"},
            hovertemplate="Short %{y} × Long %{x}: %{z:.1f} pp<extra></extra>",
            name="",
        ),
        go.Scatter(
            x=[selected_long], y=[selected_short], mode="markers", name="Selected rule",
            marker={"symbol": "square-open", "size": 18, "line": {"color": "black", "width": 2}},
        ),
    ]
    fig = go.Figure(data=traces)
    fig.update_layout(xaxis_title="Long MA period", yaxis_title="Short MA period")
    return fig


def scatter_figure(grid: pd.DataFrame, selected_name: str) -> go.Figure:
    """The LAB-08 CAGR vs max-drawdown scatter: the 24 notebook rules plus buy-and-hold
    (D-08), consistent with the headline grid."""
    sizes = [
        _SELECTED_MARKER_SIZE if name == selected_name else _RULE_MARKER_SIZE
        for name in grid.index
    ]
    traces = [
        go.Scatter(
            x=grid["max_drawdown"] * 100, y=grid["cagr"] * 100, mode="markers",
            text=list(grid.index), name="Notebook rules",
            marker={"color": STRATEGY_BLUE, "size": sizes},
            hovertemplate="%{text}<br>Max drawdown %{x:.1f}%, CAGR %{y:.1f}%<extra></extra>",
        ),
        go.Scatter(
            x=[grid["bh_max_drawdown"].iloc[0] * 100], y=[grid["bh_cagr"].iloc[0] * 100],
            mode="markers", name="Buy and hold",
            marker={"color": BH_GRAY, "size": 12, "symbol": "diamond"},
            hovertemplate="Buy and hold<br>Max drawdown %{x:.1f}%, CAGR %{y:.1f}%<extra></extra>",
        ),
    ]
    fig = go.Figure(data=traces)
    fig.update_layout(xaxis_title="Max drawdown (%)", yaxis_title="CAGR (%)")
    return fig


def rolling_figure(df: pd.DataFrame) -> go.Figure:
    """The LAB-06 rolling-start chart: excess total return per start year (D-11)."""
    colors = [GAIN_GREEN if v > 0 else LOSS_RED for v in df["excess"]]
    fig = go.Figure(
        data=[go.Bar(x=df.index.year, y=df["excess"] * 100, marker={"color": colors},
                     name="Excess vs B&H")]
    )
    fig.update_layout(xaxis_title="Start year", yaxis_title="Excess total return vs B&H (pp)")
    return fig


def _is_nan(value: object) -> bool:
    try:
        return bool(math.isnan(float(value)))
    except (TypeError, ValueError):
        return False


def format_metrics(table: pd.DataFrame) -> pd.DataFrame:
    """Format the metrics_table() output as display strings, nan as 'n/a'."""
    out = table.astype(object).copy()
    for row in out.index:
        if row in _PERCENT_ROWS:
            out.loc[row] = [
                "n/a" if _is_nan(v) else f"{float(v):.1%}" for v in out.loc[row]
            ]
        elif row in _RATIO_ROWS:
            out.loc[row] = [
                "n/a" if _is_nan(v) else f"{float(v):.2f}" for v in out.loc[row]
            ]
        elif row == "Trades":
            out.loc[row] = [
                "n/a" if _is_nan(v) else str(int(v)) for v in out.loc[row]
            ]
    return out
