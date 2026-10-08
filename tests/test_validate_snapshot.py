from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.config import SETTINGS
from core.market_calendar import nyse_sessions
from core.validate import drop_incomplete_session, validate_snapshot


@pytest.fixture
def nyse_frame():
    """Random-walk OHLCV on real NYSE sessions (no bdate_range holiday noise)."""
    idx = nyse_sessions("2023-01-03", "2023-12-29")
    rng = np.random.default_rng(11)
    n = len(idx)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    open_ = close * np.exp(rng.normal(0, 0.002, n))
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) * 1.001,
            "low": np.minimum(open_, close) * 0.999,
            "close": close,
            "adj_close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        },
        index=idx,
    )


def test_clean_append_passes(nyse_frame):
    old = nyse_frame.iloc[:-1]
    new = nyse_frame
    validate_snapshot(new, old, SETTINGS)  # no raise


def test_shorter_row_count_raises(nyse_frame):
    old = nyse_frame.iloc[:-1]
    new = nyse_frame.iloc[:-5]
    with pytest.raises(ValueError, match="row count"):
        validate_snapshot(new, old, SETTINGS)


def test_last_date_regression_raises(nyse_frame):
    old = nyse_frame
    new = nyse_frame.copy()
    # Same row count as old (no shrink), but the last date moved back.
    new.index = list(new.index[:-1]) + [new.index[-2]]
    with pytest.raises(ValueError, match="last date"):
        validate_snapshot(new, old, SETTINGS)


def test_close_rewrite_beyond_tolerance_raises(nyse_frame):
    old = nyse_frame.iloc[:-1]
    new = nyse_frame.copy()
    new.loc[new.index[100], "close"] *= 1.001  # 0.1% > 0.01% tolerance
    with pytest.raises(ValueError, match="close"):
        validate_snapshot(new, old, SETTINGS)


def test_volume_rewrite_beyond_tolerance_raises(nyse_frame):
    old = nyse_frame.iloc[:-1]
    new = nyse_frame.copy()
    new.loc[new.index[50], "volume"] *= 1.01  # 1% > 0.01% tolerance
    with pytest.raises(ValueError, match="volume"):
        validate_snapshot(new, old, SETTINGS)


def test_adj_close_common_factor_passes(nyse_frame):
    old = nyse_frame.iloc[:-1]
    new = nyse_frame.copy()
    new["adj_close"] = new["adj_close"] * 0.99
    validate_snapshot(new, old, SETTINGS)  # no raise


def test_adj_close_non_common_factor_raises(nyse_frame):
    old = nyse_frame.iloc[:-1]
    new = nyse_frame.copy()
    new["adj_close"] = new["adj_close"] * 0.99
    new.loc[new.index[30], "adj_close"] *= 1.05  # one row scaled differently
    with pytest.raises(ValueError, match="adj_close"):
        validate_snapshot(new, old, SETTINGS)


def test_missing_session_inside_new_raises(nyse_frame):
    new = nyse_frame.drop(nyse_frame.index[100])
    with pytest.raises(ValueError, match="missing session"):
        validate_snapshot(new, None, SETTINGS)


def test_first_run_without_old_passes_on_gapless_frame(nyse_frame):
    validate_snapshot(nyse_frame, None, SETTINGS)  # no raise


def test_drop_incomplete_session_drops_before_complete_time():
    idx = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    df = pd.DataFrame({"close": [1.0, 2.0]}, index=idx)
    now_utc = pd.Timestamp("2024-01-03 20:00", tz="UTC")  # 15:00 ET in January (EST)

    result = drop_incomplete_session(df, now_utc, SETTINGS)

    assert len(result) == 1
    assert result.index[-1] == idx[0]


def test_drop_incomplete_session_keeps_after_complete_time():
    idx = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    df = pd.DataFrame({"close": [1.0, 2.0]}, index=idx)
    now_utc = pd.Timestamp("2024-01-03 22:00", tz="UTC")  # 17:00 ET in January (EST)

    result = drop_incomplete_session(df, now_utc, SETTINGS)

    assert len(result) == 2


def test_drop_incomplete_session_keeps_bar_dated_yesterday():
    idx = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    df = pd.DataFrame({"close": [1.0, 2.0]}, index=idx)
    now_utc = pd.Timestamp("2024-01-04 12:00", tz="UTC")  # "today" is 01-04

    result = drop_incomplete_session(df, now_utc, SETTINGS)

    assert len(result) == 2
