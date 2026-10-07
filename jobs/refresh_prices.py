"""Nightly SPY price refresh: fetch, retry, write the committed snapshot.

Usage:
    python -m jobs.refresh_prices
    python -m jobs.refresh_prices --retry-wait-max 5

On any failure after retries, this prints an error to stderr and exits 1 without
touching data/ — the last committed snapshot stays in place (D-16, D-17).
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from tenacity import Retrying, stop_after_attempt, wait_exponential

from core.config import SETTINGS
from core.data import fetch_yfinance, write_prices
from core.storage import build_meta, write_meta


def fetch_with_retry(
    ticker: str, start: str, attempts: int, wait_min_s: float, wait_max_s: float
) -> pd.DataFrame:
    """Fetch SPY prices, retrying transient failures with exponential backoff."""

    def _log_retry(retry_state) -> None:
        exc = retry_state.outcome.exception()
        print(
            f"price fetch attempt {retry_state.attempt_number} failed: {exc}",
            file=sys.stderr,
        )

    retryer = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=wait_min_s, max=wait_max_s),
        reraise=True,
        before_sleep=_log_retry,
    )
    # Calls the module-level name so tests can monkeypatch jobs.refresh_prices.fetch_yfinance.
    return retryer(fetch_yfinance, ticker, start=start)


def _write_snapshot(df: pd.DataFrame, prices_path: Path, meta_path: Path) -> None:
    """Single call site for the write path. Plan 02 inserts the D-13 validation gate here."""
    write_prices(df, prices_path)
    write_meta(
        build_meta(
            df,
            ticker=SETTINGS.ticker,
            refreshed_at=datetime.now(UTC),
            detector_version=SETTINGS.detector_version,
            schema_version=SETTINGS.meta_schema_version,
        ),
        meta_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices-path", default=str(SETTINGS.prices_path))
    parser.add_argument("--meta-path", default=str(SETTINGS.meta_path))
    parser.add_argument("--retry-wait-max", type=float, default=SETTINGS.fetch_wait_max_s)
    args = parser.parse_args(argv)

    wait_max = args.retry_wait_max
    wait_min = 0.0 if wait_max <= 0 else SETTINGS.fetch_wait_min_s

    try:
        df = fetch_with_retry(
            SETTINGS.ticker, SETTINGS.history_start, SETTINGS.fetch_attempts, wait_min, wait_max
        )
    except Exception as exc:  # noqa: BLE001 - final-retry exhaustion, keep last snapshot
        print(f"price refresh failed: {exc}; keeping last snapshot", file=sys.stderr)
        return 1

    _write_snapshot(df, Path(args.prices_path), Path(args.meta_path))
    print(
        f"wrote {len(df)} rows ({df.index[0].date()} to {df.index[-1].date()}) "
        f"to {args.prices_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
