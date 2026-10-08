from __future__ import annotations

import pandas as pd

from core.config import SETTINGS
from core.data import COLUMNS, write_prices
from core.market_calendar import nyse_sessions
from core.storage import load_meta
from jobs import refresh_prices


def _gapless_frame():
    """A real-NYSE-session gapless frame, so the D-13 gap check never rejects it."""
    idx = nyse_sessions("2024-01-02", "2024-01-10")
    opens = [100.0, 110.0, 99.0, 99.0, 120.0, 132.0, 140.0]
    return pd.DataFrame(
        {
            "open": opens, "high": opens, "low": opens, "close": opens,
            "adj_close": opens, "volume": 1,
        },
        index=idx,
    )


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


def test_main_success_writes_prices_and_meta(tmp_path, monkeypatch):
    gapless = _gapless_frame()
    gapless.attrs["source"] = "yfinance"

    def fake_fetch(ticker, start, end=None):
        return gapless

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
    assert meta["row_counts"] == {"prices": 7}
    assert meta["detector_version"] == SETTINGS.detector_version
    assert meta["last_trading_day"] == "2024-01-10"


def test_main_requests_history_start(tmp_path, monkeypatch):
    gapless = _gapless_frame()
    gapless.attrs["source"] = "yfinance"
    recorded = {}

    def fake_fetch(ticker, start, end=None):
        recorded["start"] = start
        return gapless

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


def test_main_exits_1_on_validation_failure_and_keeps_files(tmp_path, monkeypatch):
    gapless = _gapless_frame()
    gapless.attrs["source"] = "yfinance"

    prices_path = tmp_path / "prices.parquet"
    meta_path = tmp_path / "meta.json"
    write_prices(gapless, prices_path)
    meta_path.write_text('{"existing": true}')

    before_prices = prices_path.read_bytes()
    before_meta = meta_path.read_bytes()

    bad = gapless.copy()
    bad.loc[bad.index[0], "close"] *= 1.01  # 1% historical rewrite, beyond tolerance

    def fake_fetch(ticker, start, end=None):
        return bad

    monkeypatch.setattr(refresh_prices, "fetch_yfinance", fake_fetch)

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


def test_main_exits_1_when_fetched_history_shrinks(tmp_path, monkeypatch):
    gapless = _gapless_frame()
    gapless.attrs["source"] = "yfinance"

    prices_path = tmp_path / "prices.parquet"
    meta_path = tmp_path / "meta.json"
    write_prices(gapless, prices_path)
    meta_path.write_text('{"existing": true}')

    before_prices = prices_path.read_bytes()
    before_meta = meta_path.read_bytes()

    shrunk = gapless.iloc[:-5]

    def fake_fetch(ticker, start, end=None):
        return shrunk

    monkeypatch.setattr(refresh_prices, "fetch_yfinance", fake_fetch)

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


def test_main_first_run_without_existing_snapshot_writes(tmp_path, monkeypatch):
    gapless = _gapless_frame()
    gapless.attrs["source"] = "yfinance"

    prices_path = tmp_path / "prices.parquet"
    meta_path = tmp_path / "meta.json"
    assert not prices_path.exists()

    def fake_fetch(ticker, start, end=None):
        return gapless

    monkeypatch.setattr(refresh_prices, "fetch_yfinance", fake_fetch)

    exit_code = refresh_prices.main(
        [
            "--prices-path", str(prices_path),
            "--meta-path", str(meta_path),
            "--retry-wait-max", "0",
        ]
    )

    assert exit_code == 0
