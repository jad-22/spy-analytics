"""Pure read/write layer for data/ files: prices.parquet and meta.json.

No Streamlit import. The app adds caching on top of this module in
app/components/store.py.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.data import read_prices, to_total_return

BASES: tuple[str, str] = ("total_return", "price_only")


def load_prices(path: Path) -> pd.DataFrame:
    """Read the committed price snapshot. Lets FileNotFoundError propagate."""
    return read_prices(path)


def load_meta(path: Path) -> dict:
    """Read the committed refresh metadata. Lets FileNotFoundError propagate."""
    return json.loads(Path(path).read_text())


def price_basis(raw: pd.DataFrame, basis: str) -> pd.DataFrame:
    """Return prices on the requested basis: total_return (dividends reinvested) or price_only."""
    if basis == "total_return":
        return to_total_return(raw)
    if basis == "price_only":
        return raw
    raise ValueError(f"Unknown price basis: {basis!r}. Expected one of {BASES}.")


def build_meta(
    prices: pd.DataFrame,
    *,
    ticker: str,
    refreshed_at: datetime,
    detector_version: int,
    schema_version: int,
) -> dict:
    """Build the data/meta.json record for a freshly written price snapshot."""
    last_refresh = refreshed_at.isoformat().replace("+00:00", "Z")
    return {
        "schema_version": schema_version,
        "ticker": ticker,
        "source": prices.attrs.get("source", "unknown"),
        "last_refresh": last_refresh,
        "first_trading_day": str(prices.index[0].date()),
        "last_trading_day": str(prices.index[-1].date()),
        "row_counts": {"prices": len(prices)},
        "detector_version": detector_version,
    }


def write_meta(meta: dict, path: Path) -> None:
    """Write meta.json, pretty-printed and sorted for stable diffs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
