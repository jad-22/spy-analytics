"""Shock/gap/drawdown/rally detection and clustering (core/events.py). Pure, hand-checkable.

Every threshold is varied via dataclasses.replace(SETTINGS, ...) rather than hard-coded in
core/events.py -- per CLAUDE.md and DET-06, thresholds must flow from config.
"""
from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.config import SETTINGS
from core.events import (
    Leg,
    cluster_legs,
    detect,
    drawdown_legs,
    gap_days,
    log_returns,
    rally_legs,
    shock_days,
    shock_zscores,
)

ROOT = Path(__file__).resolve().parents[1]
EVENTS_MODULE_PATH = ROOT / "core" / "events.py"


def _settings_with(**overrides):
    return dataclasses.replace(SETTINGS, **overrides)


def test_log_returns_matches_hand_computation():
    idx = pd.bdate_range("2024-01-01", periods=4, name="date")
    close = pd.Series([100.0, 110.0, 99.0, 99.0], index=idx)
    ret = log_returns(close)
    expected = [np.nan, np.log(1.1), np.log(99.0 / 110.0), 0.0]
    np.testing.assert_allclose(ret.to_numpy(), expected)


def test_shock_zscores_sigma_lagged_one_day_and_flags_big_jump(random_prices):
    close = random_prices["close"]
    t = 100
    injected = close.copy()
    injected.iloc[t] = close.iloc[t - 1] * 1.5  # a lone, huge one-day jump

    ret = log_returns(injected)
    z = shock_zscores(injected, SETTINGS.shock_sigma_window)

    # Sigma used at t is computed from positions t-60..t-1 only -- day t's own huge
    # return must not leak into its own sigma.
    expected_sigma = np.std(
        ret.iloc[t - SETTINGS.shock_sigma_window : t].to_numpy(), ddof=1
    )
    assert z.iloc[t] == pytest.approx(ret.iloc[t] / expected_sigma)
    assert abs(z.iloc[t]) > SETTINGS.shock_z_threshold


def test_shock_days_empty_for_first_sigma_window_days(random_prices):
    close = random_prices["close"]
    flagged = shock_days(close, SETTINGS.shock_sigma_window, SETTINGS.shock_z_threshold)
    first_window = set(close.index[: SETTINGS.shock_sigma_window])
    assert not first_window & set(flagged)


def test_gap_days_flags_above_threshold_not_below():
    idx = pd.bdate_range("2024-01-01", periods=3, name="date")
    close = pd.Series([100.0, 100.0, 100.0], index=idx)
    open_ = pd.Series([100.0, 102.0, 101.0], index=idx)  # gaps: n/a, +2%, +1%
    flagged = gap_days(open_, close, threshold=0.015)
    assert list(flagged) == [idx[1]]


def test_drawdown_legs_matches_hand_computed_episodes():
    idx = pd.bdate_range("2024-01-01", periods=5, name="date")
    close = pd.Series([100.0, 120.0, 90.0, 130.0, 104.0], index=idx)
    legs = drawdown_legs(close, threshold=0.05)
    assert legs == [
        Leg("drawdown", 1, 2, pytest.approx(-0.25), 3),
        Leg("drawdown", 3, 4, pytest.approx(-0.2), None),
    ]


def test_drawdown_legs_below_threshold_produces_no_leg():
    idx = pd.bdate_range("2024-01-01", periods=3, name="date")
    close = pd.Series([100.0, 96.0, 100.0], index=idx)  # a 4% dip
    assert drawdown_legs(close, threshold=0.05) == []


def test_rally_legs_flags_fast_rise_not_slow_spread():
    idx = pd.bdate_range("2024-01-01", periods=60, name="date")
    fast = np.concatenate(
        [np.full(20, 100.0), np.linspace(100.9, 109.0, 10), np.full(30, 109.0)]
    )
    fast_close = pd.Series(fast[:60], index=idx)
    fast_legs = rally_legs(fast_close, threshold=0.08, window=30)
    assert len(fast_legs) == 1
    assert fast_legs[0].move >= 0.08

    idx_slow = pd.bdate_range("2024-01-01", periods=60, name="date")
    slow = np.concatenate([np.full(20, 100.0), np.linspace(100.2, 109.0, 40)])
    slow_close = pd.Series(slow[:60], index=idx_slow)
    assert rally_legs(slow_close, threshold=0.08, window=30) == []


