"""Macro-release calendar builder: FOMC/CPI/payrolls dates from 1993 (CAL-01).

Usage:
    FRED_API_KEY=... python -m jobs.build_macro_calendar
    FRED_API_KEY=... python -m jobs.build_macro_calendar --retry-wait-max 5

There is deliberately NO --api-key argument (D-02): the key is read only from the
FRED_API_KEY environment variable so it never ends up in shell history. On any
failure this prints an error to stderr and exits 1 without touching data/ -- the last
committed calendar stays in place (D-03).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from tenacity import Retrying, stop_after_attempt, wait_exponential

from core.calendar import (
    CALENDAR_COLUMNS,
    drop_non_release_dates,
    merge_calendar,
    parse_fomc_calendars,
    parse_fomc_historical,
    parse_fred_release_dates,
    validate_macro_calendar,
)
from core.config import SETTINGS
from core.data import fetch_fred_release_dates, fetch_fred_release_name, fetch_text
from core.storage import load_macro_calendar, write_macro_calendar


def _retryer(attempts: int, wait_min_s: float, wait_max_s: float) -> Retrying:
    def _log_retry(retry_state) -> None:
        exc = retry_state.outcome.exception()
        print(
            f"macro calendar fetch attempt {retry_state.attempt_number} failed: {exc}",
            file=sys.stderr,
        )

    return Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=wait_min_s, max=wait_max_s),
        reraise=True,
        before_sleep=_log_retry,
    )


def _write_calendar(df: pd.DataFrame, calendar_path: Path) -> None:
    """Single call site for the write path. Caller must validate before calling this."""
    write_macro_calendar(df, calendar_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calendar-path", default=str(SETTINGS.macro_calendar_path))
    parser.add_argument("--retry-wait-max", type=float, default=SETTINGS.fetch_wait_max_s)
    parser.add_argument(
        "--today", default=pd.Timestamp.now(tz="US/Eastern").strftime("%Y-%m-%d")
    )
    args = parser.parse_args(argv)

    wait_max = args.retry_wait_max
    wait_min = 0.0 if wait_max <= 0 else SETTINGS.fetch_wait_min_s
    retryer = _retryer(SETTINGS.fetch_attempts, wait_min, wait_max)
    today = pd.Timestamp(args.today)
    calendar_path = Path(args.calendar_path)

    key = os.environ.get(SETTINGS.fred_api_key_env, "")
    if not key:
        print(
            f"{SETTINGS.fred_api_key_env} is not set; set it in your local shell "
            "(never commit it)",
            file=sys.stderr,
        )
        return 1

    try:
        calendars_html = retryer(fetch_text, SETTINGS.fomc_calendars_url, SETTINGS.http_timeout_s)
        calendars_df = parse_fomc_calendars(calendars_html, SETTINGS.fomc_calendars_url)
        first_cal_year = int(calendars_df["date"].dt.year.min())

        historical_frames = [calendars_df]
        last_historical_year = min(first_cal_year - 1, today.year)
        for year in range(pd.Timestamp(SETTINGS.calendar_start).year, last_historical_year + 1):
            url = SETTINGS.fomc_historical_url_template.format(year=year)
            html = retryer(fetch_text, url, SETTINGS.http_timeout_s)
            historical_frames.append(
                parse_fomc_historical(html, year, url, SETTINGS.fomc_non_decision_meetings)
            )

        fred_frames = []
        for label, release_id, expected_name in SETTINGS.fred_releases:
            name = retryer(
                fetch_fred_release_name, release_id, key, SETTINGS.fred_api_url,
                SETTINGS.http_timeout_s,
            )
            if expected_name not in name:
                print(
                    f"release_id {release_id} is '{name}', expected '{expected_name}'",
                    file=sys.stderr,
                )
                return 1
            print(f"FRED release_id {release_id} = {name}")

            payload = retryer(
                fetch_fred_release_dates, release_id, key, SETTINGS.calendar_start,
                SETTINGS.fred_api_url, SETTINGS.http_timeout_s,
            )
            kept, dropped = drop_non_release_dates(
                parse_fred_release_dates(payload, label, release_id, SETTINGS.fred_source_url_template),
                SETTINGS.fred_non_release_dates,
            )
            if len(dropped):
                print(f"{label}: dropped {len(dropped)} listed non-print date(s)")
            fred_frames.append(kept)

        fresh = pd.concat(historical_frames + fred_frames, ignore_index=True)[CALENDAR_COLUMNS]
        fresh = fresh[fresh["date"] >= pd.Timestamp(SETTINGS.calendar_start)]
        horizon = today + pd.Timedelta(days=SETTINGS.calendar_horizon_days)
        fresh = fresh[fresh["date"] <= horizon]
        fresh = fresh.reset_index(drop=True)

        existing = load_macro_calendar(calendar_path) if calendar_path.exists() else None
        merged = merge_calendar(existing, fresh, today)
        validate_macro_calendar(merged, SETTINGS, today)
    except Exception as exc:  # noqa: BLE001 - any failure keeps the last calendar
        print(f"macro calendar build failed: {exc}; keeping last calendar", file=sys.stderr)
        return 1

    if existing is None:
        added, removed = len(merged), 0
    else:
        existing_keys = set(zip(existing["date"], existing["release"], strict=False))
        merged_keys = set(zip(merged["date"], merged["release"], strict=False))
        added = len(merged_keys - existing_keys)
        removed = len(existing_keys - merged_keys)

    _write_calendar(merged, calendar_path)

    for label in ("FOMC", *(r[0] for r in SETTINGS.fred_releases)):
        rows = merged[merged["release"] == label]
        if len(rows):
            print(
                f"{label}: {len(rows)} rows, {rows['date'].min().date()} to "
                f"{rows['date'].max().date()}"
            )
    print(f"added {added} / removed {removed} future rows vs existing")
    print(f"wrote {len(merged)} rows to {calendar_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
