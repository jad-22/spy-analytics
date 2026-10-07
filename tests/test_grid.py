import pytest

from core.grid import default_pairs, run_ma_grid


def test_grid_rules_share_one_window(random_prices):
    """Every rule must be measured over the same interval, so buy-and-hold is identical."""
    grid = run_ma_grid(random_prices, default_pairs())
    assert len(grid) == 24
    bh = grid["bh_total_return"].astype(float)
    assert bh.max() == pytest.approx(bh.min())
