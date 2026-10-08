import pandas as pd
import pytest

from core.grid import evaluate_strategy, run_strategy_grid
from core.indicators import MASpec
from core.signals import (
    MACrossoverStrategy,
    Strategy,
    combine_all,
    crossings,
    crossover_target,
    ma_crossover,
    trend_filter,
)


def test_crossover_target_and_crossings():
    idx = pd.bdate_range("2024-01-01", periods=5)
    short = pd.Series([1, 2, 4, 3, 1.0], index=idx)
    long = pd.Series([3, 3, 3, 3, 3.0], index=idx)
    target = crossover_target(short, long)
    assert target.tolist() == [0, 0, 1, 0, 0]
    x = crossings(target)
    assert x.to_dict() == {idx[2]: 1, idx[3]: -1}


def test_no_look_ahead(random_prices):
    """Changing prices after day k must not change any target up to day k."""
    s, lg = MASpec("ema", 10), MASpec("sma", 200)
    base = ma_crossover(random_prices["close"], s, lg)
    k = 900
    shocked = random_prices.copy()
    shocked.iloc[k + 1:, shocked.columns.get_loc("close")] *= 0.5
    after = ma_crossover(shocked["close"], s, lg)
    pd.testing.assert_series_equal(base.iloc[: k + 1], after.iloc[: k + 1])


def test_combine_all_is_logical_and():
    a = pd.Series([1.0, 1, 0, None])
    b = pd.Series([1.0, 0, 0, 1])
    assert combine_all(a.rename("a"), b.rename("b")).tolist()[:3] == [1, 0, 0]
    assert pd.isna(combine_all(a.rename("a"), b.rename("b")).iloc[3])


def test_ma_crossover_strategy_name_and_target(random_prices):
    strategy = MACrossoverStrategy(MASpec("ema", 10), MASpec("sma", 200))
    assert strategy.name == "ema10__sma200"
    expected = ma_crossover(random_prices["close"], MASpec("ema", 10), MASpec("sma", 200))
    pd.testing.assert_series_equal(strategy.target(random_prices), expected, check_names=False)


def test_ma_crossover_strategy_with_trend_filter(random_prices):
    strategy = MACrossoverStrategy(MASpec("ema", 10), MASpec("sma", 200), trend_filter_period=200)
    assert strategy.name == "ema10__sma200__trend200"
    base = ma_crossover(random_prices["close"], MASpec("ema", 10), MASpec("sma", 200))
    filt = trend_filter(random_prices["close"], 200)
    expected = combine_all(base, filt)
    pd.testing.assert_series_equal(strategy.target(random_prices), expected, check_names=False)


def test_ma_crossover_strategy_is_a_strategy():
    strategy = MACrossoverStrategy(MASpec("ema", 10), MASpec("sma", 200))
    assert isinstance(strategy, Strategy) is True


def test_custom_strategy_plugs_in(random_prices):
    class AlwaysLong:
        name = "always_long"
        label = "Always long"

        def target(self, prices: pd.DataFrame) -> pd.Series:
            return pd.Series(1.0, index=prices.index)

    strategy = AlwaysLong()
    result = evaluate_strategy(random_prices, strategy)
    pd.testing.assert_series_equal(result.equity, result.benchmark, check_names=False)

    grid = run_strategy_grid(random_prices, [strategy])
    assert grid.loc["always_long", "excess_total_return"] == pytest.approx(0.0, abs=1e-9)
