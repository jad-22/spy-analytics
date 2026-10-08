import math

import numpy as np
import pandas as pd
import pytest

from core.backtest import run_backtest
from core.metrics import TRADING_DAYS, cagr, calmar, max_drawdown, metrics_table, sortino


def _equity_from_returns(r: np.ndarray) -> pd.Series:
    idx = pd.bdate_range("2024-01-01", periods=len(r) + 1)
    values = np.concatenate([[1.0], np.cumprod(1 + r)])
    return pd.Series(values, index=idx)


def test_sortino_hand_computed():
    r = np.array([0.01, -0.02, 0.01, -0.01])
    equity = _equity_from_returns(r)
    result = sortino(equity)
    expected_dd = math.sqrt(np.mean(np.minimum(r, 0.0) ** 2)) * math.sqrt(TRADING_DAYS)
    expected = r.mean() * TRADING_DAYS / expected_dd
    assert result == pytest.approx(expected)


def test_sortino_nan_when_no_negative_return():
    r = np.array([0.01, 0.02, 0.01, 0.015])
    equity = _equity_from_returns(r)
    assert math.isnan(sortino(equity))


def test_calmar_matches_formula():
    eq = pd.Series([1.0, 1.2, 0.9, 1.3, 1.04], index=pd.bdate_range("2024-01-01", periods=5))
    result = calmar(eq)
    expected = cagr(eq) / abs(max_drawdown(eq))
    assert result == pytest.approx(expected)


def test_calmar_nan_when_no_drawdown():
    eq = pd.Series([1.0, 1.1, 1.2, 1.3], index=pd.bdate_range("2024-01-01", periods=4))
    assert math.isnan(calmar(eq))


def test_metrics_table_shape_and_bh_values(tiny_prices):
    target = pd.Series([1.0, 0, 0, 1, 1, 1], index=tiny_prices.index)
    result = run_backtest(tiny_prices, target)
    table = metrics_table(result)
    assert list(table.index) == [
        "CAGR",
        "Max drawdown",
        "Sharpe",
        "Sortino",
        "Calmar",
        "Time in market",
        "Trades",
    ]
    assert list(table.columns) == ["Strategy", "Buy & hold"]
    assert table.loc["Time in market", "Buy & hold"] == pytest.approx(1.0)
    assert table.loc["Trades", "Buy & hold"] == 1
