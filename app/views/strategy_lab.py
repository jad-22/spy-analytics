"""Strategy Lab page: live headline, selected rule's equity vs buy-and-hold, metrics table.

LAB-09/D-02/D-03's core honesty claim leads the page: "N of 24 rules beat buy-and-hold in
this window", recomputed live from the sidebar settings, anchored by the notebook's own
2010-2022 window. The view only ever constructs the active rule through the Strategy
interface (LAB-10) — it never calls ma_crossover/trend_filter/combine_all/MASpec directly.
"""
from __future__ import annotations

import streamlit as st

from app.components.lab_charts import (
    equity_figure,
    format_metrics,
    heatmap_figure,
    rolling_figure,
    scatter_figure,
)
from app.components.lab_compute import (
    headline_grid,
    heatmap_for,
    is_oos_for,
    phase0_anchor_count,
    rolling_for,
    selected_backtest,
)
from app.components.lab_sidebar import lab_settings, rule_input, split_input
from app.components.store import get_raw_prices, render_freshness, require_data
from core.config import SETTINGS
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

st.divider()

st.subheader("Short × long grid")
try:
    hm = heatmap_for(strategy, settings.basis, start_iso, end_iso, settings.cost_bps)
except ValueError:
    st.warning(_INSUFFICIENT_HISTORY_WARNING)
else:
    if hm is None:
        st.info("The grid applies to moving-average crossover rules.")
    else:
        short_kind = strategy.short.kind.upper()
        long_kind = strategy.long.kind.upper()
        st.plotly_chart(
            heatmap_figure(hm, strategy.short.period, strategy.long.period),
            theme="streamlit", width="stretch",
        )
        st.caption(
            f"Excess total return vs buy-and-hold for every {short_kind} short × "
            f"{long_kind} long period pair, window {hm.start:%Y-%m-%d} → "
            f"{hm.end:%Y-%m-%d}, same cost, basis and filter as above."
        )
        st.caption(
            "Look for plateaus, not spikes: a lone bright cell usually means the window "
            "was fitted, not that the rule works."
        )
        st.caption("The best cell is shown for reference, not a recommendation.")
        short_lo, short_hi, _ = SETTINGS.heatmap_short_range
        long_lo, long_hi, _ = SETTINGS.heatmap_long_range
        if not (short_lo <= strategy.short.period <= short_hi
                and long_lo <= strategy.long.period <= long_hi):
            st.caption("The selected rule lies outside the grid shown.")

st.divider()

st.subheader("Risk and return across the notebook rules")
try:
    scatter_grid = headline_grid(
        settings.basis, start_iso, end_iso, settings.cost_bps, settings.trend_filter
    )
except ValueError:
    st.warning(_INSUFFICIENT_HISTORY_WARNING)
else:
    st.plotly_chart(
        scatter_figure(scatter_grid, strategy.name), theme="streamlit", width="stretch"
    )
    st.caption(
        "Each blue dot is one of the 24 notebook rules; gray is buy-and-hold. Up and to "
        "the right is better."
    )

st.divider()

st.subheader("Does the start year matter?")
try:
    rolling_df = rolling_for(strategy, settings.basis, settings.cost_bps)
except ValueError:
    st.warning(_INSUFFICIENT_HISTORY_WARNING)
else:
    st.plotly_chart(rolling_figure(rolling_df), theme="streamlit", width="stretch")
    st.caption(
        "Uses full history (1993 → latest), ignoring the sidebar dates, to show how much "
        f"the result depends on when you start. Each bar is the excess total return over "
        f"the following {SETTINGS.rolling_horizon_years} years."
    )

st.divider()

st.subheader("In-sample vs out-of-sample")
last_date = get_raw_prices().index[-1]
split = split_input(settings, last_date)
try:
    is_result, oos_result = is_oos_for(
        strategy, settings.basis, start_iso, split.isoformat(), settings.cost_bps
    )
except ValueError:
    st.warning(_INSUFFICIENT_HISTORY_WARNING)
else:
    col_is, col_oos = st.columns(2, gap="large")
    with col_is, st.container(border=True):
        st.subheader(f"In-sample ({settings.start:%Y-%m-%d} → {split:%Y-%m-%d})")
        st.dataframe(format_metrics(metrics_table(is_result)))
    with col_oos, st.container(border=True):
        st.subheader(f"Out-of-sample ({split:%Y-%m-%d} → {last_date:%Y-%m-%d})")
        st.dataframe(format_metrics(metrics_table(oos_result)))
    st.caption(
        "Out-of-sample always runs from the split date to the latest data "
        f"({last_date:%Y-%m-%d}), regardless of the sidebar end date. The default split, "
        "2022-12-16, makes 2023 onward a true out-of-sample test of the notebook's rule."
    )
