"""Sidebar controls shared by every page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

# Total return listed first: it's the honest default per SPEC.md (OVER-06).
BASIS_LABELS = {"Total return": "total_return", "Price only": "price_only"}


def price_basis_input(key: str) -> str:
    """Render the price-basis radio and return the selected basis value."""
    label = st.sidebar.radio("Price basis", list(BASIS_LABELS), key=key, horizontal=True)
    return BASIS_LABELS[label]


def date_range_input(
    index: pd.DatetimeIndex,
    default_start: pd.Timestamp,
    default_end: pd.Timestamp,
    key: str,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Render a bounded date range input, falling back to the defaults on a partial selection."""
    value = st.sidebar.date_input(
        "Date range",
        value=(default_start.date(), default_end.date()),
        min_value=index[0].date(),
        max_value=index[-1].date(),
        key=key,
    )
    if not isinstance(value, tuple) or len(value) < 2:
        return default_start, default_end
    start, end = pd.Timestamp(value[0]), pd.Timestamp(value[1])
    if start > end:
        start, end = end, start
    return start, end
