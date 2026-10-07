"""Price loading and storage.

yfinance is the only price source (the Stooq fallback was removed: pandas-datareader
dropped its Stooq reader, and Stooq's own endpoint now requires a CAPTCHA-gated API key,
per D-17). Network calls live here and are only used by jobs/scripts, never by the
Streamlit app. A failed refresh keeps the last committed snapshot — see
jobs/refresh_prices.py. The app reads the committed parquet snapshot through
`core.storage` (which wraps `read_prices` below).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]


def _finalise(df: pd.DataFrame, source: str) -> pd.DataFrame:
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index.name = "date"
    df = df[COLUMNS].sort_index()
    df = df[~df.index.duplicated(keep="last")].dropna(subset=["open", "close"])
    df.attrs["source"] = source
    return df


def fetch_yfinance(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    """Daily OHLCV plus dividend/split-adjusted close from Yahoo Finance."""
    import yfinance as yf

    raw = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if raw is None or raw.empty:
        raise ValueError(f"yfinance returned no rows for {ticker}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(
        columns={
            "Open": "open", "High": "high", "Low": "low", "Close": "close",
            "Adj Close": "adj_close", "Volume": "volume",
        }
    )
    return _finalise(raw, "yfinance")


def to_total_return(df: pd.DataFrame) -> pd.DataFrame:
    """Scale OHLC by adj_close/close so returns include dividends.

    Backtests should use this frame so buy-and-hold is not understated.
    """
    factor = df["adj_close"] / df["close"]
    out = df.copy()
    for col in ("open", "high", "low", "close"):
        out[col] = df[col] * factor
    return out


def write_prices(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["source"] = df.attrs.get("source", "unknown")
    out.to_parquet(path)


def read_prices(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    source = df["source"].iloc[-1] if "source" in df.columns else "unknown"
    df = df.drop(columns=["source"], errors="ignore")
    df.attrs["source"] = source
    return df
