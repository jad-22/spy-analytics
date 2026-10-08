"""Tests for core/calendar.py: pure FOMC/FRED parsing, merge and validation (CAL-01)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import pytest

from core.calendar import (
    parse_fomc_calendars,
    parse_fomc_historical,
    parse_fred_release_dates,
)
from core.config import SETTINGS

FIXTURES = Path(__file__).parent / "fixtures" / "macro"
ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- parse_fomc_historical -------------------------------------------------------

def test_parse_fomc_historical_1993_eight_scheduled_meetings():
    df = parse_fomc_historical(_read("fomchistorical1993.htm"), 1993, "https://u/1993")
    scheduled = df[df["scheduled"]]["date"].dt.strftime("%Y-%m-%d").tolist()
    assert scheduled == [
        "1993-02-03", "1993-03-23", "1993-05-18", "1993-07-07",
        "1993-08-17", "1993-09-21", "1993-11-16", "1993-12-21",
    ]
    unscheduled = df[~df["scheduled"]]
    assert (unscheduled["release_type"] == "unscheduled").all()
    assert len(unscheduled) == 8


def test_parse_fomc_historical_two_day_header_yields_second_day():
    df = parse_fomc_historical(_read("fomchistorical1993.htm"), 1993, "u")
    assert pd.Timestamp("1993-02-03") in set(df["date"])  # "February 2-3 Meeting"
    assert pd.Timestamp("1993-07-07") in set(df["date"])  # "July 6-7 Meeting"


def test_parse_fomc_historical_2008_conference_calls_unscheduled():
    df = parse_fomc_historical(_read("fomchistorical2008.htm"), 2008, "u")
    conf_call_dates = {
        "2008-01-09", "2008-01-21", "2008-03-10",
        "2008-07-24", "2008-09-29", "2008-10-07",
    }
    unscheduled_dates = set(
        df[~df["scheduled"]]["date"].dt.strftime("%Y-%m-%d")
    )
    assert unscheduled_dates == conf_call_dates
    assert int(df["scheduled"].sum()) == 8


def test_parse_fomc_historical_2020_unscheduled_and_cancelled():
    df = parse_fomc_historical(_read("fomchistorical2020.htm"), 2020, "u")
    # "March 2 (unscheduled)" and "March 15 (unscheduled)" are emergency actions.
    unscheduled_dates = set(df[~df["scheduled"]]["date"].dt.strftime("%Y-%m-%d"))
    assert unscheduled_dates == {"2020-03-02", "2020-03-15"}
    # "March 17-18 (cancelled)" produced no decision and must not appear at all.
    assert pd.Timestamp("2020-03-17") not in set(df["date"])
    assert pd.Timestamp("2020-03-18") not in set(df["date"])
    assert int(df["scheduled"].sum()) == 7


def test_parse_fomc_historical_2015_all_scheduled():
    df = parse_fomc_historical(_read("fomchistorical2015.htm"), 2015, "u")
    assert len(df) == 8
    assert df["scheduled"].all()
    assert (df["release_type"] == "meeting").all()


def test_parse_fomc_historical_raises_on_zero_rows():
    with pytest.raises(ValueError):
        parse_fomc_historical("<html>nothing here</html>", 1993, "u")


# --- parse_fomc_calendars ----------------------------------------------------------

def test_parse_fomc_calendars_min_year_and_unscheduled():
    df = parse_fomc_calendars(_read("fomccalendars.htm"), "https://u/cal")
    assert int(df["date"].dt.year.min()) >= 2019
    unscheduled = df[~df["scheduled"]]
    assert (unscheduled["release_type"] == "unscheduled").all()


def test_parse_fomc_calendars_covers_every_listed_year():
    df = parse_fomc_calendars(_read("fomccalendars.htm"), "u")
    years = set(df["date"].dt.year)
    # Confirmed live this session: current page covers 2021-2027 section headers.
    assert {2021, 2022, 2023, 2024, 2025}.issubset(years)


def test_parse_fomc_calendars_raises_on_zero_rows():
    with pytest.raises(ValueError):
        parse_fomc_calendars("<html>nothing here</html>", "u")


# --- parse_fred_release_dates -------------------------------------------------------

def test_parse_fred_release_dates_cpi_shape():
    payload = json.loads((FIXTURES / "fred_release_dates_10.json").read_text())
    df = parse_fred_release_dates(payload, "CPI", 10, SETTINGS.fred_source_url_template)
    assert (df["release"] == "CPI").all()
    assert (df["release_type"] == "release").all()
    assert df["scheduled"].all()
    row = df.iloc[0]
    assert row["source_url"] == f"https://alfred.stlouisfed.org/releases/calendar?rid=10&y={row['date'].year}"


def test_parse_fred_release_dates_pagination_guard_raises():
    payload = {"count": 999, "release_dates": [{"release_id": 10, "date": "1993-01-13"}]}
    with pytest.raises(ValueError):
        parse_fred_release_dates(payload, "CPI", 10, SETTINGS.fred_source_url_template)


def test_parse_fred_release_dates_bad_date_raises():
    payload = {"count": 1, "release_dates": [{"release_id": 10, "date": "not-a-date"}]}
    with pytest.raises(ValueError):
        parse_fred_release_dates(payload, "CPI", 10, SETTINGS.fred_source_url_template)


def test_parse_fred_release_dates_raises_on_zero_rows():
    payload = {"count": 0, "release_dates": []}
    with pytest.raises(ValueError):
        parse_fred_release_dates(payload, "CPI", 10, SETTINGS.fred_source_url_template)


# --- purity --------------------------------------------------------------------------

def test_calendar_module_is_pure():
    tree = ast.parse((ROOT / "core" / "calendar.py").read_text())
    forbidden = {
        "requests", "yfinance", "urllib", "httpx", "socket", "anthropic",
        "jobs", "scripts", "core.data", "core.storage", "streamlit",
    }
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    for module in modules:
        assert not any(module == bad or module.startswith(f"{bad}.") for bad in forbidden), (
            f"core/calendar.py imports forbidden module {module!r}"
        )
