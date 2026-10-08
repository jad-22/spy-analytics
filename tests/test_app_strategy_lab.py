"""End-to-end AppTest coverage for the Strategy Lab page (LAB-01..04, LAB-09, LAB-10)."""
from __future__ import annotations

import re
import socket
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app.components.lab_charts import heatmap_figure, rolling_figure, scatter_figure
from app.components.lab_compute import heatmap_for, headline_grid
from core.config import SETTINGS
from core.grid import HeatmapResult, rolling_start_strategy
from core.indicators import MASpec
from core.signals import MACrossoverStrategy

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


def test_robustness_sections_render():
    at = AppTest.from_file(STRATEGY_LAB_PATH, default_timeout=120).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 4
    assert len(at.dataframe) >= 3
    captions = [c.value for c in at.caption]
    joined = "\n".join(captions)
    assert "look for plateaus, not spikes" in joined.lower()
    assert "not a recommendation" in joined
    assert "1993" in joined
    assert "ignoring the sidebar dates" in joined
    assert "regardless of the sidebar end date" in joined


def test_split_date_change():
    at = AppTest.from_file(STRATEGY_LAB_PATH, default_timeout=120).run()
    at.sidebar.date_input(key="lab_split").set_value(pd.Timestamp("2018-12-31").date())
    at.run()
    assert not at.exception


def test_heatmap_figure_contract():
    excess = pd.DataFrame(
        [[-0.1, 0.05, 0.2], [0.0, 0.1, -0.05]],
        index=[10, 20],
        columns=[100, 150, 200],
    )
    hm = HeatmapResult(
        excess=excess, start=pd.Timestamp("2010-01-01"), end=pd.Timestamp("2020-01-01")
    )
    fig = heatmap_figure(hm, selected_short=10, selected_long=150)
    assert fig.data[0].type == "heatmap"
    assert fig.data[0].zmid == 0
    colorscale = fig.data[0].colorscale
    assert colorscale[0][1] == "#C0152F"
    assert colorscale[-1][1] == "#1A7F37"
    names = [trace.name for trace in fig.data]
    assert "Selected rule" in names


def test_scatter_has_25_points():
    grid = headline_grid(
        "total_return", SETTINGS.lab_default_start, SETTINGS.lab_default_end, 0.0, False
    )
    fig = scatter_figure(grid, "ema10__sma200")
    total_points = sum(len(trace.x) for trace in fig.data)
    assert total_points == 25


def test_rolling_figure_contract():
    strategy = MACrossoverStrategy(MASpec("ema", 10), MASpec("sma", 200))
    from app.components.store import get_prices

    prices = get_prices("total_return")
    rolling_df = rolling_start_strategy(prices, strategy, SETTINGS.rolling_horizon_years)
    fig = rolling_figure(rolling_df)
    assert fig.data[0].type == "bar"


def test_heatmap_uses_selected_type_pair():
    strategy = MACrossoverStrategy(MASpec("sma", 10), MASpec("ema", 200))
    hm = heatmap_for(
        strategy, "total_return", SETTINGS.lab_default_start, SETTINGS.lab_default_end, 0.0
    )
    assert hm is not None
    assert list(hm.excess.index) == sorted(hm.excess.index)
    assert list(hm.excess.columns) == sorted(hm.excess.columns)


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
