"""End-to-end AppTest coverage for the Overview skeleton (DATA-05, OVER-01, OVER-06)."""
from __future__ import annotations

import dataclasses
import socket
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

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
    def _blocked(*args, **kwargs):
        raise RuntimeError("network call attempted")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

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
