import pandas as pd
import pytest

from core.backtest import run_backtest
from core.metrics import max_drawdown, summarise


def test_hand_computed_equity(tiny_prices):
    # Decisions at each close: long, cash, cash, long, long, long
    target = pd.Series([1.0, 0, 0, 1, 1, 1], index=tiny_prices.index)
    res = run_backtest(tiny_prices, target)
    # Buy at open[1]=110, sell at open[2]=99 (-10%), buy at open[4]=120, value at open[5]=132 (+10%)
    assert res.equity.iloc[0] == 1.0
    assert res.equity.iloc[-1] == pytest.approx(0.9 * 1.1)
    # Buy and hold over the same window: 132 / 110
    assert res.benchmark.iloc[-1] == pytest.approx(132 / 110)
    assert res.trades["side"].tolist() == ["buy", "sell", "buy"]
    assert res.trades["fill_price"].tolist() == [110.0, 99.0, 120.0]
    # Equity is labelled by the open at which it is measured
    assert res.equity.index[0] == tiny_prices.index[1]
    assert res.equity.index[-1] == tiny_prices.index[5]


def test_costs_charged_per_unit_turnover(tiny_prices):
    target = pd.Series([1.0, 0, 0, 1, 1, 1], index=tiny_prices.index)
    res = run_backtest(tiny_prices, target, cost_bps=10)
    c = 0.001
    expected = (1 - 0.1 - c) * (1 - c) * 1.0 * (1 + 0.1 - c)
    assert res.equity.iloc[-1] == pytest.approx(expected)


def test_always_long_equals_buy_and_hold(random_prices):
    target = pd.Series(1.0, index=random_prices.index)
    res = run_backtest(random_prices, target, cost_bps=5)
    pd.testing.assert_series_equal(res.equity, res.benchmark, check_names=False)


def test_always_cash_stays_flat(random_prices):
    target = pd.Series(0.0, index=random_prices.index)
    res = run_backtest(random_prices, target)
    assert (res.equity == 1.0).all()
    assert summarise(res)["time_in_market"] == 0


def test_max_drawdown_known_series():
    eq = pd.Series([1.0, 1.2, 0.9, 1.3, 1.04], index=pd.bdate_range("2024-01-01", periods=5))
    assert max_drawdown(eq) == pytest.approx(0.9 / 1.2 - 1)
