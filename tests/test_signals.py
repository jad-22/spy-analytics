import pandas as pd

from core.indicators import MASpec
from core.signals import combine_all, crossings, crossover_target, ma_crossover


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
