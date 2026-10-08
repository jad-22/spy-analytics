import pandas as pd
import pytest

from core.config import SETTINGS
from core.grid import (
    count_beating,
    default_pairs,
    evaluate_strategy,
    grid_window,
    heatmap_grid,
    heatmap_pairs,
    is_oos_split,
    rolling_start,
    rolling_start_strategy,
    run_ma_grid,
    run_strategy_grid,
)
from core.indicators import MASpec
from core.signals import MACrossoverStrategy


def test_grid_rules_share_one_window(random_prices):
    """Every rule must be measured over the same interval, so buy-and-hold is identical."""
    grid = run_ma_grid(random_prices, default_pairs())
    assert len(grid) == 24
    bh = grid["bh_total_return"].astype(float)
    assert bh.max() == pytest.approx(bh.min())


def test_run_ma_grid_with_trend_filter(random_prices):
    grid = run_ma_grid(random_prices, default_pairs(), trend_filter_period=200)
    assert len(grid) == 24
    assert all(name.endswith("__trend200") for name in grid.index)
    bh = grid["bh_total_return"].astype(float)
    assert bh.max() == pytest.approx(bh.min())


def test_run_strategy_grid_matches_run_ma_grid(random_prices):
    end = random_prices.index[1000]
    old = run_ma_grid(random_prices.loc[:end], default_pairs())
    new = run_ma_grid(random_prices, default_pairs(), end=end)
    pd_total_old = old["total_return"].sort_index()
    pd_total_new = new["total_return"].sort_index()
    for name in pd_total_old.index:
        assert pd_total_new[name] == pytest.approx(pd_total_old[name])


def test_run_strategy_grid_raises_on_insufficient_history(random_prices):
    from core.grid import notebook_strategies

    with pytest.raises(ValueError, match="Not enough price history"):
        run_strategy_grid(
            random_prices,
            notebook_strategies(),
            start=random_prices.index[0],
            end=random_prices.index[1],
        )


def test_count_beating(random_prices):
    grid = run_ma_grid(random_prices, default_pairs())
    assert count_beating(grid) == int((grid["excess_total_return"] > 0).sum())


def test_evaluate_strategy_matches_grid_row(random_prices):
    from core.grid import notebook_strategies

    strategies = notebook_strategies()
    grid = run_ma_grid(random_prices, default_pairs())
    strategy = next(s for s in strategies if s.name == "ema10__sma200")
    result = evaluate_strategy(random_prices, strategy)
    from core.metrics import total_return

    assert total_return(result.equity) == pytest.approx(grid.loc["ema10__sma200", "total_return"])


# --- Plan 05: heatmap, strategy-aware rolling start, IS/OOS split ---------------------


def test_heatmap_pairs_shape_and_edges():
    pairs = heatmap_pairs("ema", "sma", (5, 60, 5), (100, 250, 10))
    assert len(pairs) == 192  # 12 shorts * 16 longs
    assert pairs[0] == (MASpec("ema", 5), MASpec("sma", 100))
    assert pairs[-1] == (MASpec("ema", 60), MASpec("sma", 250))


def test_heatmap_pairs_excludes_short_not_less_than_long():
    pairs = heatmap_pairs("ema", "sma", (40, 60, 10), (50, 60, 10))
    kept = {(s.period, lg.period) for s, lg in pairs}
    assert kept == {(40, 50), (40, 60), (50, 60)}
    assert (50, 50) not in kept
    assert (60, 50) not in kept
    assert (60, 60) not in kept


def test_heatmap_grid_shape_and_matches_run_ma_grid(random_prices):
    pairs = heatmap_pairs("ema", "sma", (5, 15, 5), (30, 50, 10))
    hm = heatmap_grid(random_prices, "ema", "sma", (5, 15, 5), (30, 50, 10))
    assert hm.excess.shape == (3, 3)
    assert list(hm.excess.index) == [5, 10, 15]
    assert list(hm.excess.columns) == [30, 40, 50]

    grid = run_ma_grid(random_prices, pairs)
    for short, long in pairs:
        name = MACrossoverStrategy(short, long).name
        assert hm.excess.loc[short.period, long.period] == pytest.approx(
            grid.loc[name, "excess_total_return"]
        )

    strategies = [MACrossoverStrategy(s, lg) for s, lg in pairs]
    expected_start, _ = grid_window(random_prices, strategies)
    assert hm.start == expected_start


def test_heatmap_grid_with_trend_filter_differs(random_prices):
    unfiltered = heatmap_grid(random_prices, "ema", "sma", (5, 15, 5), (30, 50, 10))
    filtered = heatmap_grid(
        random_prices, "ema", "sma", (5, 15, 5), (30, 50, 10), trend_filter_period=200
    )
    assert not unfiltered.excess.equals(filtered.excess)


def test_rolling_start_strategy_matches_rolling_start(random_prices):
    by_strategy = rolling_start_strategy(
        random_prices, MACrossoverStrategy(MASpec("ema", 10), MASpec("sma", 200))
    )
    by_pair = rolling_start(random_prices, MASpec("ema", 10), MASpec("sma", 200))
    pd.testing.assert_frame_equal(by_strategy, by_pair)


def test_rolling_start_strategy_with_trend_filter_differs(random_prices):
    unfiltered = rolling_start_strategy(
        random_prices, MACrossoverStrategy(MASpec("ema", 10), MASpec("sma", 200))
    )
    filtered = rolling_start_strategy(
        random_prices,
        MACrossoverStrategy(MASpec("ema", 10), MASpec("sma", 200), trend_filter_period=200),
    )
    assert not unfiltered.equals(filtered)


def test_is_oos_split_contiguous_no_overlap(random_prices):
    strategy = MACrossoverStrategy(MASpec("ema", 10), MASpec("sma", 200))
    split = random_prices.index[1000]
    is_result, oos_result = is_oos_split(random_prices, strategy, split)
    assert is_result.equity.index[-1] == split
    assert oos_result.equity.index[0] == split
    assert is_result.equity.index[:-1].isin(oos_result.equity.index).sum() == 0


def test_is_oos_split_raises_when_split_outside_window(random_prices):
    strategy = MACrossoverStrategy(MASpec("ema", 10), MASpec("sma", 200))
    with pytest.raises(ValueError, match="Split date must fall inside the backtest window"):
        is_oos_split(random_prices, strategy, random_prices.index[0])
    with pytest.raises(ValueError, match="Split date must fall inside the backtest window"):
        is_oos_split(random_prices, strategy, random_prices.index[-1])


def test_heatmap_short_and_long_range_settings_give_192_pairs():
    pairs = heatmap_pairs(
        "ema", "sma", SETTINGS.heatmap_short_range, SETTINGS.heatmap_long_range
    )
    assert len(pairs) == 192
