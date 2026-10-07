"""Drawdown regimes and Overview KPIs (core/regimes.py). Pure, hand-computed checks."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from core.indicators import MASpec
from core.metrics import TRADING_DAYS
from core.regimes import drawdown_series, drawdown_table, overview_kpis, regime_spans


@pytest.fixture
def dd_prices():
    """Five days, hand-checkable: two drawdown episodes, one recovered."""
    idx = pd.bdate_range("2024-01-01", periods=5, name="date")
    return pd.Series([100.0, 120.0, 90.0, 130.0, 104.0], index=idx, name="close")


def test_drawdown_series(dd_prices):
    dd = drawdown_series(dd_prices)
    expected = [0.0, 0.0, -0.25, 0.0, -0.2]
    assert dd.tolist() == pytest.approx(expected)


def test_regime_spans_contiguous_runs(dd_prices):
    dd = drawdown_series(dd_prices)
    spans = regime_spans(dd, -0.10)
    assert spans == [
        (dd_prices.index[2], dd_prices.index[2]),
        (dd_prices.index[4], dd_prices.index[4]),
    ]


def test_regime_spans_stricter_threshold_excludes_shallower_episode(dd_prices):
    dd = drawdown_series(dd_prices)
    spans = regime_spans(dd, -0.21)
    assert spans == [(dd_prices.index[2], dd_prices.index[2])]


def test_regime_spans_merges_contiguous_bars():
    idx = pd.bdate_range("2024-01-01", periods=4, name="date")
    close = pd.Series([100.0, 90.0, 85.0, 100.0], index=idx)
    dd = drawdown_series(close)
    spans = regime_spans(dd, -0.05)
    assert spans == [(idx[1], idx[2])]


def test_drawdown_table_rows(dd_prices):
    table = drawdown_table(dd_prices, top_n=10)
    assert len(table) == 2
    row1, row2 = table.iloc[0], table.iloc[1]
    assert row1["peak"] == dd_prices.index[1]
    assert row1["trough"] == dd_prices.index[2]
    assert row1["recovery"] == dd_prices.index[3]
    assert row1["depth"] == pytest.approx(-0.25)
    assert row1["days_underwater"] == 2
    assert row2["peak"] == dd_prices.index[3]
    assert row2["trough"] == dd_prices.index[4]
    assert pd.isna(row2["recovery"])
    assert row2["depth"] == pytest.approx(-0.2)
    assert row2["days_underwater"] == 1


def test_drawdown_table_sorted_by_depth_ascending(dd_prices):
    table = drawdown_table(dd_prices, top_n=10)
    assert table["depth"].tolist() == sorted(table["depth"].tolist())


def test_drawdown_table_respects_top_n(dd_prices):
    table = drawdown_table(dd_prices, top_n=1)
    assert len(table) == 1
    assert table.iloc[0]["depth"] == pytest.approx(-0.25)


def test_overview_kpis_ytd_return_uses_prior_year_last_close():
    idx = pd.bdate_range("2023-12-28", "2024-01-05", name="date")
    close = pd.Series(100.0, index=idx)
    close.loc["2023-12-29"] = 100.0
    close.iloc[-1] = 110.0
    kpis = overview_kpis(close, vol_window=3)
    assert kpis["ytd_return"] == pytest.approx(0.10)


def test_overview_kpis_ytd_return_falls_back_to_first_bar_of_year():
    idx = pd.bdate_range("2024-01-01", periods=5, name="date")
    close = pd.Series([100.0, 101.0, 102.0, 103.0, 110.0], index=idx)
    kpis = overview_kpis(close, vol_window=3)
    assert kpis["ytd_return"] == pytest.approx(110.0 / 100.0 - 1)


def test_overview_kpis_drawdown_and_ath(dd_prices):
    kpis = overview_kpis(dd_prices, vol_window=3)
    last = dd_prices.iloc[-1]
    cummax = dd_prices.cummax()
    assert kpis["current_drawdown"] == pytest.approx(last / cummax.iloc[-1] - 1)
    assert kpis["current_drawdown"] <= 0
    assert kpis["distance_from_ath"] == pytest.approx(cummax.max() / last - 1)
    assert kpis["distance_from_ath"] >= 0
    assert kpis["ath_date"] == dd_prices.index[3]


def test_overview_kpis_realised_vol_matches_hand_computation(random_prices):
    close = random_prices["close"]
    kpis = overview_kpis(close, vol_window=20)
    log_returns = np.log(close / close.shift(1)).dropna()
    expected = log_returns.iloc[-20:].std() * math.sqrt(TRADING_DAYS)
    assert kpis["realised_vol"] == pytest.approx(expected)


def test_maspec_from_label_parses_kind_and_period():
    assert MASpec.from_label("ema200") == MASpec("ema", 200)
    assert MASpec.from_label("sma50") == MASpec("sma", 50)


def test_maspec_from_label_raises_on_invalid():
    with pytest.raises(ValueError):
        MASpec.from_label("foo")
