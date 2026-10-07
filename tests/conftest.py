import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def tiny_prices():
    """Six days, hand-checkable. Close = open for simplicity."""
    idx = pd.bdate_range("2024-01-01", periods=6, name="date")
    opens = [100.0, 110.0, 99.0, 99.0, 120.0, 132.0]
    return pd.DataFrame({"open": opens, "high": opens, "low": opens, "close": opens,
                         "adj_close": opens, "volume": 1}, index=idx)


@pytest.fixture
def random_prices():
    """~6 years of geometric random-walk prices for property-style tests."""
    rng = np.random.default_rng(7)
    n = 1500
    idx = pd.bdate_range("2015-01-01", periods=n, name="date")
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.011, n)))
    open_ = close * np.exp(rng.normal(0, 0.003, n))
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.002,
                         "low": np.minimum(open_, close) * 0.998, "close": close,
                         "adj_close": close, "volume": 1_000}, index=idx)
