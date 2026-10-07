"""Run many MA crossover rules on one common window, and test robustness to start date."""
from __future__ import annotations

from itertools import product

import pandas as pd

from core.backtest import run_backtest
from core.indicators import MASpec
from core.metrics import summarise
from core.signals import ma_crossover


def default_pairs(short_periods=(10, 20, 50), long_periods=(100, 200),
                  kinds=("sma", "ema")) -> list[tuple[MASpec, MASpec]]:
    """Same 24 combinations as the 2022 notebook."""
    shorts = [MASpec(k, p) for k in kinds for p in short_periods]
    longs = [MASpec(k, p) for k in kinds for p in long_periods]
    return list(product(shorts, longs))


def run_ma_grid(prices: pd.DataFrame, pairs: list[tuple[MASpec, MASpec]], cost_bps: float = 0.0,
                start=None, end=None) -> pd.DataFrame:
    """All rules share the window that starts once the slowest MA is available.

    Exposure lags the target by one bar, so the first interval every rule can trade is the
    bar *after* the slowest target becomes valid.
    """
    targets = {f"{s.label}__{lg.label}": ma_crossover(prices["close"], s, lg) for s, lg in pairs}
    last_first_valid = max(t.first_valid_index() for t in targets.values())
    common_start = prices.index[prices.index.get_loc(last_first_valid) + 1]
    if start is not None:
        common_start = max(common_start, pd.Timestamp(start))
    rows = {}
    for name, target in targets.items():
        res = run_backtest(prices, target, cost_bps=cost_bps, start=common_start, end=end)
        rows[name] = summarise(res)
    return pd.DataFrame(rows).T.sort_values("excess_total_return", ascending=False)


def rolling_start(prices: pd.DataFrame, short: MASpec, long: MASpec, horizon_years: int = 5,
                  freq: str = "YS", cost_bps: float = 0.0) -> pd.DataFrame:
    """Excess return of one rule for every start date (default yearly) over a fixed horizon."""
    target = ma_crossover(prices["close"], short, long)
    first = target.first_valid_index()
    last = prices.index[-1] - pd.DateOffset(years=horizon_years)
    rows = []
    for s in pd.date_range(first, last, freq=freq):
        e = s + pd.DateOffset(years=horizon_years)
        m = summarise(run_backtest(prices, target, cost_bps=cost_bps, start=s, end=e))
        rows.append({"start": s, "end": e, "strategy": m["total_return"],
                     "buy_and_hold": m["bh_total_return"], "excess": m["excess_total_return"]})
    return pd.DataFrame(rows).set_index("start")
