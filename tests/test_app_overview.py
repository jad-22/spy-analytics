"""End-to-end AppTest coverage for the Overview skeleton (DATA-05, OVER-01, OVER-06)."""
from __future__ import annotations

import dataclasses
import socket
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from core.config import SETTINGS

# AppTest.from_file resolves relative paths against this test file's own directory, not
# cwd, so every call below passes an absolute path rooted at the repo root.
ROOT = Path(__file__).resolve().parents[1]
OVERVIEW_PATH = str(ROOT / "app/views/overview.py")
HOME_PATH = str(ROOT / "app/Home.py")


@pytest.fixture(autouse=True)
def _clear_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def test_overview_renders_from_committed_data():
    at = AppTest.from_file(OVERVIEW_PATH, default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Overview"
    assert len(at.get("plotly_chart")) >= 1


def test_overview_makes_no_network_calls(monkeypatch):
    # Loopback only: Windows' asyncio event loop creates a self-pipe via a loopback
    # socketpair() fallback, which calls socket.connect() internally on every AppTest
    # run — unrelated to app behavior. Block everything except 127.0.0.1/::1/localhost
    # so a real external call (e.g. to Yahoo Finance) still fails this test.
    allowed_hosts = {"127.0.0.1", "::1", "localhost"}
    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def _guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in allowed_hosts:
            raise RuntimeError(f"network call attempted to {host!r}")
        return original_connect(self, address, *args, **kwargs)

    def _guarded_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in allowed_hosts:
            raise RuntimeError(f"network call attempted to {host!r}")
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket, "create_connection", _guarded_create_connection)

    at = AppTest.from_file(OVERVIEW_PATH, default_timeout=60).run()
    assert not at.exception


def test_home_entrypoint_runs():
    at = AppTest.from_file(HOME_PATH, default_timeout=60).run()
    assert not at.exception


def test_price_basis_toggle():
    at = AppTest.from_file(OVERVIEW_PATH, default_timeout=60).run()
    at.sidebar.radio(key="overview_basis").set_value("Price only").run()
    assert not at.exception


def test_empty_state_when_data_missing(tmp_path, monkeypatch):
    from app.components import store

    missing_settings = dataclasses.replace(
        store.SETTINGS,
        prices_path=tmp_path / "missing.parquet",
        meta_path=tmp_path / "missing.json",
    )
    monkeypatch.setattr(store, "SETTINGS", missing_settings)

    at = AppTest.from_file(OVERVIEW_PATH, default_timeout=60).run()
    assert not at.exception

    values = [h.value for h in at.header] + [m.value for m in at.markdown]
    assert "No market data yet" in values


def test_kpi_strip_has_four_metrics():
    at = AppTest.from_file(OVERVIEW_PATH, default_timeout=60).run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert labels == ["YTD return", "Distance from ATH", "Current drawdown", "20D realised vol"]


def test_candlestick_switch():
    at = AppTest.from_file(OVERVIEW_PATH, default_timeout=60).run()
    at.sidebar.radio(key="overview_chart_type").set_value("Candlestick").run()
    assert not at.exception


def test_drawdown_table_rendered():
    at = AppTest.from_file(OVERVIEW_PATH, default_timeout=60).run()
    assert not at.exception
    assert len(at.dataframe) >= 1
    first_df = at.dataframe[0].value
    assert len(first_df) <= SETTINGS.top_drawdowns


def test_all_regimes_and_mas():
    at = AppTest.from_file(OVERVIEW_PATH, default_timeout=60).run()
    at.sidebar.multiselect(key="overview_mas").set_value(list(SETTINGS.overview_ma_options)).run()
    try:
        regimes_widget = at.sidebar.pills(key="overview_regimes")
    except KeyError:
        regimes_widget = None
    if regimes_widget is not None:
        regimes_widget.set_value(list(SETTINGS.drawdown_regimes)).run()
    else:
        at.sidebar.multiselect(key="overview_regimes").set_value(
            list(SETTINGS.drawdown_regimes)
        ).run()
    assert not at.exception


def test_ma_overlay_no_warmup_gap():
    from app.components.price_charts import price_figure
    from app.components.store import get_prices
    from core.indicators import MASpec

    full = get_prices("total_return")
    full_close = full["close"]
    sma200 = MASpec.from_label("sma200").compute(full_close)
    window = full.loc["2024-01-02":]
    overlays = {"sma200": sma200.loc[window.index[0] : window.index[-1]]}

    fig = price_figure(window, "Line", overlays, {})
    sma_trace = next(t for t in fig.data if t.name == "SMA 200")
    assert not pd.isna(sma_trace.y[0])
