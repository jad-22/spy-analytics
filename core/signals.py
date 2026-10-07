"""Signal rules. Every function returns a *target exposure* decided at the close of each day:
1.0 = hold SPY, 0.0 = hold cash, NaN = not enough history yet.

Fix vs the 2022 notebook: the old crossover test compared against tomorrow's moving
average (look-ahead). Here a target on day t uses only data up to and including day t.
"""
from __future__ import annotations

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
