"""Price loading and storage, plus FOMC/FRED fetchers for the macro calendar (CAL-01).

yfinance is the only price source (the Stooq fallback was removed: pandas-datareader
dropped its Stooq reader, and Stooq's own endpoint now requires a CAPTCHA-gated API key,
per D-17). Network calls live here and are only used by jobs/scripts, never by the
Streamlit app. A failed refresh keeps the last committed snapshot — see
jobs/refresh_prices.py. The app reads the committed parquet snapshot through
`core.storage` (which wraps `read_prices` below).

`fetch_text`/`fetch_fred_release_dates`/`fetch_fred_release_name` are used only by
jobs/build_macro_calendar.py. Per D-02 the FRED API key is read from an environment
variable by the job and passed in here as a parameter -- never logged, never put in a
URL that gets echoed, never included in an exception message (T-02-09/T-02-10).
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


def fetch_text(url: str, timeout: float) -> str:
    """GET a public URL and return its body as text. Raises on any non-200 response."""
    import requests

    resp = requests.get(url, timeout=timeout)
    if resp.status_code != 200:
        raise ValueError(f"GET {url} returned HTTP {resp.status_code}")
    return resp.text


def fetch_fred_release_dates(
    release_id: int, api_key: str, start: str, base_url: str, timeout: float
) -> dict:
    """Scheduled FRED release dates for one release_id, from `start` onward.

    Never calls resp.raise_for_status() and never includes resp.url or the request
    params in an exception message -- the api_key must not leak into any error text
    (D-02, T-02-09).
    """
    import requests

    if not api_key:
        raise ValueError("FRED api_key is empty")

    params = {
        "release_id": release_id,
        "api_key": api_key,
        "file_type": "json",
        "realtime_start": start,
        "realtime_end": "9999-12-31",
        "include_release_dates_with_no_data": "true",
        "sort_order": "asc",
        "limit": 10000,
    }
    try:
        resp = requests.get(f"{base_url}/release/dates", params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise ValueError(
            f"FRED request failed for release_id={release_id}: {type(exc).__name__}"
        ) from None

    if resp.status_code != 200:
        raise ValueError(f"FRED returned HTTP {resp.status_code} for release_id={release_id}")
    return resp.json()


def fetch_fred_release_name(release_id: int, api_key: str, base_url: str, timeout: float) -> str:
    """The human-readable name FRED has on file for release_id (RESEARCH A1 confirmation)."""
    import requests

    if not api_key:
        raise ValueError("FRED api_key is empty")

    params = {"release_id": release_id, "api_key": api_key, "file_type": "json"}
    try:
        resp = requests.get(f"{base_url}/release", params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise ValueError(
            f"FRED request failed for release_id={release_id}: {type(exc).__name__}"
        ) from None

    if resp.status_code != 200:
        raise ValueError(f"FRED returned HTTP {resp.status_code} for release_id={release_id}")
    return resp.json()["releases"][0]["name"]
