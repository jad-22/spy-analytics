"""Price loading and storage.

Network calls live here and are only used by jobs/scripts, never by the Streamlit app.
The app reads the committed parquet snapshot through `read_prices`.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

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


def fetch_stooq(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    """Fallback source. Stooq's series is treated as already adjusted (adj_close = close).

    Verify this assumption against yfinance before relying on Stooq for total-return work.
    """
    url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    raw = pd.read_csv(io.StringIO(resp.text), parse_dates=["Date"], index_col="Date")
    if raw.empty or "Close" not in raw.columns:
        raise ValueError(f"Stooq returned no usable rows for {ticker}")
    raw = raw.rename(columns=str.lower)
    raw["adj_close"] = raw["close"]
    raw = raw.loc[start:end] if end else raw.loc[start:]
    return _finalise(raw, "stooq")


def load_prices(ticker: str, start: str, end: str | None = None,
                sources: tuple[str, ...] = ("yfinance", "stooq")) -> pd.DataFrame:
    """Try each source in order and return the first that works."""
    fetchers = {"yfinance": fetch_yfinance, "stooq": fetch_stooq}
    errors = []
    for name in sources:
        try:
            return fetchers[name](ticker, start, end)
        except Exception as exc:  # noqa: BLE001 - try the next source
            errors.append(f"{name}: {exc}")
    raise RuntimeError("All price sources failed: " + "; ".join(errors))


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
