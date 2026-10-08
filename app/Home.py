"""Entrypoint: `streamlit run app/Home.py`.

Uses st.navigation + st.Page (not the legacy app/pages/ auto-discovery) per CLAUDE.md's
correction to the original spec and SKELETON.md's architectural decision — this keeps
Streamlit from ever mixing the two navigation models.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

st.set_page_config(page_title="SPY Market Lens", layout="wide")

pg = st.navigation(
    [
        st.Page(
            "views/overview.py",
            title="Overview",
            icon=":material/show_chart:",
            url_path="overview",
            default=True,
        ),
        st.Page(
            "views/strategy_lab.py",
            title="Strategy Lab",
            icon=":material/science:",
            url_path="strategy-lab",
        ),
    ]
)
pg.run()
