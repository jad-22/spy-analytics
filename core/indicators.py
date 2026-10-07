"""Moving averages.

Fix vs the 2022 notebook: `Series.ewm(period)` sets the centre of mass, so the old
"10-day EMA" was really ~21 days. EMAs here use `span=n`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=n).mean()


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False, min_periods=n).mean()


@dataclass(frozen=True)
class MASpec:
    kind: Literal["sma", "ema"]
    period: int

    @property
    def label(self) -> str:
        return f"{self.kind}{self.period}"

    def compute(self, series: pd.Series) -> pd.Series:
        fn = sma if self.kind == "sma" else ema
        return fn(series, self.period).rename(self.label)


def add_mas(df: pd.DataFrame, specs: list[MASpec], col: str = "close") -> pd.DataFrame:
    out = df.copy()
    for spec in specs:
        out[spec.label] = spec.compute(df[col])
    return out