def test_cluster_legs_merges_within_window_not_beyond():
    close_pair = [
        Leg("shock", 10, 10, 0.03, None),
        Leg("shock", 13, 13, -0.03, None),
    ]
    merged = cluster_legs(close_pair, merge_window_days=3)
    assert len(merged) == 1
    assert {leg.start_pos for leg in merged[0]} == {10, 13}

    separate_pair = [
        Leg("shock", 10, 10, 0.03, None),
        Leg("shock", 14, 14, -0.03, None),
    ]
    clusters = cluster_legs(separate_pair, merge_window_days=3)
    assert len(clusters) == 2


def test_cluster_legs_uses_trading_days_not_calendar_days():
    # A Thursday and the Monday right after it are four calendar days apart, but with a
    # Friday holiday they are adjacent (gap 1) in the trading-day position space that
    # cluster_legs operates on.
    idx = pd.DatetimeIndex(["2024-01-04", "2024-01-08"], name="date")  # Thu, Mon
    assert idx[0].day_name() == "Thursday"
    assert idx[1].day_name() == "Monday"
    legs = [Leg("shock", 0, 0, 0.03, None), Leg("shock", 1, 1, -0.03, None)]
    clusters = cluster_legs(legs, merge_window_days=1)
    assert len(clusters) == 1


def test_cluster_legs_does_not_absorb_via_recovery_span():
    """D-01: clustering uses a drawdown leg's steepest span, never its recovery span."""
    dd_leg = Leg("drawdown", start_pos=5, end_pos=20, move=-0.30, recovery_pos=500)
    shock_leg = Leg("shock", start_pos=100, end_pos=100, move=0.03, recovery_pos=None)
    clusters = cluster_legs([dd_leg, shock_leg], merge_window_days=3)
    assert len(clusters) == 2


def test_detect_trigger_precedence_anchor_and_severity():
    idx = pd.bdate_range("2024-01-01", periods=30, name="date")
    baseline = [100.00, 100.01, 99.99, 100.02, 99.98, 100.01, 99.99, 100.00, 100.01, 99.99]
    closes = list(baseline)
    closes.append(80.0)  # pos10: crash day
    closes.append(105.0)  # pos11: recovers above the pre-crash peak
    closes += [105.0 + 0.01 * ((-1) ** i) for i in range(10)]  # pos12-21: calm
    closes.append(109.0)  # pos22: independent spike, far from the first cluster
    closes += [109.0 + 0.01 * ((-1) ** i) for i in range(30 - len(closes))]
    closes = np.array(closes[:30], dtype=float)
    close = pd.Series(closes, index=idx, name="close")

    opens = close.shift(1).fillna(close.iloc[0]).to_numpy().copy()
    opens[10] = close.iloc[9] * 0.95  # -5% gap at the crash
    opens[22] = close.iloc[21] * 1.02  # +2% gap at the spike
    open_ = pd.Series(opens, index=idx, name="open")

    settings = _settings_with(
        shock_sigma_window=5,
        shock_z_threshold=2.0,
        gap_threshold=0.015,
        drawdown_threshold=0.05,
        rally_threshold=10.0,  # disabled: isolates drawdown from an incidental rally
        merge_window_days=3,
    )
    prices = pd.DataFrame({"open": open_, "high": close, "low": close, "close": close})
    episodes = detect(prices, settings)

    assert len(episodes) == 2
    first, second = episodes.iloc[0], episodes.iloc[1]

    assert first["trigger"] == "drawdown"
    assert first["triggers"] == "drawdown,gap,shock"
    # anchor is the day with the largest |log return| in [start_date, end_date]: the
    # recovery jump (80 -> 105) is numerically bigger than the crash itself (100 -> 80).
    crash_ret = np.log(80.0 / close.iloc[9])
    recovery_ret = np.log(105.0 / 80.0)
    assert abs(recovery_ret) > abs(crash_ret)
    assert first["anchor_date"] == idx[11]
    assert first["episode_id"] == f"{idx[11]:%Y-%m-%d}_drawdown"

    assert second["trigger"] == "shock"
    assert second["triggers"] == "gap,shock"
    assert second["anchor_date"] == idx[22]
    assert second["episode_id"] == f"{idx[22]:%Y-%m-%d}_shock"

    for row in (first, second):
        expected_severity = row["max_z"] + abs(row["move_pct"]) / settings.severity_move_step
        assert row["severity"] == pytest.approx(expected_severity)


