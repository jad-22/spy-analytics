"""Pure read/write layer for data/ files: prices.parquet and meta.json.

No Streamlit import. The app adds caching on top of this module in
app/components/store.py.
"""
from __future__ import annotations

import json
import os
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


def load_episodes(path: Path) -> pd.DataFrame:
    """Read the committed episode backfill. Lets FileNotFoundError propagate."""
    return pd.read_parquet(path)


def _write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    """Write to a temporary sibling, then rename over `path`, so an interrupted run never
    leaves a truncated committed file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def write_episodes(df: pd.DataFrame, path: Path) -> None:
    """Write the episode backfill. Single call site: jobs/detect_events.py."""
    _write_parquet_atomic(df, path)


def load_macro_calendar(path: Path) -> pd.DataFrame:
    """Read the committed macro calendar. Lets FileNotFoundError propagate."""
    return pd.read_parquet(path)


def write_macro_calendar(df: pd.DataFrame, path: Path) -> None:
    """Write the macro calendar. Single call site: jobs/build_macro_calendar.py."""
    _write_parquet_atomic(df, path)


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


def write_json_atomic(obj: object, path: Path) -> None:
    """Write any JSON-serialisable object to a temporary sibling, then rename over
    `path`, so an interrupted run never leaves a truncated committed file. Pretty-printed
    and key-sorted for stable diffs (news enrichment's events.json / event_overrides.json
    / enrichment_spend.json, NEWS-05..07)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n")
    os.replace(tmp, path)


def load_events(path: Path, missing_ok: bool = False) -> list[dict]:
    """Read the committed events.json "records" list. If `missing_ok`, a missing file
    returns [] instead of raising FileNotFoundError."""
    path = Path(path)
    if missing_ok and not path.exists():
        return []
    return json.loads(path.read_text())["records"]


def write_events(records: list[dict], path: Path) -> None:
    """Write data/events.json, sorted by episode_id for stable diffs. Single call site:
    jobs/enrich_events.py."""
    sorted_records = sorted(records, key=lambda r: r["episode_id"])
    write_json_atomic({"schema_version": 1, "records": sorted_records}, path)


def load_spend_ledger(path: Path) -> list[dict]:
    """Read the committed enrichment spend ledger's "runs" list. [] if missing."""
    path = Path(path)
    if not path.exists():
        return []
    return json.loads(path.read_text())["runs"]


def write_spend_ledger(entries: list[dict], path: Path) -> None:
    """Write data/enrichment_spend.json. Single call site: jobs/enrich_events.py."""
    write_json_atomic({"schema_version": 1, "runs": entries}, path)
