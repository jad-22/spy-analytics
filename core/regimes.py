"""Drawdown regimes and Overview KPIs. Pure; computed on whatever price basis the caller passes.

Thresholds and windows are passed in by callers from SETTINGS; no literals in function bodies.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from core.metrics import TRADING_DAYS


def drawdown_series(close: pd.Series) -> pd.Series:
    """Fractional drawdown from the running high: close / cummax - 1 (<= 0)."""
    return close / close.cummax() - 1


def regime_spans(
    drawdown: pd.Series, threshold: float
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Contiguous (first_date, last_date) runs where drawdown <= threshold."""
    mask = drawdown <= threshold
    spans: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    start = None
    prev_date = None
    for date, flag in mask.items():
        if flag:
            if start is None:
                start = date
            prev_date = date
        elif start is not None:
            spans.append((start, prev_date))
            start = None
    if start is not None:
        spans.append((start, prev_date))
    return spans


def drawdown_table(close: pd.Series, top_n: int) -> pd.DataFrame:
    """The top_n deepest drawdown episodes, sorted by depth ascending (deepest first).

    Columns: peak, trough, recovery (NaT if unrecovered), depth, days_underwater (bar count
    from peak to recovery, or to the last bar if the episode has not recovered).
    """
    drawdown = drawdown_series(close)
    episodes: list[dict] = []
    peak_price = float(close.iloc[0])
    peak_date = close.index[0]
    in_episode = False
    episode_start_idx: int | None = None

    for i, (date, price) in enumerate(close.items()):
        if price >= peak_price:
            if in_episode:
                episode_slice = drawdown.iloc[episode_start_idx : i + 1]
                episodes.append(
                    {
                        "peak": peak_date,
                        "trough": episode_slice.idxmin(),
                        "recovery": date,
                        "depth": float(episode_slice.min()),
                        "days_underwater": i - episode_start_idx,
                    }
                )
                in_episode = False
            peak_price = float(price)
            peak_date = date
        elif not in_episode:
            in_episode = True
            episode_start_idx = i - 1

    if in_episode:
        last_idx = len(close) - 1
        episode_slice = drawdown.iloc[episode_start_idx:]
        episodes.append(
            {
                "peak": peak_date,
                "trough": episode_slice.idxmin(),
                "recovery": pd.NaT,
                "depth": float(episode_slice.min()),
                "days_underwater": last_idx - episode_start_idx,
            }
        )

    table = pd.DataFrame(
        episodes, columns=["peak", "trough", "recovery", "depth", "days_underwater"]
    )
    return table.sort_values("depth", ascending=True).head(top_n).reset_index(drop=True)


def overview_kpis(close: pd.Series, vol_window: int) -> dict[str, float]:
    """YTD return, current drawdown, distance from all-time high and realised vol.

    ytd_return uses the last close over the last close of the prior calendar year; if no
    prior-year bar exists, it falls back to the first bar of the current year.
    """
    last = float(close.iloc[-1])
    current_year = close.index[-1].year
    prior_year_mask = close.index.year == current_year - 1
    if prior_year_mask.any():
        baseline = float(close[prior_year_mask].iloc[-1])
    else:
        current_year_mask = close.index.year == current_year
        baseline = float(close[current_year_mask].iloc[0])

    cummax = close.cummax()
    ath = float(cummax.max())

    log_returns = np.log(close / close.shift(1)).dropna()
    recent_vol = log_returns.iloc[-vol_window:]
    realised_vol = float(recent_vol.std() * math.sqrt(TRADING_DAYS))

    return {
        "ytd_return": last / baseline - 1,
        "current_drawdown": float(last / cummax.iloc[-1] - 1),
        "distance_from_ath": ath / last - 1,
        "realised_vol": realised_vol,
        "ath_date": close.idxmax(),
    }
