import pytest

from core.grid import (
    count_beating,
    default_pairs,
    evaluate_strategy,
    run_ma_grid,
    run_strategy_grid,
)


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
