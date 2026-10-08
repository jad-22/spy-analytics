"""End-to-end test: the detector job on the real committed price history (DET-01..07).

Mirrors tests/test_phase0_regression.py's "run against real data, not a fixture" style
and tests/test_refresh_prices.py's tmp_path + main([...]) job-test shape.
"""
from __future__ import annotations

import shutil

import pandas as pd
import pytest

from core.config import SETTINGS
from core.events import EPISODE_COLUMNS
from core.storage import load_episodes, load_meta
from jobs import detect_events

KNOWN_EPISODES = {
    "2000-02": "2002-07-23",
    "2008": "2008-10-09",
    "Aug 2015": "2015-08-24",
    "Feb 2018": "2018-02-05",
    "Q4 2018": "2018-12-24",
    "Mar 2020": "2020-03-16",
    "2022": "2022-06-13",
}


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
