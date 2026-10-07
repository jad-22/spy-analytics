"""Vectorised long/cash backtest.

Conventions (fixes the 2022 notebook's value-tracking bugs):
- target[t] is decided with information up to the close of day t.
- It is executed at the open of day t+1 (no look-ahead, realistic fill).
- Interval i runs from open[i] to open[i+1]; exposure during interval i is target[i-1].
- equity[d] is portfolio value at the open of date d, starting at 1.0 on the entry date.
- Value changes only while invested; cash earns 0 (a cash-yield option can come later).
- cost_bps is charged on each unit of turnover (entry or exit), one way.
- The benchmark (buy and hold) uses exactly the same window, fills and entry cost.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    equity: pd.Series
    benchmark: pd.Series
    exposure: pd.Series  # exposure per interval, indexed by interval start date
    trades: pd.DataFrame  # one row per fill: side, fill_price
    cost_bps: float


def _relabel_to_next_open(values: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Value after interval i is measured at open[i+1]; label it with that date."""
    next_date = pd.Series(index[1:], index=index[:-1])
    out = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(next_date.loc[values.index]))
    start = pd.Series([1.0], index=pd.DatetimeIndex([values.index[0]]))
    out = pd.concat([start, out])
    out.index.name = "date"
    return out


def run_backtest(prices: pd.DataFrame, target: pd.Series, cost_bps: float = 0.0,
                 start: str | pd.Timestamp | None = None,
                 end: str | pd.Timestamp | None = None) -> BacktestResult:
    open_ = prices["open"]
    interval_ret = open_.shift(-1) / open_ - 1
    exposure = target.reindex(prices.index).shift(1)

    df = pd.DataFrame({"r": interval_ret, "exp": exposure}).loc[start:end].dropna()
    if df.empty:
        raise ValueError("No overlapping data between prices and target in the window")

    cost = cost_bps / 1e4
    delta = df["exp"].diff()
    delta.iloc[0] = df["exp"].iloc[0]  # entering from cash on day one
    turnover = delta.abs()
    strat_ret = df["exp"] * df["r"] - turnover * cost

    bench_turnover = pd.Series(0.0, index=df.index)
    bench_turnover.iloc[0] = 1.0
    bench_ret = df["r"] - bench_turnover * cost

    equity = _relabel_to_next_open((1 + strat_ret).cumprod(), prices.index).rename("strategy")
    benchmark = _relabel_to_next_open((1 + bench_ret).cumprod(), prices.index).rename(
        "buy_and_hold"
    )

    fills = delta[delta != 0]
    trades = pd.DataFrame(
        {
            "side": ["buy" if d > 0 else "sell" for d in fills],
            "fill_price": open_.loc[fills.index].to_numpy(),
        },
        index=pd.DatetimeIndex(fills.index, name="date"),
    )
    return BacktestResult(equity, benchmark, df["exp"].rename("exposure"), trades, cost_bps)
