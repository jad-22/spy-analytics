"""End-to-end test: the detector job on the real committed price history (DET-01..07).

Mirrors tests/test_phase0_regression.py's "run against real data, not a fixture" style
and tests/test_refresh_prices.py's tmp_path + main([...]) job-test shape.
"""
from __future__ import annotations

import shutil

import pandas as pd
import pytest

from core.calendar import TAG_COLUMNS
from core.config import SETTINGS
from core.events import EPISODE_COLUMNS
from core.storage import load_episodes, load_meta
from jobs import detect_events
from scripts.report_phase2 import KNOWN_EPISODES


@pytest.fixture(scope="module")
def tmp_meta_path(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("detect_events_meta")
    meta_path = tmp_dir / "meta.json"
    shutil.copy(SETTINGS.meta_path, meta_path)
    return meta_path


@pytest.fixture(scope="module")
def episodes(tmp_path_factory, tmp_meta_path):
    tmp_dir = tmp_path_factory.mktemp("detect_events_out")
    episodes_path = tmp_dir / "episodes.parquet"
    exit_code = detect_events.main(
        [
            "--prices-path", str(SETTINGS.prices_path),
            "--episodes-path", str(episodes_path),
            "--meta-path", str(tmp_meta_path),
            "--calendar-path", str(SETTINGS.macro_calendar_path),
        ]
    )
    assert exit_code == 0
    return load_episodes(episodes_path)


def test_schema(episodes):
    assert list(episodes.columns)[: len(EPISODE_COLUMNS)] == EPISODE_COLUMNS
    assert episodes["episode_id"].is_unique
    assert (episodes["start_date"] <= episodes["anchor_date"]).all()
    assert (episodes["anchor_date"] <= episodes["end_date"]).all()
    assert (episodes["search_from"] <= episodes["search_to"]).all()
    assert set(episodes["direction"].unique()) <= {"down", "up"}
    assert set(episodes["trigger"].unique()) <= {"drawdown", "rally", "shock", "gap"}
    assert (episodes["detector_version"] == SETTINGS.detector_version).all()
    assert episodes["start_date"].is_monotonic_increasing
    expected_ids = episodes.apply(
        lambda row: f"{row['anchor_date']:%Y-%m-%d}_{row['trigger']}", axis=1
    )
    assert (episodes["episode_id"] == expected_ids).all()


def test_count_in_low_hundreds(episodes):
    lo, hi = SETTINGS.episode_count_bounds
    assert lo <= len(episodes) <= hi


@pytest.mark.parametrize("label,probe", list(KNOWN_EPISODES.items()))
def test_known_episodes_detected(episodes, label, probe):
    probe_date = pd.Timestamp(probe)
    matches = episodes[
        (episodes["start_date"] <= probe_date) & (probe_date <= episodes["end_date"])
    ]
    assert len(matches) == 1, f"{label}: expected exactly one episode containing {probe}"
    assert matches.iloc[0]["direction"] == "down"


def test_feb_and_q4_2018_are_separate(episodes):
    feb_probe = pd.Timestamp("2018-02-05")
    q4_probe = pd.Timestamp("2018-12-24")
    feb = episodes[(episodes["start_date"] <= feb_probe) & (feb_probe <= episodes["end_date"])]
    q4 = episodes[(episodes["start_date"] <= q4_probe) & (q4_probe <= episodes["end_date"])]
    assert feb.iloc[0]["episode_id"] != q4.iloc[0]["episode_id"]


def test_meta_detector_version_bumped(tmp_meta_path):
    meta = load_meta(tmp_meta_path)
    assert meta["detector_version"] == SETTINGS.detector_version == 1


# --- CAL-02 tagging (02-05) --------------------------------------------------------------

def test_episodes_carry_tag_columns(episodes):
    assert list(episodes.columns)[len(EPISODE_COLUMNS):] == list(TAG_COLUMNS)


def test_tagged_release_dates_lie_within_search_window(episodes):
    for _, row in episodes.iterrows():
        for entry in list(row["scheduled_releases"]) + list(row["unscheduled_releases"]):
            date_str = entry.rsplit(" ", 1)[1]
            date = pd.Timestamp(date_str)
            assert row["search_from"] <= date <= row["search_to"], (
                f"{row['episode_id']}: {entry!r} outside "
                f"[{row['search_from'].date()}, {row['search_to'].date()}]"
            )


def test_catalyst_is_scheduled_iff_scheduled_releases_nonempty(episodes):
    has_scheduled = episodes["scheduled_releases"].apply(lambda x: len(x) > 0)
    assert (episodes["catalyst"] == "scheduled").equals(has_scheduled)
    assert set(episodes["catalyst"].unique()) <= {"scheduled", "surprise"}


def test_mar_2020_episode_lists_emergency_fomc_as_unscheduled(episodes):
    probe_date = pd.Timestamp("2020-03-16")
    matches = episodes[
        (episodes["start_date"] <= probe_date) & (probe_date <= episodes["end_date"])
    ]
    assert len(matches) == 1
    row = matches.iloc[0]
    assert "FOMC 2020-03-15" in list(row["unscheduled_releases"])
    assert "FOMC 2020-03-15" not in list(row["scheduled_releases"])


def test_main_fails_without_touching_data_when_calendar_missing(tmp_path, tmp_meta_path):
    episodes_path = tmp_path / "episodes.parquet"
    exit_code = detect_events.main(
        [
            "--prices-path", str(SETTINGS.prices_path),
            "--episodes-path", str(episodes_path),
            "--meta-path", str(tmp_meta_path),
            "--calendar-path", str(tmp_path / "missing_calendar.parquet"),
        ]
    )
    assert exit_code == 1
    assert not episodes_path.exists()
