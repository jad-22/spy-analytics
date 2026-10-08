"""Signal rules. Every function returns a *target exposure* decided at the close of each day:
1.0 = hold SPY, 0.0 = hold cash, NaN = not enough history yet.

Fix vs the 2022 notebook: the old crossover test compared against tomorrow's moving
average (look-ahead). Here a target on day t uses only data up to and including day t.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd

from core.indicators import MASpec, sma


def crossover_target(short: pd.Series, long: pd.Series) -> pd.Series:
    valid = short.notna() & long.notna()
    return (short > long).astype(float).where(valid)


def ma_crossover(close: pd.Series, short: MASpec, long: MASpec) -> pd.Series:
    return crossover_target(short.compute(close), long.compute(close)).rename(
        f"{short.label}__{long.label}"
    )


def trend_filter(close: pd.Series, period: int = 200) -> pd.Series:
    """In the market only while the close is above its `period`-day SMA."""
    return crossover_target(close, sma(close, period)).rename(f"close__sma{period}")


def combine_all(*targets: pd.Series) -> pd.Series:
    """Long only when every rule says long (logical AND)."""
    df = pd.concat(targets, axis=1)
    name = "__and__".join(t.name or "rule" for t in targets)
    return df.min(axis=1, skipna=False).rename(name)


def crossings(target: pd.Series) -> pd.Series:
    """+1 on days the target flips to long, -1 when it flips to cash (decision dates)."""
    change = target.dropna().diff()
    return change[change != 0].dropna().astype(int)


@runtime_checkable
class Strategy(Protocol):
    """Anything that can plug into the Strategy Lab (LAB-10).

    A Strategy returns a target exposure series per core/backtest.py's conventions: 1.0/0.0/NaN,
    decided at each close, using only data up to and including that day. Never index future
    values. `name` is a short, stable, filesystem/dict-key-safe identifier; `label` is the
    human-readable string shown in the UI.
    """

    name: str
    label: str

    def target(self, prices: pd.DataFrame) -> pd.Series: ...


@dataclass(frozen=True)
class MACrossoverStrategy:
    """Wraps ma_crossover, optionally AND-ed with a trend filter (LAB-01, LAB-10).

    Never reimplements the crossover/trend-filter math — delegates to ma_crossover,
    trend_filter and combine_all exactly as they already exist in this module.
    """

    short: MASpec
    long: MASpec
    trend_filter_period: int | None = None

    @property
    def name(self) -> str:
        base = f"{self.short.label}__{self.long.label}"
        if self.trend_filter_period:
            return f"{base}__trend{self.trend_filter_period}"
        return base

    @property
    def label(self) -> str:
        base = (
            f"{self.short.kind.upper()} {self.short.period} vs "
            f"{self.long.kind.upper()} {self.long.period}"
        )
        if self.trend_filter_period:
            return f"{base} + {self.trend_filter_period}D trend filter"
        return base

    def target(self, prices: pd.DataFrame) -> pd.Series:
        base = ma_crossover(prices["close"], self.short, self.long)
        if self.trend_filter_period:
            filtered = trend_filter(prices["close"], self.trend_filter_period)
            return combine_all(base, filtered).rename(self.name)
        return base.rename(self.name)
