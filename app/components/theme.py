"""Semantic Plotly trace colours, shared across pages.

Theme (UI chrome) tokens live in .streamlit/config.toml; these are for financial-data
semantics (gain/loss, strategy vs buy-and-hold, drawdown shading) that Streamlit's theme
engine does not control. See 01-UI-SPEC.md Color section.
"""
from __future__ import annotations

STRATEGY_BLUE = "#1A5FB4"
BH_GRAY = "#6B7280"
GAIN_GREEN = "#1A7F37"
LOSS_RED = "#C0152F"

DRAWDOWN_OPACITY: dict[float, float] = {-0.05: 0.08, -0.10: 0.15, -0.20: 0.25}

DIVERGING_COLORSCALE = [[0.0, "#C0152F"], [0.5, "#FFFFFF"], [1.0, "#1A7F37"]]
