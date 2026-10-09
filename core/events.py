"""Shock/gap/drawdown/rally detection and clustering into episodes (DET-01..07).

Pure: no Streamlit import, no network call, must not import core.data or core.storage.
The caller passes a price frame on whatever basis it wants (jobs/detect_events.py passes
total return, per CLAUDE.md's honesty rule). Every threshold arrives via a Settings
argument -- no literals in function bodies that encode a detection rule. Trading-day
distances use integer positions in the DatetimeIndex, never pd.Timedelta, so weekends and
holidays never silently stretch a window (D-01, mirrors core/market_calendar.py's
rationale).

Replay stability (DET-05): every episode carries a "status" of "closed" or "open". A
closed episode's fields (episode_id, start/end/anchor dates, trigger, triggers, search
window, recovery_date, move_pct/max_z/severity) can never change when more rows are
appended to `close`/`open_` -- see closure_frontier's docstring for the proof. An open
episode's fields, including its episode_id, may still change as the episode grows;
downstream consumers (Phase 3's paid news enrichment) must only enrich closed episodes.

Known limitation (not fixed here, accepted per DET-05's contract): Yahoo re-adjusts
adj_close on every dividend ex-date. Total-return ratios used for thresholds are
scale-invariant under a uniform adjustment, but rounding in a re-downloaded adj_close
could in principle flip a borderline threshold crossing right at the boundary of a
closed window. The replay test proves stability under *append-only* data -- that is
DET-05's contract, not immunity to upstream data revision (core/validate.py's D-13
rewrite-tolerance gate already bounds how much adj_close itself is allowed to be
rewritten).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.config import Settings

EPISODE_COLUMNS = [
    "episode_id",
    "start_date",
    "end_date",
    "anchor_date",
    "direction",
    "trigger",
    "triggers",
    "move_pct",
    "max_z",
    "severity",
    "search_from",
    "search_to",
    "recovery_date",
    "status",
    "detector_version",
]


@dataclass(frozen=True)
class Leg:
    """One detected primitive: a single shock/gap day, or a drawdown/rally span."""

    kind: str
    start_pos: int
    end_pos: int
    move: float
    recovery_pos: int | None
    # Last position whose data can still change this leg. A rally's merged candidate span
    # can run past its peak (end_pos); a future candidate starting inside the span would
    # merge into it and move the peak. None means end_pos.
    reach_pos: int | None = None


def log_returns(close: pd.Series) -> pd.Series:
    """Daily log return: log(close_t / close_t-1)."""
    return np.log(close / close.shift(1))


def shock_zscores(close: pd.Series, sigma_window: int) -> pd.Series:
    """Log return divided by sigma estimated over the prior sigma_window days (lagged one day).

    The lag means the sigma used to flag day t never includes day t itself (DET-01).
    """
    ret = log_returns(close)
    sigma = ret.rolling(sigma_window, min_periods=sigma_window).std().shift(1)
    return ret / sigma


def shock_days(close: pd.Series, sigma_window: int, z_threshold: float) -> pd.DatetimeIndex:
    """Dates where |shock z-score| exceeds z_threshold (DET-01)."""
    z = shock_zscores(close, sigma_window)
    return z.index[z.abs() > z_threshold]


def gap_days(open_: pd.Series, close: pd.Series, threshold: float) -> pd.DatetimeIndex:
    """Dates where |open / prev close - 1| exceeds threshold (DET-02)."""
    gap = open_ / close.shift(1) - 1
    return gap.index[gap.abs() > threshold]


def drawdown_legs(close: pd.Series, threshold: float) -> list[Leg]:
    """Peak-to-trough legs of at least `threshold` depth, single causal pass (DET-03).

    Same running-peak scan as core/regimes.py::drawdown_table, but position-indexed and
    filtered to episodes at least `threshold` deep. Trough is the earliest position of the
    minimum close since the peak. An episode still open at the end of data is emitted with
    recovery_pos=None (D-01: the steepest leg is what matters for clustering, not whether
    price has since made a new high).
    """
    legs: list[Leg] = []
    values = close.to_numpy(dtype=float)
    n = len(values)
    peak_price = values[0]
    peak_pos = 0
    in_episode = False
    episode_start_pos: int | None = None

    for i in range(n):
        price = values[i]
        if price >= peak_price:
            if in_episode:
                segment = values[episode_start_pos : i + 1]
                trough_pos = episode_start_pos + int(segment.argmin())
                trough_price = values[trough_pos]
                move = trough_price / peak_price - 1
                if move <= -threshold:
                    legs.append(Leg("drawdown", peak_pos, trough_pos, move, i))
                in_episode = False
            peak_price = price
            peak_pos = i
        elif not in_episode:
            in_episode = True
            episode_start_pos = i - 1

    if in_episode:
        segment = values[episode_start_pos:]
        trough_pos = episode_start_pos + int(segment.argmin())
        trough_price = values[trough_pos]
        move = trough_price / peak_price - 1
        if move <= -threshold:
            legs.append(Leg("drawdown", peak_pos, trough_pos, move, None))

    return legs


def rally_legs(close: pd.Series, threshold: float, window: int) -> list[Leg]:
    """Trough-to-peak legs of at least `threshold` gain completed within `window` days (DET-03).

    For each position i, finds the earliest minimum over the trailing `window` days; if the
    rise from that trough to i is at least `threshold`, the (trough, i) interval is a
    candidate. Overlapping/touching candidates merge (sort-and-sweep), then each merged
    span's true trough (earliest min) and peak (earliest max after the trough) are located.
    The span's end is kept as the leg's reach_pos, since closure must wait for it.
    """
    values = close.to_numpy(dtype=float)
    n = len(values)
    candidates: list[tuple[int, int]] = []
    for i in range(n):
        lo = max(0, i - window)
        segment = values[lo : i + 1]
        j = lo + int(segment.argmin())
        if values[i] / values[j] - 1 >= threshold:
            candidates.append((j, i))

    if not candidates:
        return []

    candidates.sort(key=lambda pair: pair[0])
    merged: list[list[int]] = [list(candidates[0])]
    for start, end in candidates[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    legs: list[Leg] = []
    for start, end in merged:
        segment = values[start : end + 1]
        trough_pos = start + int(segment.argmin())
        peak_segment = values[trough_pos : end + 1]
        peak_pos = trough_pos + int(peak_segment.argmax())
        move = values[peak_pos] / values[trough_pos] - 1
        legs.append(Leg("rally", trough_pos, peak_pos, move, None, reach_pos=end))

    return legs


def cluster_legs(legs: list[Leg], merge_window_days: int) -> list[list[Leg]]:
    """Merge legs within merge_window_days trading days into clusters (DET-04).

    Per D-01, clustering uses each leg's own (start_pos, end_pos) -- the steepest leg for
    drawdown/rally, a single day for shock/gap -- never recovery_pos. Sorted sweep: a leg
    joins the current cluster when its start is within merge_window_days of the cluster's
    current end; otherwise it starts a new cluster.
    """
    if not legs:
        return []
    ordered = sorted(legs, key=lambda leg: (leg.start_pos, leg.end_pos, leg.kind))
    clusters: list[list[Leg]] = [[ordered[0]]]
    cluster_end = ordered[0].end_pos
    for leg in ordered[1:]:
        if leg.start_pos - cluster_end <= merge_window_days:
            clusters[-1].append(leg)
            cluster_end = max(cluster_end, leg.end_pos)
        else:
            clusters.append([leg])
            cluster_end = leg.end_pos
    return clusters


def closure_frontier(close: pd.Series, settings: Settings) -> int:
    """First integer position that future (not-yet-seen) rows could still touch (DET-05).

    A cluster with ``reach + settings.merge_window_days < closure_frontier(...)``, where
    ``reach`` is the largest of its legs' end_pos and reach_pos, can never be changed by
    appending more rows to `close`, and is therefore safe to mark "closed". Proof, by the
    three ways a future row could reach back into an existing cluster:

    (a) A future shock/gap leg is a single day at the first not-yet-seen position,
        ``len(close)``. It can only start there or later.
    (b) A future rally candidate (trough j, i) flagged at some future position i looks
        back at most ``settings.rally_window_days`` bars for its trough (see rally_legs),
        so ``j >= len(close) - settings.rally_window_days``. rally_legs merges a candidate
        into an existing span when j is at or before that span's end -- the leg's
        reach_pos, which can lie past its peak -- so the cluster test uses reach, not
        end_pos. With ``reach < frontier <= j`` no future candidate can join an existing
        span, and a new span's leg starts at j, more than merge_window_days past reach.
    (c) A future drawdown leg can only start at a peak position. If the last observed
        close is below the series' own running all-time peak (by any depth -- a shallow
        dip may deepen into a qualifying leg later), that peak's position is still a live
        candidate for a future drawdown leg's start_pos, so it is also a lower bound on
        what future data can touch.

    `closure_frontier` is the minimum of (a), (b) and whichever of (c) applies. Positions
    at or after it may still be absorbed into a cluster that currently ends before it,
    because cluster_legs' sweep-merge only ever extends a cluster's end forward and never
    reaches backward across a gap wider than merge_window_days. Everything used to compute
    a closed cluster's anchor_date, move_pct, max_z and severity is drawn only from
    positions inside [start_pos, reach]; the search window reaches at most
    max(search_post_days, structural_search_half_width) past end_pos, which stays before
    the frontier while that is at most merge_window_days (asserted in tests/test_episode_replay.py).
    shock_zscores' rolling sigma is itself causal (lagged one day), so it never reaches
    into future rows either. A closed cluster's fields are therefore a pure function of data
    already fixed at closure time.
    """
    n = len(close)
    candidates = [n, n - settings.rally_window_days]
    values = close.to_numpy(dtype=float)
    running_peak = np.maximum.accumulate(values)
    if values[-1] < running_peak[-1]:
        at_peak = np.nonzero(values == running_peak)[0]
        candidates.append(int(at_peak[-1]))
    return min(candidates)


def detect(prices: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Detect and cluster shock/gap/drawdown/rally primitives into episodes (DET-01..07).

    `prices` must carry open/close on the basis the caller wants thresholds measured on
    (jobs/detect_events.py passes total return). Returns a DataFrame with EPISODE_COLUMNS,
    sorted by start_date. Raises ValueError if two clusters produce the same episode_id
    (should be impossible, since clusters are disjoint position ranges).
    """
    close = prices["close"]
    open_ = prices["open"]
    index = close.index
    n = len(close)

    ret = log_returns(close)
    z = shock_zscores(close, settings.shock_sigma_window)

    legs: list[Leg] = []
    for date in shock_days(close, settings.shock_sigma_window, settings.shock_z_threshold):
        pos = index.get_loc(date)
        legs.append(Leg("shock", pos, pos, float(ret.loc[date]), None))
    for date in gap_days(open_, close, settings.gap_threshold):
        pos = index.get_loc(date)
        legs.append(Leg("gap", pos, pos, float(ret.loc[date]), None))
    legs.extend(drawdown_legs(close, settings.drawdown_threshold))
    legs.extend(rally_legs(close, settings.rally_threshold, settings.rally_window_days))

    frontier = closure_frontier(close, settings)

    rows: list[dict] = []
    seen_ids: set[str] = set()
    for cluster in cluster_legs(legs, settings.merge_window_days):
        start_pos = min(leg.start_pos for leg in cluster)
        end_pos = max(leg.end_pos for leg in cluster)
        reach = max(
            leg.end_pos if leg.reach_pos is None else leg.reach_pos for leg in cluster
        )
        kinds = {leg.kind for leg in cluster}
        trigger = next(kind for kind in settings.trigger_precedence if kind in kinds)
        triggers = ",".join(sorted(kinds))

        window_rets = ret.iloc[start_pos : end_pos + 1].to_numpy(dtype=float)
        anchor_offset = int(np.nanargmax(np.abs(window_rets)))
        anchor_pos = start_pos + anchor_offset
        anchor_date = index[anchor_pos]

        if trigger == "drawdown":
            direction = "down"
        elif trigger == "rally":
            direction = "up"
        else:
            direction = "down" if ret.iloc[anchor_pos] < 0 else "up"

        if trigger == "drawdown":
            move_pct = min(leg.move for leg in cluster if leg.kind == "drawdown")
        elif trigger == "rally":
            move_pct = max(leg.move for leg in cluster if leg.kind == "rally")
        else:
            prior_pos = max(start_pos - 1, 0)
            move_pct = float(close.iloc[end_pos] / close.iloc[prior_pos] - 1)

        z_window = z.iloc[start_pos : end_pos + 1].abs().to_numpy(dtype=float)
        max_z = float(np.nanmax(z_window)) if np.isfinite(z_window).any() else 0.0

        severity = max_z + abs(move_pct) / settings.severity_move_step

        if trigger in ("drawdown", "rally"):
            cluster_rets = ret.iloc[start_pos : end_pos + 1].to_numpy(dtype=float)
            if trigger == "drawdown":
                steepest_offset = int(np.nanargmin(cluster_rets))
            else:
                steepest_offset = int(np.nanargmax(cluster_rets))
            steepest_pos = start_pos + steepest_offset
            half_width = settings.structural_search_half_width
            search_from_pos = steepest_pos - half_width
            search_to_pos = steepest_pos + half_width
        else:
            search_from_pos = start_pos - settings.search_pre_days
            search_to_pos = end_pos + settings.search_post_days
        search_from_pos = min(max(search_from_pos, 0), n - 1)
        search_to_pos = min(max(search_to_pos, 0), n - 1)

        drawdown_in_cluster = [leg for leg in cluster if leg.kind == "drawdown"]
        drawdown_recovered = all(leg.recovery_pos is not None for leg in drawdown_in_cluster)
        if not drawdown_in_cluster or not drawdown_recovered:
            recovery_date = pd.NaT
        else:
            recovery_pos = max(leg.recovery_pos for leg in drawdown_in_cluster)
            recovery_date = index[recovery_pos]

        status = (
            "closed"
            if reach + settings.merge_window_days < frontier and drawdown_recovered
            else "open"
        )

        episode_id = f"{anchor_date:%Y-%m-%d}_{trigger}"
        if episode_id in seen_ids:
            raise ValueError(f"duplicate episode_id: {episode_id!r}")
        seen_ids.add(episode_id)

        rows.append(
            {
                "episode_id": episode_id,
                "start_date": index[start_pos],
                "end_date": index[end_pos],
                "anchor_date": anchor_date,
                "direction": direction,
                "trigger": trigger,
                "triggers": triggers,
                "move_pct": move_pct,
                "max_z": max_z,
                "severity": severity,
                "search_from": index[search_from_pos],
                "search_to": index[search_to_pos],
                "recovery_date": recovery_date,
                "status": status,
                "detector_version": settings.detector_version,
            }
        )

    episodes = pd.DataFrame(rows, columns=EPISODE_COLUMNS)
    return episodes.sort_values("start_date").reset_index(drop=True)
