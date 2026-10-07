from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest
from core.storage import BASES, build_meta, load_meta, price_basis, write_meta

from core.data import to_total_return


def test_price_basis_total_return(tiny_prices):
    assert "total_return" in BASES
    result = price_basis(tiny_prices, "total_return")
    expected = to_total_return(tiny_prices)
    pd.testing.assert_frame_equal(result, expected)


def test_price_basis_price_only(tiny_prices):
    result = price_basis(tiny_prices, "price_only")
    pd.testing.assert_frame_equal(result, tiny_prices)


def test_price_basis_unknown_raises(tiny_prices):
    with pytest.raises(ValueError):
        price_basis(tiny_prices, "bogus")


def test_build_meta_fields(tiny_prices):
    tiny_prices.attrs["source"] = "yfinance"
    meta = build_meta(
        tiny_prices,
        ticker="SPY",
        refreshed_at=datetime(2024, 1, 9, 12, 0, 0, tzinfo=UTC),
        detector_version=0,
        schema_version=1,
    )
    expected_keys = {
        "schema_version", "ticker", "source", "last_refresh", "first_trading_day",
        "last_trading_day", "row_counts", "detector_version",
    }
    assert expected_keys <= set(meta.keys())
    assert meta["last_trading_day"] == "2024-01-08"
    assert meta["row_counts"] == {"prices": 6}
    assert meta["last_refresh"].endswith("Z")


def test_write_meta_load_meta_roundtrip(tmp_path, tiny_prices):
    tiny_prices.attrs["source"] = "yfinance"
    meta = build_meta(
        tiny_prices,
        ticker="SPY",
        refreshed_at=datetime.now(UTC),
        detector_version=0,
        schema_version=1,
    )
    path = tmp_path / "meta.json"
    write_meta(meta, path)
    loaded = load_meta(path)
    assert loaded == meta
