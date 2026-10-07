"""End-to-end AppTest coverage for the Strategy Lab page (LAB-01..04, LAB-09, LAB-10)."""
from __future__ import annotations

import re
import socket
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_LAB_PATH = str(ROOT / "app/views/strategy_lab.py")


@pytest.fixture(autouse=True)
def _clear_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def test_default_headline():
    at = AppTest.from_file(STRATEGY_LAB_PATH, default_timeout=120).run()
    assert not at.exception
    values = [m.value for m in at.markdown]
    assert any("0 of 24 rules beat buy-and-hold in this window" in v for v in values)


def test_anchor_caption():
    at = AppTest.from_file(STRATEGY_LAB_PATH, default_timeout=120).run()
    assert not at.exception
    captions = [c.value for c in at.caption]
    assert any("On the notebook's 2010–2022 window" in c for c in captions)
    assert any("0 of 24" in c for c in captions)


def test_equity_and_metrics_render():
    at = AppTest.from_file(STRATEGY_LAB_PATH, default_timeout=120).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 1
    assert len(at.dataframe) >= 1


def test_trend_filter_and_cost():
    at = AppTest.from_file(STRATEGY_LAB_PATH, default_timeout=120).run()
    at.sidebar.toggle(key="lab_trend_filter").set_value(True)
    at.sidebar.slider(key="lab_cost").set_value(5.0)
    at.run()
    assert not at.exception
    values = [m.value for m in at.markdown]
    assert any(
        re.search(r"\d+ of 24 rules beat buy-and-hold in this window", v) for v in values
    )


def test_short_not_less_than_long_warns():
    at = AppTest.from_file(STRATEGY_LAB_PATH, default_timeout=120).run()
    at.sidebar.number_input(key="lab_short_period").set_value(60)
    at.sidebar.number_input(key="lab_long_period").set_value(60)
    at.run()
    assert not at.exception
    warnings = [w.value for w in at.warning]
    assert any("Short MA period must be shorter than the long MA period." in w for w in warnings)


def test_insufficient_history_warns():
    at = AppTest.from_file(STRATEGY_LAB_PATH, default_timeout=120).run()
    at.sidebar.date_input(key="lab_range").set_value(
        ("1993-02-01", "1993-06-30")
    )
    at.run()
    assert not at.exception
    warnings = [w.value for w in at.warning]
    assert any(
        "Not enough price history for this rule in the selected date range" in w
        for w in warnings
    )


def test_no_network(monkeypatch):
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

    at = AppTest.from_file(STRATEGY_LAB_PATH, default_timeout=120).run()
    assert not at.exception
