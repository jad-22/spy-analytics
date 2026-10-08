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


def downside_deviation(equity: pd.Series, target: float = 0.0) -> float:
    """Annualised downside deviation, taken over ALL return observations (standard
    convention): positive returns contribute 0 to the squared-deviation average, they are
    not excluded from the count."""
    r = equity.pct_change().dropna() - target / TRADING_DAYS
    return float(math.sqrt((r.clip(upper=0.0) ** 2).mean()) * math.sqrt(TRADING_DAYS))


def sortino(equity: pd.Series, rf_annual: float = 0.0) -> float:
    r = equity.pct_change().dropna() - rf_annual / TRADING_DAYS
    dd = downside_deviation(equity, rf_annual)
    return float(r.mean() * TRADING_DAYS / dd) if dd > 0 else float("nan")


def calmar(equity: pd.Series) -> float:
    mdd = max_drawdown(equity)
    return float(cagr(equity) / abs(mdd)) if mdd < 0 else float("nan")


def summarise(result: BacktestResult) -> dict[str, float]:
    s, b = result.equity, result.benchmark
    return {
        "total_return": total_return(s),
        "cagr": cagr(s),
        "max_drawdown": max_drawdown(s),
        "sharpe": sharpe(s),
        "sortino": sortino(s),
        "calmar": calmar(s),
        "time_in_market": float(result.exposure.mean()),
        "fills": len(result.trades),
        "bh_total_return": total_return(b),
        "bh_cagr": cagr(b),
        "bh_max_drawdown": max_drawdown(b),
        "bh_sharpe": sharpe(b),
        "bh_sortino": sortino(b),
        "bh_calmar": calmar(b),
        "excess_total_return": total_return(s) - total_return(b),
        "excess_cagr": cagr(s) - cagr(b),
    }


def metrics_table(result: BacktestResult) -> pd.DataFrame:
    """7x2 metrics table (strategy vs buy-and-hold) for the Strategy Lab's selected rule."""
    s, b = result.equity, result.benchmark
    rows = {
        "CAGR": (cagr(s), cagr(b)),
        "Max drawdown": (max_drawdown(s), max_drawdown(b)),
        "Sharpe": (sharpe(s), sharpe(b)),
        "Sortino": (sortino(s), sortino(b)),
        "Calmar": (calmar(s), calmar(b)),
        "Time in market": (float(result.exposure.mean()), 1.0),
        "Trades": (len(result.trades), 1),
    }
    return pd.DataFrame(rows, index=["Strategy", "Buy & hold"]).T
