"""Offline validation of the committed data/macro_calendar.parquet (CAL-01).

Runs with no network and no FRED key -- every assertion reads the file Jason built
locally in plan 02-04 and committed. Skipped entirely until that file exists, so this
module collects cleanly even before the live run (Task 2 of 02-04-PLAN.md).
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.calendar import CALENDAR_COLUMNS, validate_macro_calendar
from core.config import SETTINGS
from core.storage import load_macro_calendar

pytestmark = pytest.mark.skipif(
    not SETTINGS.macro_calendar_path.exists(),
    reason="macro calendar not built yet",
)

# Same 8 scheduled 1993 FOMC decision dates asserted against the real
# fomchistorical1993.htm fixture in tests/test_calendar.py and
# tests/test_build_macro_calendar.py -- repeated here (not imported) since this
# module validates the committed artifact independently of those parser-unit tests.
FOMC_1993_SCHEDULED_DATES = [
    "1993-02-03", "1993-03-23", "1993-05-18", "1993-07-07",
    "1993-08-17", "1993-09-21", "1993-11-16", "1993-12-21",
]


@pytest.fixture(scope="module")
def calendar() -> pd.DataFrame:
    return load_macro_calendar(SETTINGS.macro_calendar_path)


def test_columns_match_calendar_columns(calendar: pd.DataFrame) -> None:
    assert list(calendar.columns) == CALENDAR_COLUMNS


def test_validates_against_settings(calendar: pd.DataFrame) -> None:
    # Bound "today" by the last CPI date actually in the file (not wall-clock "today")
    # so CI never time-bombs a year after the calendar was last rebuilt: validate_macro_calendar
    # checks every full year up to today.year - 1 has in-range FOMC/monthly counts, which
    # would start failing on stale data if "today" kept advancing with the real clock.
    last_cpi_date = calendar.loc[calendar["release"] == "CPI", "date"].max()
    today = min(pd.Timestamp.today().normalize(), last_cpi_date)
    validate_macro_calendar(calendar, SETTINGS, today)


def test_all_three_releases_present_from_1993(calendar: pd.DataFrame) -> None:
    assert set(calendar["release"]) == {"FOMC", "CPI", "payrolls"}

    first_release_by = pd.Timestamp(SETTINGS.calendar_first_release_by)
    for label in ("FOMC", "CPI", "payrolls"):
        rows = calendar[calendar["release"] == label]
        assert rows["date"].min() <= first_release_by, (
            f"{label}'s first date {rows['date'].min()} is after {first_release_by}"
        )

    fomc_min = calendar.loc[calendar["release"] == "FOMC", "date"].min()
    assert fomc_min.year == 1993


def test_1993_scheduled_fomc_dates_match_known_fixture(calendar: pd.DataFrame) -> None:
    fomc = calendar[calendar["release"] == "FOMC"]
    scheduled_1993 = (
        fomc[(fomc["date"].dt.year == 1993) & (fomc["scheduled"])]["date"]
        .dt.strftime("%Y-%m-%d")
        .sort_values()
        .tolist()
    )
    assert scheduled_1993 == FOMC_1993_SCHEDULED_DATES


def test_march_2020_emergency_actions_marked_unscheduled(calendar: pd.DataFrame) -> None:
    fomc = calendar[calendar["release"] == "FOMC"]
    march_2020 = fomc[(fomc["date"] >= "2020-03-01") & (fomc["date"] <= "2020-03-31")]

    assert (~march_2020["scheduled"]).any(), "expected at least one unscheduled March 2020 row"

    # The two real emergency-action dates (federalreserve.gov fomchistorical2020.htm:
    # "March 2 (unscheduled)" and "March 15 (unscheduled)") must never be tagged as a
    # scheduled "meeting" row -- the cancelled March 17-18 regular meeting produced no
    # decision at all and is absent from the calendar entirely (see 02-03-SUMMARY.md).
    meeting_dates = set(
        march_2020.loc[march_2020["release_type"] == "meeting", "date"]
        .dt.strftime("%Y-%m-%d")
    )
    assert "2020-03-02" not in meeting_dates
    assert "2020-03-15" not in meeting_dates


def test_no_secret_in_any_source_url(calendar: pd.DataFrame) -> None:
    assert calendar["source_url"].str.startswith("https://").all()
    assert not calendar["source_url"].str.contains("api_key", case=False).any()


def test_sorted_by_date_release_release_type_no_duplicates(calendar: pd.DataFrame) -> None:
    sort_cols = ["date", "release", "release_type"]
    expected = calendar.sort_values(sort_cols).reset_index(drop=True)
    pd.testing.assert_frame_equal(calendar.reset_index(drop=True), expected)
    assert not calendar.duplicated(subset=sort_cols).any()
