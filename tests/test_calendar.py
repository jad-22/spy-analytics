"""Tests for core/calendar.py: pure FOMC/FRED parsing, merge and validation (CAL-01)."""
from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
import requests

from core.calendar import (
    first_release_per_month,
    merge_calendar,
    parse_fomc_calendars,
    parse_fomc_historical,
    parse_fred_release_dates,
    validate_macro_calendar,
)
from core.config import SETTINGS
from core.data import fetch_fred_release_dates, fetch_fred_release_name

SENTINEL_KEY = "TESTKEY-DO-NOT-LEAK"

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


# --- first_release_per_month (02-04 live-run fix) ----------------------------------------

# Exact live FRED release/dates output for the two years that failed the 10-13/year
# check in the first real 02-04 run.
LIVE_CPI_2000 = [
    "2000-01-14", "2000-02-18", "2000-02-29", "2000-03-17", "2000-04-14", "2000-05-16",
    "2000-06-14", "2000-07-18", "2000-08-16", "2000-09-15", "2000-09-28", "2000-10-18",
    "2000-11-16", "2000-12-15",
]
LIVE_PAYROLLS_2024 = [
    "2024-01-05", "2024-01-10", "2024-02-02", "2024-03-08", "2024-04-05", "2024-05-03",
    "2024-06-07", "2024-07-05", "2024-08-02", "2024-08-21", "2024-09-06", "2024-10-04",
    "2024-11-01", "2024-12-06",
]


def _fred_frame(dates: list[str], label: str, rid: int) -> pd.DataFrame:
    payload = {"count": len(dates), "release_dates": [{"release_id": rid, "date": d} for d in dates]}
    return parse_fred_release_dates(payload, label, rid, SETTINGS.fred_source_url_template)


@pytest.mark.parametrize(
    ("dates", "label", "rid", "revisions"),
    [
        (LIVE_CPI_2000, "CPI", 10, ["2000-02-29", "2000-09-28"]),
        (LIVE_PAYROLLS_2024, "payrolls", 50, ["2024-01-10", "2024-08-21"]),
    ],
)
def test_first_release_per_month_drops_live_off_cycle_revisions(dates, label, rid, revisions):
    kept, dropped = first_release_per_month(_fred_frame(dates, label, rid))
    assert dropped["date"].dt.strftime("%Y-%m-%d").tolist() == revisions
    assert len(kept) == 12
    assert kept["date"].dt.month.tolist() == list(range(1, 13))
    assert list(kept.columns) == list(dropped.columns)


def test_first_release_per_month_is_per_release():
    """CPI and payrolls in the same month are different releases; both survive."""
    df = pd.concat(
        [_fred_frame(["2000-01-07"], "payrolls", 50), _fred_frame(["2000-01-14"], "CPI", 10)],
        ignore_index=True,
    )
    kept, dropped = first_release_per_month(df)
    assert len(kept) == 2
    assert dropped.empty


# --- merge_calendar (D-03 idempotency) -------------------------------------------------

def _row(date, release, release_type="meeting", scheduled=True, url="https://u/1"):
    return {
        "date": pd.Timestamp(date), "release": release, "release_type": release_type,
        "scheduled": scheduled, "source_url": url,
    }