def test_detect_anchor_picks_earliest_on_tie():
    idx = pd.bdate_range("2024-01-01", periods=16, name="date")
    baseline = [100.00, 100.01, 99.99, 100.02, 99.98, 100.01, 99.99, 100.00, 100.01, 100.00]
    closes = list(baseline)
    closes += [150.0, 120.0, 180.0]  # pos10: +50%, pos11: -20%, pos12: ties pos10 exactly
    closes += [180.0 + 0.01 * ((-1) ** i) for i in range(16 - len(closes))]
    closes = np.array(closes[:16], dtype=float)
    close = pd.Series(closes, index=idx, name="close")
    open_ = close.shift(1).fillna(close.iloc[0])

    pos10_ret = np.log(150.0 / close.iloc[9])
    pos12_ret = np.log(180.0 / 120.0)
    assert pos10_ret == pytest.approx(pos12_ret)  # a genuine tie in |log return|

    settings = _settings_with(
        shock_sigma_window=5,
        shock_z_threshold=2.0,
        gap_threshold=1.0,  # disabled: isolates the anchor tie-break from gap flags
        drawdown_threshold=0.05,
        rally_threshold=10.0,  # disabled: isolates the anchor tie-break from a rally leg
        merge_window_days=3,
    )
    prices = pd.DataFrame({"open": open_, "high": close, "low": close, "close": close})
    episodes = detect(prices, settings)

    assert len(episodes) == 1
    assert episodes.iloc[0]["anchor_date"] == idx[10]  # earliest of the tied days


def test_detect_respects_custom_shock_threshold_from_settings(random_prices):
    prices = random_prices[["open", "high", "low", "close"]]
    default_episodes = detect(prices, SETTINGS)
    strict_settings = _settings_with(shock_z_threshold=10.0)
    strict_episodes = detect(prices, strict_settings)

    default_shock_count = default_episodes["triggers"].str.contains("shock").sum()
    strict_shock_count = strict_episodes["triggers"].str.contains("shock").sum()
    assert strict_shock_count < default_shock_count


def test_events_module_has_no_numeric_literals():
    """DET-06: every detection threshold must flow from Settings, not a bare literal.

    Only 0 and 1 are allowed (array/position bookkeeping -- e.g. close.iloc[0],
    max(x - 1, 0), 0.0 as a "no data" severity default) since those aren't thresholds.
    """
    tree = ast.parse(EVENTS_MODULE_PATH.read_text())
    bad_lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if isinstance(node.value, bool):
                continue
            if node.value not in (0, 1):
                bad_lines.append(node.lineno)
    assert not bad_lines, (
        f"core/events.py has non-0/1 numeric literals (should flow from Settings) at "
        f"line(s): {sorted(set(bad_lines))}"
    )


def test_events_module_is_pure():
    """core/events.py must stay a pure transform: no network, no core.data/core.storage,
    no jobs/scripts -- same forbidden-module boundary as tests/test_app_purity.py.
    """
    forbidden = {
        "requests", "urllib", "httpx", "socket", "yfinance", "anthropic", "streamlit",
        "core.data", "core.storage", "jobs", "scripts",
    }
    tree = ast.parse(EVENTS_MODULE_PATH.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    for module in imported:
        is_forbidden = any(
            module == bad or module.startswith(f"{bad}.") for bad in forbidden
        )
        assert not is_forbidden, f"core/events.py imports forbidden module '{module}'"
