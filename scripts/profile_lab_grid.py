"""Measure the Strategy Lab's worst-case cold recompute time, to settle D-09 (Plan 05).

Usage (from the repo root, reads the committed snapshot, no network):
    python -m scripts.profile_lab_grid

Prints each component's cold time, then the worst-case cold sum for one sidebar change
((a) heatmap + (c) 24-rule grid + (d) rolling-start + (e) is_oos_split), and the resulting
D-09 decision against SETTINGS.grid_debounce_threshold_s.
"""
from __future__ import annotations

import time

from core.config import SETTINGS
from core.grid import (
    heatmap_grid,
    is_oos_split,
    notebook_strategies,
    rolling_start_strategy,
    run_strategy_grid,
)
from core.indicators import MASpec
from core.signals import MACrossoverStrategy
from core.storage import load_prices, price_basis

_DEFAULT_SHORT = MASpec(*SETTINGS.lab_default_short)
_DEFAULT_LONG = MASpec(*SETTINGS.lab_default_long)
_DEFAULT_STRATEGY = MACrossoverStrategy(_DEFAULT_SHORT, _DEFAULT_LONG)


def _time(label: str, fn) -> float:
    start = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - start
    print(f"{label}: {elapsed:.3f}s")
    return elapsed


def main() -> None:
    raw = load_prices(SETTINGS.prices_path)
    prices = price_basis(raw, "total_return")

    print(f"Loaded {len(prices)} rows ({prices.index[0].date()} to {prices.index[-1].date()})")
    print()

    a = _time(
        "(a) heatmap_grid, ema/sma, full history 1993 -> latest",
        lambda: heatmap_grid(
            prices, _DEFAULT_SHORT.kind, _DEFAULT_LONG.kind,
            SETTINGS.heatmap_short_range, SETTINGS.heatmap_long_range,
        ),
    )
    _time(
        "(b) heatmap_grid, ema/sma, D-01 default window",
        lambda: heatmap_grid(
            prices, _DEFAULT_SHORT.kind, _DEFAULT_LONG.kind,
            SETTINGS.heatmap_short_range, SETTINGS.heatmap_long_range,
            start=SETTINGS.lab_default_start, end=SETTINGS.lab_default_end,
        ),
    )
    c = _time(
        "(c) run_strategy_grid, 24 notebook rules, full history",
        lambda: run_strategy_grid(prices, notebook_strategies()),
    )
    d = _time(
        "(d) rolling_start_strategy, EMA10/SMA200, full history",
        lambda: rolling_start_strategy(prices, _DEFAULT_STRATEGY),
    )
    e = _time(
        "(e) is_oos_split, EMA10/SMA200, default split",
        lambda: is_oos_split(prices, _DEFAULT_STRATEGY, SETTINGS.default_split),
    )

    worst_case = a + c + d + e
    print()
    print(f"Worst-case cold sum for one sidebar change (a+c+d+e): {worst_case:.3f}s")
    print(f"SETTINGS.grid_debounce_threshold_s: {SETTINGS.grid_debounce_threshold_s:.3f}s")
    if worst_case <= SETTINGS.grid_debounce_threshold_s:
        print("D-09 decision: REACTIVE OK")
    else:
        print("D-09 decision: DEBOUNCE NEEDED")


if __name__ == "__main__":
    main()
