"""Event detection: turn the committed data/prices.parquet into data/episodes.parquet.

Usage:
    python -m jobs.detect_events

Reads prices on the total-return basis (so ex-dividend days don't masquerade as gaps or
shocks, per CLAUDE.md's honesty rule), calls the pure core.events.detect, tags each
episode with in-window macro releases via core.calendar.tag_episodes (CAL-02), and
writes the episode backfill. No network call -- this job only reads committed data (the
calendar is built separately, locally, by jobs/build_macro_calendar.py). On any
detection or tagging failure, or if the macro calendar is missing, this prints to
stderr and exits 1 without touching data/.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from core.calendar import tag_episodes
from core.config import SETTINGS
from core.events import detect
from core.storage import (
    load_macro_calendar,
    load_meta,
    load_prices,
    price_basis,
    write_episodes,
    write_meta,
)


def _write_episodes(df: pd.DataFrame, episodes_path: Path, meta: dict, meta_path: Path) -> None:
    """Single call site for the write path. Caller loads meta first, so a missing or
    corrupt meta.json fails before anything is written."""
    write_episodes(df, episodes_path)
    meta["detector_version"] = SETTINGS.detector_version
    write_meta(meta, meta_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices-path", default=str(SETTINGS.prices_path))
    parser.add_argument("--episodes-path", default=str(SETTINGS.episodes_path))
    parser.add_argument("--meta-path", default=str(SETTINGS.meta_path))
    parser.add_argument("--calendar-path", default=str(SETTINGS.macro_calendar_path))
    args = parser.parse_args(argv)

    try:
        raw = load_prices(Path(args.prices_path))
        meta = load_meta(Path(args.meta_path))
    except (OSError, ValueError) as exc:
        print(f"episode detection failed: {exc}", file=sys.stderr)
        return 1

    try:
        calendar = load_macro_calendar(Path(args.calendar_path))
    except FileNotFoundError:
        print(
            f"macro calendar missing at {args.calendar_path}; run jobs.build_macro_calendar "
            "locally (needs FRED_API_KEY)",
            file=sys.stderr,
        )
        return 1

    try:
        prices = price_basis(raw, "total_return")
        df = tag_episodes(detect(prices, SETTINGS), calendar)
    except ValueError as exc:
        print(f"episode detection failed: {exc}", file=sys.stderr)
        return 1

    if df.empty:
        print("episode detection failed: zero episodes detected", file=sys.stderr)
        return 1

    lo, hi = SETTINGS.episode_count_bounds
    if not lo <= len(df) <= hi:
        print(
            f"WARNING: episode count {len(df)} outside expected bounds ({lo}, {hi})",
            file=sys.stderr,
        )

    _write_episodes(df, Path(args.episodes_path), meta, Path(args.meta_path))
    print(
        f"wrote {len(df)} episodes ({df['start_date'].iloc[0].date()} to "
        f"{df['end_date'].iloc[-1].date()}) to {args.episodes_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
