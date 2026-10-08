"""Plotly figure builder and metrics formatting for the Strategy Lab (LAB-03, LAB-04)."""
from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from app.components.theme import BH_GRAY, GAIN_GREEN, LOSS_RED, STRATEGY_BLUE
from core.backtest import BacktestResult

_PERCENT_ROWS = ("CAGR", "Max drawdown", "Time in market")
_RATIO_ROWS = ("Sharpe", "Sortino", "Calmar")


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
