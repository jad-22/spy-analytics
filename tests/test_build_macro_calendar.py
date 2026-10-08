"""Offline job tests for jobs/build_macro_calendar.py (CAL-01).

All network calls are monkeypatched to fixture data captured in tests/fixtures/macro/;
no test here needs a FRED API key or internet access. The sentinel key
"TESTKEY-DO-NOT-LEAK" stands in for FRED_API_KEY and must never appear in any written
file, exception message, or captured stderr (D-02).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from core.storage import load_macro_calendar
from jobs import build_macro_calendar

FIXTURES = Path(__file__).parent / "fixtures" / "macro"
SENTINEL_KEY = "TESTKEY-DO-NOT-LEAK"

# Real decision dates read off tests/fixtures/macro/fomchistorical1993.htm (Task 1):
# header text -> classification:
#   "January 6 Conference Call"   -> unscheduled
#   "February 2-3 Meeting"        -> scheduled, decision date = second day (02-03)
#   "February 18 Conference Call" -> unscheduled
#   "March 1 Conference Call"     -> unscheduled
#   "March 23 Meeting"            -> scheduled
#   "May 18 Meeting"              -> scheduled
#   "July 6-7 Meeting"            -> scheduled, decision date = second day (07-07)
#   "August 17 Meeting"           -> scheduled
#   "September 21 Meeting"        -> scheduled
#   "October 5 Conference Call"   -> unscheduled
#   "October 15 Conference Call"  -> unscheduled
#   "October 22 Conference Call"  -> unscheduled
#   "November 9 Conference Call"  -> unscheduled
#   "November 10 Conference Call" -> unscheduled
#   "November 16 Meeting"         -> scheduled
#   "December 21 Meeting"         -> scheduled
# 8 scheduled "Meeting" rows, 8 unscheduled "Conference Call" rows.
FOMC_1993_SCHEDULED_DATES = [
    "1993-02-03", "1993-03-23", "1993-05-18", "1993-07-07",
    "1993-08-17", "1993-09-21", "1993-11-16", "1993-12-21",
]


def _install_fakes(monkeypatch, tmp_path=None):
    """Monkeypatch build_macro_calendar's fetch_* names to fixture data.

    Historical years 1993/2008/2015/2020 use their real captured fixtures; any other
    year in the 1993..first_calendars_year-1 range (e.g. 1994, 1995, 1996) is a
    synthetic convenience -- it reuses the 2015 fixture text with the year string
    substituted, since 2015's "8 regular meetings, no conference calls" shape is a
    reasonable stand-in and this plan's tests never assert specific dates for those
    synthetic years.
    """
    real_years = {"1993", "2008", "2015", "2020"}
    html_2015 = (FIXTURES / "fomchistorical2015.htm").read_text(encoding="utf-8")
    html_calendars = (FIXTURES / "fomccalendars.htm").read_text(encoding="utf-8")
    fred_10 = json.loads((FIXTURES / "fred_release_dates_10.json").read_text())
    fred_50 = json.loads((FIXTURES / "fred_release_dates_50.json").read_text())

    def fake_fetch_text(url, timeout):
        if "fomccalendars.htm" in url:
            return html_calendars
        for year in real_years:
            if f"fomchistorical{year}.htm" in url:
                return (FIXTURES / f"fomchistorical{year}.htm").read_text(encoding="utf-8")
        # Synthetic convenience year: splice the requested year into the 2015 shape.
        marker = "fomchistorical"
        start = url.index(marker) + len(marker)
        year = url[start : start + 4]
        return html_2015.replace("2015", year)

    def fake_fetch_fred_release_dates(release_id, api_key, start, base_url, timeout):
        assert api_key == SENTINEL_KEY
        assert "api_key" not in base_url
        if release_id == 10:
            return fred_10
        if release_id == 50:
            return fred_50
        raise ValueError(f"unexpected release_id {release_id}")

    def fake_fetch_fred_release_name(release_id, api_key, base_url, timeout):
        assert api_key == SENTINEL_KEY
        if release_id == 10:
            return "Consumer Price Index"
        if release_id == 50:
            return "Employment Situation"
        raise ValueError(f"unexpected release_id {release_id}")

    monkeypatch.setattr(build_macro_calendar, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(
        build_macro_calendar, "fetch_fred_release_dates", fake_fetch_fred_release_dates
    )
    monkeypatch.setattr(
        build_macro_calendar, "fetch_fred_release_name", fake_fetch_fred_release_name
    )
    monkeypatch.setenv("FRED_API_KEY", SENTINEL_KEY)


def test_main_success_writes_calendar(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    calendar_path = tmp_path / "cal.parquet"

    exit_code = build_macro_calendar.main(
        [
            "--calendar-path", str(calendar_path),
            "--retry-wait-max", "0",
            "--today", "1996-06-30",
        ]
    )

    assert exit_code == 0
    df = load_macro_calendar(calendar_path)
    assert list(df.columns) == build_macro_calendar.CALENDAR_COLUMNS
    assert set(df["release"]) == {"FOMC", "CPI", "payrolls"}
    assert df["source_url"].str.startswith("https://").all()
    joined_urls = " ".join(df["source_url"])
    assert "TESTKEY" not in joined_urls
    assert "api_key" not in joined_urls.lower()

    fomc = df[df["release"] == "FOMC"]
    scheduled_1993 = fomc[
        (fomc["date"].dt.year == 1993) & (fomc["scheduled"])
    ]["date"].dt.strftime("%Y-%m-%d").tolist()
    assert sorted(scheduled_1993) == FOMC_1993_SCHEDULED_DATES
