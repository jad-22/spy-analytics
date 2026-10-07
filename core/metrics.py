"""Performance metrics on an equity curve (value series, any base)."""
from __future__ import annotations

import math

import pandas as pd

from core.backtest import BacktestResult

TRADING_DAYS = 252


def total_return(equity: pd.Series) -> float:
    return float(equity.iloc[-1] / equity.iloc[0] - 1)


def cagr(equity: pd.Series) -> float:
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return float("nan")
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1).min())


def sharpe(equity: pd.Series, rf_annual: float = 0.0) -> float:
    r = equity.pct_change().dropna() - rf_annual / TRADING_DAYS
    sd = r.std()
    return float(r.mean() / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else float("nan")


def summarise(result: BacktestResult) -> dict[str, float]:
    s, b = result.equity, result.benchmark
    return {
        "total_return": total_return(s),
        "cagr": cagr(s),
        "max_drawdown": max_drawdown(s),
        "sharpe": sharpe(s),
        "time_in_market": float(result.exposure.mean()),
        "fills": len(result.trades),
        "bh_total_return": total_return(b),
        "bh_cagr": cagr(b),
        "bh_max_drawdown": max_drawdown(b),
        "excess_total_return": total_return(s) - total_return(b),
        "excess_cagr": cagr(s) - cagr(b),
    }
