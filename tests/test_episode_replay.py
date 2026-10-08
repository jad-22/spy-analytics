"""Replay-stability tests for core/events.py's closed/open status (DET-05).

Synthetic tests pin the closure_frontier rule on hand-built series (02-02-PLAN.md's
<behavior> block). Real-data tests prove the full `detect` pipeline is replay-stable: every
closed episode detected on data truncated at a cutoff appears identically when more history
is appended -- the contract Phase 3's irreversible LLM spend depends on (STATE.md roadmap
decision).
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from core.config import SETTINGS
from core.events import detect
from core.storage import load_prices, price_basis

CUTOFFS = [
    "2002-12-31", "2008-06-30", "2011-12-30",
    "2016-06-30", "2020-12-31", "2023-06-30",
]

# Smaller windows than production SETTINGS so hand-built synthetic fixtures stay short and
# hand-checkable; rally disabled by default (unreachable threshold) in most synthetic tests
# so a drawdown/shock/gap cluster never picks up an incidental rally leg (same isolation
# technique as tests/test_events.py's existing fixtures).
REPLAY_SETTINGS = dataclasses.replace(
    SETTINGS,
    shock_sigma_window=5,
    shock_z_threshold=2.0,
    gap_threshold=1.0,  # disabled
    drawdown_threshold=0.05,
    rally_threshold=10.0,  # disabled
    rally_window_days=10,
    merge_window_days=3,
)


def _calm_prices(n: int, bumps: dict[int, float] | None = None, start: str = "2024-01-01"):
    """A causal, cumulative-return series: tiny alternating noise plus optional one-day
    jumps (sustained, not reverted -- so a jump never looks like a drawdown). The final bar
    is forced to an unambiguous new high so the series is never "below its own peak" at the
    end, isolating the merge_window/rally_window frontier candidates from the peak-position
    candidate (tested separately below).
    """
    idx = pd.bdate_range(start, periods=n, name="date")
    rets = np.array([0.0002 * ((-1) ** i) for i in range(n)])
    rets[0] = 0.0
    if bumps:
        for pos, ret in bumps.items():
            rets[pos] = ret
    closes = 100.0 * np.cumprod(1.0 + rets)
    closes[-1] = closes[:-1].max() * 1.01
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes}, index=idx
    )


def _assert_rows_match(before_row, after_row, cols):
    for col in cols:
        b, a = before_row[col], after_row[col]
        if pd.isna(b) and pd.isna(a):
            continue
        assert b == a, f"{col}: {b!r} != {a!r}"


def test_shock_cluster_closes_and_survives_append():
    n = 80
    prices = _calm_prices(n, bumps={10: 0.20})

    before = detect(prices, REPLAY_SETTINGS)
    closed_shocks = before[(before["status"] == "closed") & (before["trigger"] == "shock")]
    assert len(closed_shocks) >= 1
    shock_row = closed_shocks.iloc[0]

    idx2 = pd.bdate_range(
        prices.index[-1] + pd.tseries.offsets.BDay(1), periods=50, name="date"
    )
    rets2 = np.array([0.0002 * ((-1) ** i) for i in range(50)])
    rets2[30] = 0.20  # a second, independent shock far from the first
    closes2 = prices["close"].iloc[-1] * np.cumprod(1.0 + rets2)
    closes2[-1] = max(closes2[:-1].max(), prices["close"].max()) * 1.01
    prices2 = pd.DataFrame(
        {"open": closes2, "high": closes2, "low": closes2, "close": closes2}, index=idx2
    )
    full = pd.concat([prices, prices2])

    after = detect(full, REPLAY_SETTINGS)
    after_rows = after[after["episode_id"] == shock_row["episode_id"]]
    assert len(after_rows) == 1
    after_row = after_rows.iloc[0]

    _assert_rows_match(
        shock_row,
        after_row,
        [
            "episode_id", "start_date", "end_date", "anchor_date", "direction", "trigger",
            "triggers", "search_from", "search_to", "recovery_date", "status",
        ],
    )
    for col in ["move_pct", "max_z", "severity"]:
        assert after_row[col] == pytest.approx(shock_row[col], rel=1e-9)


def test_open_drawdown_at_end_has_nat_recovery_and_open_status():
    n = 40
    idx = pd.bdate_range("2024-01-01", periods=n, name="date")
    rets = np.array([0.0002 * ((-1) ** i) for i in range(n)])
    rets[0] = 0.0
    rets[5] = 0.10  # forms the peak
    rets[20] = -0.10  # drawdown leg starts here; never recovers by end of data
    closes = 100.0 * np.cumprod(1.0 + rets)
    prices = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes}, index=idx
    )

    episodes = detect(prices, REPLAY_SETTINGS)

    close = prices["close"]
    at_peak = (close.to_numpy() == close.cummax().to_numpy())
    peak_pos = int(np.nonzero(at_peak)[0][-1])
    peak_date = close.index[peak_pos]

    on_or_after_peak = episodes[episodes["end_date"] >= peak_date]
    assert len(on_or_after_peak) >= 1
    assert (on_or_after_peak["status"] == "open").all()

    dd_rows = episodes[episodes["trigger"] == "drawdown"]
    assert len(dd_rows) == 1
    dd_row = dd_rows.iloc[0]
    assert dd_row["status"] == "open"
    assert pd.isna(dd_row["recovery_date"])


def test_shock_near_end_is_open():
    n = 40
    prices = _calm_prices(n, bumps={n - 3: 0.05})  # shock at position last-2

    episodes = detect(prices, REPLAY_SETTINGS)
    shock_rows = episodes[episodes["end_date"] == prices.index[n - 3]]
    assert len(shock_rows) == 1
    assert shock_rows.iloc[0]["status"] == "open"


def test_closed_boundary_merge_plus_rally_window_plus_one_bars_before_end():
    rally_window_days = REPLAY_SETTINGS.rally_window_days
    merge_window_days = REPLAY_SETTINGS.merge_window_days
    gap = merge_window_days + rally_window_days + 1
    n = 60
    bump_pos = n - 1 - gap
    prices = _calm_prices(n, bumps={bump_pos: 0.05})

    episodes = detect(prices, REPLAY_SETTINGS)
    target = episodes[episodes["end_date"] == prices.index[bump_pos]]
    assert len(target) == 1
    assert target.iloc[0]["status"] == "closed"


@pytest.fixture(scope="module")
def full_history():
    raw = load_prices(SETTINGS.prices_path)
    return price_basis(raw, "total_return")


@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_closed_episodes_are_replay_stable(full_history, cutoff):
    truncated = full_history.loc[:cutoff]
    before = detect(truncated, SETTINGS)
    after = detect(full_history, SETTINGS)

    closed = before[before["status"] == "closed"]
    assert len(closed) >= 1

    merged = closed.merge(after, on="episode_id", suffixes=("_before", "_after"))
    assert len(merged) == len(closed), "every closed episode must still exist after append"

    exact_cols = [
        "start_date", "end_date", "anchor_date", "direction", "trigger", "triggers",
        "search_from", "search_to", "status",
    ]
    for col in exact_cols:
        assert (merged[f"{col}_before"] == merged[f"{col}_after"]).all(), col

    rec_before = merged["recovery_date_before"]
    rec_after = merged["recovery_date_after"]
    assert ((rec_before == rec_after) | (rec_before.isna() & rec_after.isna())).all(), (
        "recovery_date"
    )

    for col in ["move_pct", "max_z", "severity"]:
        np.testing.assert_allclose(
            merged[f"{col}_before"].to_numpy(dtype=float),
            merged[f"{col}_after"].to_numpy(dtype=float),
            rtol=1e-9,
        )


def test_dotcom_leg_still_open_at_2002_cutoff(full_history):
    truncated = full_history.loc[:"2002-12-31"]
    episodes = detect(truncated, SETTINGS)
    closed = episodes[episodes["status"] == "closed"]

    close = truncated["close"]
    at_peak = close.to_numpy() == close.cummax().to_numpy()
    peak_pos = int(np.nonzero(at_peak)[0][-1])
    peak_date = close.index[peak_pos]

    assert (closed["start_date"] < peak_date).all()
