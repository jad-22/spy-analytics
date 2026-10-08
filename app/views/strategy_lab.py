"""Strategy Lab page: live headline, selected rule's equity vs buy-and-hold, metrics table.

LAB-09/D-02/D-03's core honesty claim leads the page: "N of 24 rules beat buy-and-hold in
this window", recomputed live from the sidebar settings, anchored by the notebook's own
2010-2022 window. The view only ever constructs the active rule through the Strategy
interface (LAB-10) — it never calls ma_crossover/trend_filter/combine_all/MASpec directly.
"""
from __future__ import annotations

import streamlit as st

from app.components.lab_charts import equity_figure, format_metrics
from app.components.lab_compute import headline_grid, phase0_anchor_count, selected_backtest
from app.components.lab_sidebar import lab_settings, rule_input
from app.components.store import get_raw_prices, render_freshness, require_data
from core.grid import count_beating
from core.metrics import metrics_table

_INSUFFICIENT_HISTORY_WARNING = (
    "Not enough price history for this rule in the selected date range. Try an earlier "
    "start date or a shorter moving-average period."
)

st.title("Strategy Lab")

meta = require_data()
render_freshness(meta)

settings = lab_settings(get_raw_prices().index)
strategy = rule_input(settings)

start_iso = settings.start.isoformat()
end_iso = settings.end.isoformat()

try:
    grid = headline_grid(
        settings.basis, start_iso, end_iso, settings.cost_bps, settings.trend_filter
    )
except ValueError:
    st.warning(_INSUFFICIENT_HISTORY_WARNING)
else:
    beats = count_beating(grid)
    st.markdown(f"## {beats} of {len(grid)} rules beat buy-and-hold in this window")
    st.caption(
        "On the notebook's 2010–2022 window (total return, 0 bps, no filter): "
        f"{phase0_anchor_count()} of 24."
    )
    if beats == 0:
        st.caption(
            "Every SMA/EMA crossover tested — including the notebook's old favorite, EMA10 vs SMA200 — "
            "trails a simple buy-and-hold on this window, any price basis, any cost setting."
        )
    else:
        st.caption(
            "Some of the 24 rules come out ahead in this particular window. Check the "
            "rolling-start chart and the out-of-sample split before reading this as an edge."
        )
    st.caption(
        "Beat means a higher total return than buy-and-hold over the same window, with the "
        "same next-open fills and costs. The count always uses the notebook's 24 SMA/EMA "
        "rules" + (" with the 200D trend filter" if settings.trend_filter else "") + "."
    )

st.divider()

st.header(strategy.label)
try:
    result = selected_backtest(strategy, settings.basis, start_iso, end_iso, settings.cost_bps)
except ValueError:
    st.warning(_INSUFFICIENT_HISTORY_WARNING)
else:
    st.plotly_chart(equity_figure(result, strategy.label), theme="streamlit", width="stretch")
    st.caption(
        f"Window {result.equity.index[0]:%Y-%m-%d} → {result.equity.index[-1]:%Y-%m-%d}. "
        "Signals at the close, filled at the next open; cash earns 0."
    )
    with st.container(border=True):
        st.subheader("Metrics")
        st.dataframe(format_metrics(metrics_table(result)))
