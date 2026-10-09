"""Offline job tests for jobs/build_macro_calendar.py (CAL-01).

All network calls are monkeypatched to fixture data captured in tests/fixtures/macro/;
no test here needs a FRED API key or internet access. The sentinel key
"TESTKEY-DO-NOT-LEAK" stands in for FRED_API_KEY and must never appear in any written
file, exception message, or captured stderr (D-02).
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

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


_DEFAULT_NAMES = {10: "Consumer Price Index", 50: "Employment Situation"}


def _install_fakes(monkeypatch, *, fred_10=None, fred_50=None, names=None):
    """Monkeypatch build_macro_calendar's fetch_* names to fixture data.

    Historical years 1993/2008/2015/2020 use their real captured fixtures; any other
    year in the 1993..first_calendars_year-1 range (e.g. 1994, 1995, 1996) is a
    synthetic convenience -- it reuses the 2015 fixture text with the year string
    substituted, since 2015's "8 regular meetings, no conference calls" shape is a
    reasonable stand-in and this plan's tests never assert specific dates for those
    synthetic years.

    `fred_10`/`fred_50`/`names` let a test override the FRED payload or confirmed
    release name for one Task-3 scenario (a vanished past date, a mismatched name)
    without duplicating the whole fixture-loading setup.
    """
    real_years = {"1993", "2008", "2015", "2020"}
    html_2015 = (FIXTURES / "fomchistorical2015.htm").read_text(encoding="utf-8")
    html_calendars = (FIXTURES / "fomccalendars.htm").read_text(encoding="utf-8")
    fred_10 = fred_10 if fred_10 is not None else json.loads(
        (FIXTURES / "fred_release_dates_10.json").read_text()
    )
    fred_50 = fred_50 if fred_50 is not None else json.loads(
        (FIXTURES / "fred_release_dates_50.json").read_text()
    )
    names = {**_DEFAULT_NAMES, **(names or {})}

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
        if release_id in names:
            return names[release_id]
        raise ValueError(f"unexpected release_id {release_id}")

    monkeypatch.setattr(build_macro_calendar, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(
        build_macro_calendar, "fetch_fred_release_dates", fake_fetch_fred_release_dates
    )
    monkeypatch.setattr(
        build_macro_calendar, "fetch_fred_release_name", fake_fetch_fred_release_name
    )
    monkeypatch.setenv("FRED_API_KEY", SENTINEL_KEY)


def _argv(calendar_path):
    return [
        "--calendar-path", str(calendar_path),
        "--retry-wait-max", "0",
        "--today", "1996-06-30",
    ]


def test_main_success_writes_calendar(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    calendar_path = tmp_path / "cal.parquet"

    exit_code = build_macro_calendar.main(_argv(calendar_path))

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


def test_main_idempotent_second_run_same_fakes(tmp_path, monkeypatch):
    """D-03: re-running with the same source data produces an identical frame."""
    calendar_path = tmp_path / "cal.parquet"

    _install_fakes(monkeypatch)
    assert build_macro_calendar.main(_argv(calendar_path)) == 0
    first = load_macro_calendar(calendar_path)

    _install_fakes(monkeypatch)
    assert build_macro_calendar.main(_argv(calendar_path)) == 0
    second = load_macro_calendar(calendar_path)

    pd.testing.assert_frame_equal(first, second)


def test_main_unlisted_second_fred_date_in_month_fails_without_writing(
    tmp_path, monkeypatch, capsys
):
    """02-04 live run: FRED also lists revision/seasonal-factor days. Known ones are in
    Settings.fred_non_release_dates; an unlisted one must fail loudly, never be tagged
    as a scheduled print."""
    calendar_path = tmp_path / "cal.parquet"
    fred_10 = json.loads((FIXTURES / "fred_release_dates_10.json").read_text())
    feb_1993 = [e["date"] for e in fred_10["release_dates"] if e["date"].startswith("1993-02")]
    assert len(feb_1993) == 1
    fred_10["release_dates"].append({"release_id": 10, "date": "1993-02-26"})
    fred_10["count"] = len(fred_10["release_dates"])

    _install_fakes(monkeypatch, fred_10=fred_10)
    assert build_macro_calendar.main(_argv(calendar_path)) == 1
    assert not calendar_path.exists()
    assert "more than one release in a month" in capsys.readouterr().err


def test_main_drops_listed_non_print_dates(tmp_path, monkeypatch, capsys):
    calendar_path = tmp_path / "cal.parquet"
    fred_10 = json.loads((FIXTURES / "fred_release_dates_10.json").read_text())
    fred_10["release_dates"].append({"release_id": 10, "date": "1993-02-26"})
    fred_10["count"] = len(fred_10["release_dates"])
    settings = replace(
        build_macro_calendar.SETTINGS,
        fred_non_release_dates=(("CPI", "1993-02-26"),),
    )
    monkeypatch.setattr(build_macro_calendar, "SETTINGS", settings)

    _install_fakes(monkeypatch, fred_10=fred_10)
    assert build_macro_calendar.main(_argv(calendar_path)) == 0
    cpi = load_macro_calendar(calendar_path).query("release == 'CPI'")
    assert pd.Timestamp("1993-02-26") not in set(cpi["date"])
    assert "CPI: dropped 1 listed non-print date(s)" in capsys.readouterr().out


def test_main_vanished_past_date_rejected_leaves_file_unchanged(tmp_path, monkeypatch, capsys):
    """D-03: a previously committed past row disappearing from the source must fail
    without writing -- re-running later should extend forward, never silently rewrite
    history that was already final."""
    calendar_path = tmp_path / "cal.parquet"

    _install_fakes(monkeypatch)
    assert build_macro_calendar.main(_argv(calendar_path)) == 0
    before = calendar_path.read_bytes()

    fred_10 = json.loads((FIXTURES / "fred_release_dates_10.json").read_text())
    dropped = fred_10["release_dates"][0]["date"]  # 1993-01-13, well before --today
    assert dropped < "1996-06-30"
    fred_10["release_dates"] = fred_10["release_dates"][1:]
    fred_10["count"] = len(fred_10["release_dates"])

    _install_fakes(monkeypatch, fred_10=fred_10)
    exit_code = build_macro_calendar.main(_argv(calendar_path))

    assert exit_code == 1
    assert calendar_path.read_bytes() == before
    captured = capsys.readouterr()
    assert SENTINEL_KEY not in captured.err
    assert SENTINEL_KEY not in captured.out


def test_main_missing_key_returns_1_and_writes_nothing(tmp_path, monkeypatch, capsys):
    calendar_path = tmp_path / "cal.parquet"
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    exit_code = build_macro_calendar.main(_argv(calendar_path))

    assert exit_code == 1
    assert not calendar_path.exists()
    captured = capsys.readouterr()
    assert "FRED_API_KEY is not set" in captured.err
    assert SENTINEL_KEY not in captured.err


def test_main_release_name_mismatch_returns_1(tmp_path, monkeypatch, capsys):
    calendar_path = tmp_path / "cal.parquet"
    _install_fakes(monkeypatch, names={10: "Producer Price Index"})

    exit_code = build_macro_calendar.main(_argv(calendar_path))

    assert exit_code == 1
    assert not calendar_path.exists()
    captured = capsys.readouterr()
    assert "Producer Price Index" in captured.err
    assert SENTINEL_KEY not in captured.err
    assert SENTINEL_KEY not in captured.out


def test_main_accept_history_change_writes_and_prints_diff(tmp_path, monkeypatch, capsys):
    """WR-03: a maintainer can apply a checked correction to past rows deliberately."""
    calendar_path = tmp_path / "cal.parquet"
    _install_fakes(monkeypatch)
    assert build_macro_calendar.main(_argv(calendar_path)) == 0

    fred_10 = json.loads((FIXTURES / "fred_release_dates_10.json").read_text())
    dropped = fred_10["release_dates"][0]["date"]
    fred_10["release_dates"] = fred_10["release_dates"][1:]
    fred_10["count"] = len(fred_10["release_dates"])
    _install_fakes(monkeypatch, fred_10=fred_10)
    capsys.readouterr()

    assert build_macro_calendar.main([*_argv(calendar_path), "--accept-history-change"]) == 0
    out = capsys.readouterr().out
    assert f"past row removed/changed: {dropped} CPI" in out
    cpi = load_macro_calendar(calendar_path).query("release == 'CPI'")
    assert pd.Timestamp(dropped) not in set(cpi["date"])