def test_merge_calendar_none_existing_returns_fresh_sorted():
    fresh = pd.DataFrame([_row("1993-03-01", "CPI"), _row("1993-01-01", "FOMC")])
    merged = merge_calendar(None, fresh, pd.Timestamp("1994-01-01"))
    expected = fresh.sort_values(["date", "release", "release_type"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(merged, expected)


def test_merge_calendar_idempotent_with_self():
    fresh = pd.DataFrame([_row("1993-01-01", "FOMC"), _row("1993-02-01", "CPI")])
    once = merge_calendar(None, fresh, pd.Timestamp("1994-01-01"))
    twice = merge_calendar(once, once, pd.Timestamp("1994-01-01"))
    pd.testing.assert_frame_equal(once, twice)


def test_merge_calendar_adds_future_rows_keeps_past_unchanged():
    existing = pd.DataFrame([_row("1993-01-01", "FOMC")])
    fresh = pd.DataFrame([_row("1993-01-01", "FOMC"), _row("1995-01-01", "FOMC")])
    merged = merge_calendar(existing, fresh, pd.Timestamp("1994-01-01"))
    assert len(merged) == 2
    assert {pd.Timestamp("1993-01-01"), pd.Timestamp("1995-01-01")} == set(merged["date"])


def test_merge_calendar_missing_past_row_raises():
    existing = pd.DataFrame([_row("1993-01-01", "FOMC")])
    fresh = pd.DataFrame([_row("1993-02-01", "CPI")])  # 1993-01-01 FOMC no longer present
    with pytest.raises(ValueError, match="missing"):
        merge_calendar(existing, fresh, pd.Timestamp("1994-01-01"))


def test_merge_calendar_drops_vanished_future_row_without_raising():
    existing = pd.DataFrame([_row("1995-01-01", "FOMC")])  # future relative to today
    fresh = pd.DataFrame([_row("1993-01-01", "CPI")])  # fresh no longer confirms it
    merged = merge_calendar(existing, fresh, pd.Timestamp("1994-01-01"))
    assert pd.Timestamp("1995-01-01") not in set(merged["date"])


def test_merge_calendar_fresh_wins_on_duplicate_key():
    fresh = pd.DataFrame(
        [
            _row("1993-01-01", "FOMC", url="https://old"),
            _row("1993-01-01", "FOMC", url="https://new"),
        ]
    )
    merged = merge_calendar(None, fresh, pd.Timestamp("1994-01-01"))
    assert len(merged) == 1
    assert merged.iloc[0]["source_url"] == "https://new"


# --- validate_macro_calendar ------------------------------------------------------------

def _settings_for_validate():
    return replace(
        SETTINGS,
        calendar_start="2000-01-01",
        calendar_first_release_by="2000-01-31",
        fomc_scheduled_per_year=(1, 1),
        monthly_releases_per_year=(1, 1),
        calendar_horizon_days=400,
        fred_releases=(("CPI", 10, "Consumer Price Index"),),
    )


def _well_formed_df():
    return pd.DataFrame(
        [
            _row("2000-01-15", "FOMC", scheduled=True, url="https://fed/1"),
            _row("2000-01-10", "CPI", release_type="release", url="https://alfred/1"),
        ]
    )


def test_validate_macro_calendar_passes_on_well_formed_frame():
    validate_macro_calendar(_well_formed_df(), _settings_for_validate(), pd.Timestamp("2001-01-01"))


def test_validate_macro_calendar_raises_on_nat_date():
    df = _well_formed_df()
    df.loc[0, "date"] = pd.NaT
    with pytest.raises(ValueError, match="NaT"):
        validate_macro_calendar(df, _settings_for_validate(), pd.Timestamp("2001-01-01"))


def test_validate_macro_calendar_raises_on_duplicate_row():
    df = pd.concat(
        [_well_formed_df(), pd.DataFrame([_row("2000-01-15", "FOMC")])], ignore_index=True
    )
    with pytest.raises(ValueError, match="duplicate"):
        validate_macro_calendar(df, _settings_for_validate(), pd.Timestamp("2001-01-01"))


def test_validate_macro_calendar_raises_on_insecure_source_url():
    df = _well_formed_df()
    df.loc[0, "source_url"] = "http://insecure"
    with pytest.raises(ValueError, match="https"):
        validate_macro_calendar(df, _settings_for_validate(), pd.Timestamp("2001-01-01"))


def test_validate_macro_calendar_raises_on_api_key_in_url():
    df = _well_formed_df()
    df.loc[0, "source_url"] = "https://alfred/1?api_key=leak"
    with pytest.raises(ValueError, match="https"):
        validate_macro_calendar(df, _settings_for_validate(), pd.Timestamp("2001-01-01"))


def test_validate_macro_calendar_raises_on_date_before_calendar_start():
    df = _well_formed_df()
    df.loc[0, "date"] = pd.Timestamp("1999-12-31")
    with pytest.raises(ValueError, match="outside"):
        validate_macro_calendar(df, _settings_for_validate(), pd.Timestamp("2001-01-01"))


def test_validate_macro_calendar_raises_on_date_beyond_horizon():
    cfg = _settings_for_validate()
    df = _well_formed_df()
    df.loc[0, "date"] = pd.Timestamp("2001-01-01") + pd.Timedelta(
        days=cfg.calendar_horizon_days + 10
    )
    with pytest.raises(ValueError, match="outside"):
        validate_macro_calendar(df, cfg, pd.Timestamp("2001-01-01"))


def test_validate_macro_calendar_raises_when_fred_first_date_too_late():
    df = _well_formed_df()
    df.loc[1, "date"] = pd.Timestamp("2000-02-15")  # after calendar_first_release_by
    with pytest.raises(ValueError, match="calendar_first_release_by"):
        validate_macro_calendar(df, _settings_for_validate(), pd.Timestamp("2001-01-01"))


def test_validate_macro_calendar_raises_on_fomc_count_out_of_bounds():
    df = _well_formed_df()
    df = df[df["release"] != "FOMC"].reset_index(drop=True)
    with pytest.raises(ValueError, match="FOMC"):
        validate_macro_calendar(df, _settings_for_validate(), pd.Timestamp("2001-01-01"))


def test_validate_macro_calendar_raises_on_monthly_release_count_out_of_bounds():
    df = _well_formed_df()
    df = df[df["release"] != "CPI"].reset_index(drop=True)
    with pytest.raises(ValueError, match="CPI"):
        validate_macro_calendar(df, _settings_for_validate(), pd.Timestamp("2001-01-01"))


# --- secret-leak hardening (D-02, T-02-09) -----------------------------------------------

def test_fetch_fred_release_dates_does_not_leak_key_on_connection_error(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise requests.ConnectionError(f"failed hitting {url}?api_key={SENTINEL_KEY}")

    monkeypatch.setattr("requests.get", fake_get)
    with pytest.raises(ValueError) as exc_info:
        fetch_fred_release_dates(10, SENTINEL_KEY, "1993-01-01", "https://api.stlouisfed.org/fred", 5.0)
    assert SENTINEL_KEY not in str(exc_info.value)


def test_fetch_fred_release_dates_does_not_leak_key_on_bad_status(monkeypatch):
    class _FakeResp:
        status_code = 400
        url = f"https://api.stlouisfed.org/fred/release/dates?api_key={SENTINEL_KEY}"

    monkeypatch.setattr("requests.get", lambda url, params=None, timeout=None: _FakeResp())
    with pytest.raises(ValueError) as exc_info:
        fetch_fred_release_dates(10, SENTINEL_KEY, "1993-01-01", "https://api.stlouisfed.org/fred", 5.0)
    assert SENTINEL_KEY not in str(exc_info.value)


def test_fetch_fred_release_name_does_not_leak_key_on_connection_error(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise requests.ConnectionError(f"failed hitting {url}?api_key={SENTINEL_KEY}")

    monkeypatch.setattr("requests.get", fake_get)
    with pytest.raises(ValueError) as exc_info:
        fetch_fred_release_name(10, SENTINEL_KEY, "https://api.stlouisfed.org/fred", 5.0)
    assert SENTINEL_KEY not in str(exc_info.value)


def test_fetch_fred_release_name_does_not_leak_key_on_bad_status(monkeypatch):
    class _FakeResp:
        status_code = 400
        url = f"https://api.stlouisfed.org/fred/release?api_key={SENTINEL_KEY}"

    monkeypatch.setattr("requests.get", lambda url, params=None, timeout=None: _FakeResp())
    with pytest.raises(ValueError) as exc_info:
        fetch_fred_release_name(10, SENTINEL_KEY, "https://api.stlouisfed.org/fred", 5.0)
    assert SENTINEL_KEY not in str(exc_info.value)


def test_fetch_fred_functions_raise_on_empty_api_key():
    with pytest.raises(ValueError):
        fetch_fred_release_dates(10, "", "1993-01-01", "https://api.stlouisfed.org/fred", 5.0)
    with pytest.raises(ValueError):
        fetch_fred_release_name(10, "", "https://api.stlouisfed.org/fred", 5.0)


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
