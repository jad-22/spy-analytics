"""Pre-write validation gate for the nightly price refresh (DATA-03, D-13).

No Streamlit import, no network call. Every failure mode raises ValueError with a
descriptive message so jobs/refresh_prices.py can print it and exit non-zero,
leaving the last committed snapshot untouched.
"""
from __future__ import annotations

import pandas as pd

from core.config import Settings
from core.market_calendar import nyse_sessions

_REWRITE_COLUMNS = ("open", "high", "low", "close", "volume")


def validate_snapshot(new: pd.DataFrame, old: pd.DataFrame | None, cfg: Settings) -> None:
    """Raise ValueError if `new` fails any D-13 check against `old`. No-op on success."""
    if old is not None:
        if len(new) < len(old):
            raise ValueError(f"row count shrank from {len(old)} to {len(new)}")
        if new.index[-1] < old.index[-1]:
            raise ValueError("last date moved back")

        overlap = old.index.intersection(new.index)
        for col in _REWRITE_COLUMNS:
            if col == "volume":
                rows = overlap[old.loc[overlap, "volume"] > 0]
            else:
                rows = overlap
            if len(rows) == 0:
                continue
            ratio = (new.loc[rows, col] / old.loc[rows, col] - 1).abs()
            bad = ratio[ratio > cfg.rewrite_tolerance_pct]
            if len(bad):
                raise ValueError(
                    f"{col} rewritten beyond tolerance on {len(bad)} rows, "
                    f"first {bad.index[0].date()}"
                )

        adj_ratio = (new.loc[overlap, "adj_close"] / old.loc[overlap, "adj_close"]).dropna()
        if len(adj_ratio) and (adj_ratio.max() / adj_ratio.min() - 1) > cfg.adj_close_factor_tolerance_pct:
            raise ValueError("adj_close restated by more than a single common factor")

    missing = nyse_sessions(new.index[0], new.index[-1]).difference(new.index)
    if len(missing):
        first_ten = [str(d.date()) for d in missing[:10]]
        raise ValueError(f"missing session(s): {first_ten}")


def drop_incomplete_session(df: pd.DataFrame, now_utc: pd.Timestamp, cfg: Settings) -> pd.DataFrame:
    """Drop today's bar if fetched before cfg.session_complete_after_et (US/Eastern)."""
    now_et = now_utc.tz_convert("America/New_York")
    last_date = df.index[-1]
    if last_date.date() != now_et.date():
        return df

    complete_time = pd.Timestamp(
        f"{now_et.date()} {cfg.session_complete_after_et}"
    ).tz_localize("America/New_York")
    if now_et < complete_time:
        return df.iloc[:-1]
    return df
