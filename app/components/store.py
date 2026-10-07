"""The one cached storage module for the app (DATA-05).

Views must read data only through this module, never through core.storage directly.
All functions read the module-level SETTINGS at call time (not at import time), so
tests can monkeypatch `store.SETTINGS` to point at a missing snapshot.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from core.config import SETTINGS
from core.storage import load_meta, load_prices, price_basis


# No ttl on purpose: each nightly data commit redeploys the app and restarts the
# process, which clears this cache. Do not add a ttl to hide a failed redeploy
# (CLAUDE.md).
@st.cache_data
def _read_prices(path_str: str) -> pd.DataFrame:
    return load_prices(path_str)


@st.cache_data
def _read_meta(path_str: str) -> dict:
    return load_meta(path_str)


@st.cache_data
def _prices_for_basis(path_str: str, basis: str) -> pd.DataFrame:
    raw = _read_prices(path_str)
    return price_basis(raw, basis)


def get_raw_prices() -> pd.DataFrame:
    """Raw OHLCV prices from the committed snapshot."""
    return _read_prices(str(SETTINGS.prices_path))


def get_prices(basis: str) -> pd.DataFrame:
    """Prices on the requested basis ('total_return' or 'price_only')."""
    return _prices_for_basis(str(SETTINGS.prices_path), basis)


def get_meta() -> dict:
    """Refresh metadata from the committed snapshot."""
    return _read_meta(str(SETTINGS.meta_path))


def require_data() -> dict:
    """Return meta.json if the committed snapshot exists, else render the empty state and stop."""
    try:
        meta = get_meta()
        get_raw_prices()
    except (FileNotFoundError, json.JSONDecodeError):
        st.header("No market data yet")
        st.write(
            "SPY price history hasn't been loaded yet. This updates automatically after "
            "the next scheduled refresh — check back after today's US market close."
        )
        st.stop()
        return {}
    return meta


def render_freshness(meta: dict) -> None:
    """Show a caption with data freshness, or a stale warning past SETTINGS.stale_after_days."""
    last_refresh = meta["last_refresh"]
    last_trading_day = meta["last_trading_day"]
    refreshed_at = datetime.fromisoformat(last_refresh)
    age_days = (datetime.now(UTC) - refreshed_at).days
    if age_days > SETTINGS.stale_after_days:
        st.caption(
            f"Data was last refreshed {last_refresh}. If this looks out of date, the "
            "nightly job may have failed — the app is still showing the last good snapshot."
        )
    else:
        st.caption(f"Data as of {last_trading_day} · refreshed {last_refresh}")
