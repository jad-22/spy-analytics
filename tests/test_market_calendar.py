from __future__ import annotations

import warnings

import pandas as pd
import pytest

from core.config import SETTINGS
from core.market_calendar import nyse_holidays, nyse_sessions
from core.storage import load_prices

INCLUDED_HOLIDAYS = [
    "2024-07-04",  # Independence Day
    "2024-11-28",  # Thanksgiving
    "2024-03-29",  # Good Friday
    "2022-06-20",  # Juneteenth observed (2022-06-19 fell on a Sunday)
    "2001-09-11",  # September 11
    "2001-09-12",  # September 11
    "2001-09-13",  # September 11
    "2001-09-14",  # September 11
    "2012-10-29",  # Hurricane Sandy
    "2012-10-30",  # Hurricane Sandy
    "2018-12-05",  # G.H.W. Bush funeral
    "2025-01-09",  # Carter funeral
]

EXCLUDED_DATES = [
    "2021-12-31",  # NYSE does not observe New Year on the prior Friday
    "2021-06-18",  # Juneteenth not yet a market holiday
    "1997-01-20",  # MLK Day added to the NYSE calendar in 1998
]


@pytest.mark.parametrize("date", INCLUDED_HOLIDAYS)
def test_nyse_holidays_includes(date):
    holidays = nyse_holidays("1993-01-01", "2026-12-31")
    assert pd.Timestamp(date) in holidays


@pytest.mark.parametrize("date", EXCLUDED_DATES)
def test_nyse_holidays_excludes(date):
    holidays = nyse_holidays("1993-01-01", "2026-12-31")
    assert pd.Timestamp(date) not in holidays


def test_nyse_sessions_christmas_week_2024():
    sessions = nyse_sessions("2024-12-23", "2024-12-27")
    expected = pd.DatetimeIndex(["2024-12-23", "2024-12-24", "2024-12-26", "2024-12-27"])
    pd.testing.assert_index_equal(sessions, expected)


def test_committed_snapshot_has_no_missing_sessions():
    df = load_prices(SETTINGS.prices_path)
    sessions = nyse_sessions(df.index[0], df.index[-1])

    missing = sessions.difference(df.index)
    assert len(missing) == 0, f"missing NYSE sessions in committed snapshot: {list(missing)}"

    extra = pd.DatetimeIndex(df.index).difference(sessions)
    if len(extra):
        warnings.warn(
            f"committed snapshot has {len(extra)} date(s) that are not NYSE sessions: "
            f"{[str(d.date()) for d in extra]}",
            stacklevel=1,
        )
