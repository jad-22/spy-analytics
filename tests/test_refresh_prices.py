from __future__ import annotations

import pandas as pd

from core.config import SETTINGS
from core.data import COLUMNS, write_prices
from core.storage import load_meta
from jobs import refresh_prices


def test_fetch_yfinance_pins_auto_adjust_and_flat_columns(monkeypatch):
    from core.data import fetch_yfinance

    captured = {}

    def fake_download(ticker, start=None, end=None, auto_adjust=None, progress=None):
        captured["kwargs"] = {"auto_adjust": auto_adjust, "start": start, "end": end}
        idx = pd.bdate_range("2024-01-01", periods=3, name="Date")
        cols = pd.MultiIndex.from_product(
            [["Open", "High", "Low", "Close", "Adj Close", "Volume"], ["SPY"]]
        )
        return pd.DataFrame(1.0, index=idx, columns=cols)

    monkeypatch.setattr("yfinance.download", fake_download)
    result = fetch_yfinance("SPY", start="2024-01-01")

    assert captured["kwargs"]["auto_adjust"] is False
    assert list(result.columns) == COLUMNS


def test_fetch_with_retry_retries_then_succeeds(tiny_prices, monkeypatch):
    calls = {"n": 0}

    def fake_fetch(ticker, start, end=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return tiny_prices

    monkeypatch.setattr(refresh_prices, "fetch_yfinance", fake_fetch)
    result = refresh_prices.fetch_with_retry(
        "SPY", "1993-01-29", attempts=4, wait_min_s=0, wait_max_s=0
    )

    pd.testing.assert_frame_equal(result, tiny_prices)
    assert calls["n"] == 3


def test_main_exits_1_and_leaves_snapshot_on_final_failure(tmp_path, tiny_prices, monkeypatch):
    prices_path = tmp_path / "prices.parquet"
    meta_path = tmp_path / "meta.json"
    write_prices(tiny_prices, prices_path)
    meta_path.write_text('{"existing": true}')

    before_prices = prices_path.read_bytes()
    before_meta = meta_path.read_bytes()

    def always_fail(ticker, start, end=None):
        raise RuntimeError("yahoo is down")

    monkeypatch.setattr(refresh_prices, "fetch_yfinance", always_fail)

    exit_code = refresh_prices.main(
        [
            "--prices-path", str(prices_path),
            "--meta-path", str(meta_path),
            "--retry-wait-max", "0",
        ]
    )

    assert exit_code == 1
    assert prices_path.read_bytes() == before_prices
    assert meta_path.read_bytes() == before_meta


def test_main_success_writes_prices_and_meta(tmp_path, tiny_prices, monkeypatch):
    tiny_prices.attrs["source"] = "yfinance"

    def fake_fetch(ticker, start, end=None):
        return tiny_prices

    monkeypatch.setattr(refresh_prices, "fetch_yfinance", fake_fetch)

    prices_path = tmp_path / "prices.parquet"
    meta_path = tmp_path / "meta.json"

    exit_code = refresh_prices.main(
        [
            "--prices-path", str(prices_path),
            "--meta-path", str(meta_path),
            "--retry-wait-max", "0",
        ]
    )

    assert exit_code == 0
    meta = load_meta(meta_path)
    assert meta["row_counts"] == {"prices": 6}
    assert meta["detector_version"] == SETTINGS.detector_version
    assert meta["last_trading_day"] == "2024-01-08"


def test_main_requests_history_start(tmp_path, tiny_prices, monkeypatch):
    tiny_prices.attrs["source"] = "yfinance"
    recorded = {}

    def fake_fetch(ticker, start, end=None):
        recorded["start"] = start
        return tiny_prices

    monkeypatch.setattr(refresh_prices, "fetch_yfinance", fake_fetch)

    prices_path = tmp_path / "prices.parquet"
    meta_path = tmp_path / "meta.json"
    refresh_prices.main(
        [
            "--prices-path", str(prices_path),
            "--meta-path", str(meta_path),
            "--retry-wait-max", "0",
        ]
    )

    assert recorded["start"] == SETTINGS.history_start
