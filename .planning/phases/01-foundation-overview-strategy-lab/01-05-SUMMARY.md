---
phase: 01-foundation-overview-strategy-lab
plan: 05
subsystem: ui
tags: [streamlit, plotly, backtest, heatmap, rolling-window, in-sample-out-of-sample]

# Dependency graph
requires:
  - phase: 01-foundation-overview-strategy-lab (plan 04)
    provides: "Strategy Protocol, MACrossoverStrategy, run_strategy_grid/evaluate_strategy,
      app/components/lab_sidebar.py/lab_compute.py/lab_charts.py, Strategy Lab page shell"
provides:
  - "core/grid.py: heatmap_pairs, HeatmapResult, heatmap_grid, grid_window,
    rolling_start_strategy, is_oos_split (LAB-05..08)"
  - "app/components/lab_sidebar.py: split_input (IS/OOS split date widget)"
  - "app/components/lab_compute.py: heatmap_for, rolling_for, is_oos_for (cached, no ttl)"
  - "app/components/lab_charts.py: heatmap_figure, scatter_figure, rolling_figure"
  - "Strategy Lab page: short x long overfitting heatmap, CAGR/MDD scatter across the 24
    notebook rules, rolling-start-year robustness chart, in-sample/out-of-sample split"
  - "scripts/profile_lab_grid.py: the committed D-09 timing measurement"
affects: ["01-06"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "heatmap_grid computes each distinct short/long MA exactly once per call (dict keyed
       by period) and reuses it across every pair that needs it, instead of letting each
       of the ~190 MACrossoverStrategy objects recompute its own MAs independently —
       the fix that turned D-09 profiling from DEBOUNCE NEEDED into REACTIVE OK"
    - "heatmap_grid also skips metrics.summarise()'s full ratio suite (sharpe/sortino/
       calmar/downside_deviation) per cell, computing only the two total_return() calls
       the excess value actually needs — same numeric definition, no extra cost at ~190
       cells"
    - "grid_window factored out of run_strategy_grid as a standalone, reusable window
       calculation (start/end discovery with the warm-up + insufficient-history rule),
       used directly by heatmap_grid and available to any future caller needing the same
       window without re-running a full grid"
    - "rolling_start_strategy generalises rolling_start to any Strategy (not just a bare
       MA pair); rolling_start is now a one-line wrapper, so
       scripts/rerun_notebook_grid.py's output is provably unchanged
       (test_rolling_start_strategy_matches_rolling_start, assert_frame_equal)"
    - "is_oos_split relies on evaluate_strategy's existing end-slicing convention
       (prices.loc[:end] before computing the target) to make the in-sample and
       out-of-sample windows meet exactly at the split date with no shared interval and
       no gap — no new backtest path was needed (RESEARCH Pattern 4)"

key-files:
  created:
    - scripts/profile_lab_grid.py
  modified:
    - core/grid.py
    - core/config.py
    - tests/test_grid.py
    - app/components/lab_sidebar.py
    - app/components/lab_compute.py
    - app/components/lab_charts.py
    - app/views/strategy_lab.py
    - tests/test_app_strategy_lab.py

key-decisions:
  - "D-09 resolved by measurement: the naive heatmap_grid (each pair recomputing its own
     MAs via the generic run_ma_grid path) took 2.70s worst-case cold sum against the
     2.0s threshold (DEBOUNCE NEEDED). Two cheap, numerically-neutral vectorisations —
     computing each distinct MA once per call, and skipping unused ratio metrics for the
     heatmap's excess-only need — brought it to 1.49s (REACTIVE OK). No st.form 'Update
     grid' debounce was added; all Strategy Lab controls stay reactive, per the UI-SPEC
     default."
  - "The heatmap's 'selected rule lies outside the grid shown' caption triggers whenever
     the picker's period is outside SETTINGS.heatmap_short_range/heatmap_long_range —
     relevant in practice only for the long leg, since the picker's long lower bound
     (50, D-05) sits below the heatmap's long lower bound (100, D-06)."
  - "chartDivergingColors stays the UI-SPEC's literal 3-stop array
     (#C0152F/#FFFFFF/#1A7F37): a live headless Streamlit run (Home + Strategy Lab, both
     200) produced no config warning or error mentioning chartDivergingColors, so
     Pitfall 3's 10-stop contingency was not needed."

requirements-completed: [LAB-05, LAB-06, LAB-07, LAB-08]

# Metrics
duration: ~17min active work (4 commits, 02:48-03:05)
completed: 2026-10-08
---

# Phase 1 Plan 05: Strategy Lab Robustness Views Summary

**Short×long overfitting heatmap (red-white-green diverging, selected cell marked), a
24-rule CAGR-vs-drawdown scatter, a full-history rolling-start-year chart, and an
in-sample/out-of-sample split — all measured reactive at 1.49s worst-case recompute
against a 2.0s threshold, after two numerically-neutral vectorisations.**

## Performance

- **Duration:** ~17 min active work (4 atomic commits between 02:48 and 03:05 UTC+1)
- **Started:** 2026-10-08T02:48:36+01:00 (Task 1 RED)
- **Completed:** 2026-10-08T03:05:17+01:00
- **Tasks:** 2
- **Files modified:** 9 (1 created, 8 modified)

## Accomplishments

- `core/grid.py` gained `heatmap_pairs` (independent short/long MA kind + range, short<long
  filtered), `HeatmapResult`/`heatmap_grid` (D-06/D-07's ~192-cell excess-vs-B&H grid),
  `grid_window` (factored out of `run_strategy_grid`, behaviour-neutral), and `is_oos_split`
  (D-12's contiguous, non-overlapping in-sample/out-of-sample split, relying on
  `evaluate_strategy`'s existing end-slicing convention rather than a new backtest path).
- `rolling_start` (the existing Plan 0/04 function) is now a thin wrapper over the new
  `rolling_start_strategy`, which generalises the rolling-start-year robustness check to
  any `Strategy`, not just a bare MA pair — `test_rolling_start_strategy_matches_rolling_start`
  proves the output is byte-for-byte unchanged (`assert_frame_equal`), so
  `scripts/rerun_notebook_grid.py` keeps reproducing identical numbers.
- Fixed a latent crash (Rule 1): `rolling_start(_strategy)` raised `KeyError: "None of
  ['start'] are in the columns"` whenever the available window left no `YS`-frequency
  start date for the requested horizon (an empty `rows` list fed into
  `pd.DataFrame(rows).set_index("start")`). Now builds the frame with an explicit column
  list so an empty result is a valid, empty, correctly-indexed `DataFrame` instead of a
  crash.
- The Strategy Lab page gained four new sections after the metrics card: "Short × long
  grid" (heatmap, with the selected rule's cell marked and the "look for plateaus, not
  spikes" / "not a recommendation" overfitting captions — RESEARCH Pitfall 5), "Risk and
  return across the notebook rules" (scatter, 24 rules + buy-and-hold), "Does the start
  year matter?" (rolling-start chart, always full history 1993→latest regardless of the
  sidebar window — D-11), and "In-sample vs out-of-sample" (a user-adjustable split date,
  defaulting to 2022-12-16, with out-of-sample always running to the latest committed data
  regardless of the sidebar end date — D-12).
- **D-09 settled by measurement, not guesswork.** `scripts/profile_lab_grid.py` cold-times
  (a) the full-history heatmap, (b) the D-01-window heatmap, (c) the 24-rule grid, (d) the
  rolling-start chart, (e) the IS/OOS split, against the real committed 8,480-row snapshot.
  First run: 2.70s worst-case cold sum (a+c+d+e) against the 2.0s threshold — DEBOUNCE
  NEEDED. Per the plan's instructed first move ("try a cheap vectorisation... re-run"),
  two optimisations to `heatmap_grid` (shared per-period MA computation instead of
  per-pair recomputation; skipping `summarise()`'s unused sharpe/sortino/calmar for the
  heatmap's excess-only need) brought the heatmap alone from ~2.2s to ~1.0s and the
  worst-case sum to 1.49s — **REACTIVE OK**. No `st.form` "Update grid" debounce was added;
  every Strategy Lab control, including the new split-date widget, stays reactive.
- `.streamlit/config.toml`'s `chartDivergingColors` (UI-SPEC's literal 3-stop
  `["#C0152F", "#FFFFFF", "#1A7F37"]`) was verified against a live headless Streamlit run
  (Home and Strategy Lab both returned HTTP 200, no config warning/error in the log
  mentioning `chartDivergingColors`) — left unchanged, Pitfall 3's 10-stop contingency
  was not needed.
- Full suite: 124 tests pass (`pytest -q`, up from the 109 baseline); `ruff check .` clean.

### Profiling output (scripts/profile_lab_grid.py, final run)

```
Loaded 8480 rows (1993-01-29 to 2026-10-07)

(a) heatmap_grid, ema/sma, full history 1993 -> latest: 1.021s
(b) heatmap_grid, ema/sma, D-01 default window: 0.963s
(c) run_strategy_grid, 24 notebook rules, full history: 0.254s
(d) rolling_start_strategy, EMA10/SMA200, full history: 0.210s
(e) is_oos_split, EMA10/SMA200, default split: 0.012s

Worst-case cold sum for one sidebar change (a+c+d+e): 1.498s
SETTINGS.grid_debounce_threshold_s: 2.000s
D-09 decision: REACTIVE OK
```

## Task Commits

Each task followed the TDD RED→GREEN cycle, committed atomically:

1. **Task 1 RED: failing tests — heatmap, strategy-aware rolling start, IS/OOS split** - `a77eff5` (test)
2. **Task 1 GREEN: core robustness helpers** - `7c9e488` (feat)
3. **Task 2 RED: failing tests — Lab robustness sections and chart contracts** - `000c925` (test)
4. **Task 2 GREEN: Lab robustness sections, profiling script, D-09 decision** - `a6d6dd9` (feat)

## Files Created/Modified

- `scripts/profile_lab_grid.py` - the committed D-09 timing measurement (new)
- `core/grid.py` - `heatmap_pairs`, `HeatmapResult`, `heatmap_grid` (vectorised),
  `grid_window`, `rolling_start_strategy`, `is_oos_split`; `rolling_start` is now a thin
  wrapper; `run_strategy_grid` uses the factored-out `grid_window`
- `core/config.py` - `split_min_years`, `split_min_oos_months` (split-date widget bounds)
- `app/components/lab_sidebar.py` - `split_input` (IS/OOS split date, bounded, clamped
  default)
- `app/components/lab_compute.py` - `heatmap_for`, `rolling_for`, `is_oos_for` (cached, no
  ttl, matching the module's existing convention)
- `app/components/lab_charts.py` - `heatmap_figure`, `scatter_figure`, `rolling_figure`
- `app/views/strategy_lab.py` - four new sections: short×long grid, risk/return scatter,
  rolling-start-year chart, in-sample/out-of-sample split
- `tests/test_grid.py`, `tests/test_app_strategy_lab.py` - extended per the plan's
  `<behavior>` lists for both tasks

## Decisions Made

- D-09: REACTIVE OK, reached by measurement and two numerically-neutral vectorisations
  (see Accomplishments and the profiling output above). No `st.form` debounce.
- `chartDivergingColors` config.toml array: left as the UI-SPEC's 3-stop array, verified
  live, no 10-stop expansion needed.
- The heatmap's "selected rule lies outside the grid shown" caption is driven by
  `SETTINGS.heatmap_short_range`/`heatmap_long_range` bounds, not by whether the selected
  period lands exactly on a plotted grid line (the marker overlay renders at its exact
  numeric position on continuous axes either way).
- `scatter_figure`'s "selected rule" emphasis is a larger marker size (14 vs 9) within the
  same "Notebook rules" trace, rather than a second overlay trace — simpler, and the
  24+1-point count (`test_scatter_has_25_points`) stays exactly as D-08 specifies.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Latent crash in rolling_start(_strategy) on a narrow available window**
- **Found during:** Task 1, writing the trend-filter-divergence test for
  `rolling_start_strategy` against the `random_prices` fixture (1500 bdays, ~6y)
- **Issue:** With a 5-year rolling horizon and a ~6-year fixture, the warm-up-adjusted
  start-to-(latest minus horizon) window contained zero `YS`-frequency dates, so
  `rolling_start_strategy` built an empty `rows` list and `pd.DataFrame(rows).set_index
  ("start")` raised `KeyError: "None of ['start'] are in the columns"` — a pre-existing
  bug in the Plan 0/04 `rolling_start`, never exercised before because no prior test
  called it against a short-enough fixture.
- **Fix:** Build the `DataFrame` with an explicit column list (`["start", "end",
  "strategy", "buy_and_hold", "excess"]`) so a zero-row result is still a valid, correctly
  -indexed empty frame.
- **Files modified:** `core/grid.py`
- **Verification:** `test_rolling_start_strategy_matches_rolling_start`,
  `test_rolling_start_strategy_with_trend_filter_differs` (rewritten to use a longer,
  locally-generated 3000-bday series so the divergence test has real rows to compare) both
  pass; full suite green.
- **Committed in:** `7c9e488` (Task 1 feat commit)

**2. [Rule 3 - Blocking] D-09 profiling initially failed the threshold; fixed via the
  plan's own "try a cheap vectorisation first" instruction**
- **Found during:** Task 2, first run of `scripts/profile_lab_grid.py`
- **Issue:** The initial `heatmap_grid` (built on the generic `run_ma_grid` →
  `run_strategy_grid` → `grid_window` path, called three times per invocation) measured
  2.70s worst-case cold sum against the 2.0s `grid_debounce_threshold_s` — DEBOUNCE NEEDED.
- **Fix:** Rewrote `heatmap_grid` to compute each distinct short/long MA exactly once
  (dict keyed by period) and to skip `metrics.summarise()`'s unused sharpe/sortino/calmar/
  downside_deviation computations per cell (only `total_return` is needed for
  `excess_total_return`) — same numeric values, measured and re-confirmed against
  `run_ma_grid` row-for-row in `test_heatmap_grid_shape_and_matches_run_ma_grid`.
- **Files modified:** `core/grid.py`
- **Verification:** Re-ran `scripts/profile_lab_grid.py`: worst-case sum dropped to
  1.498s, REACTIVE OK. Full suite + ruff re-confirmed clean.
- **Committed in:** `a6d6dd9` (Task 2 feat commit)

**3. [Rule 1 - Bug] Docstring literally contained the forbidden substring "on_select"**
- **Found during:** Task 2, acceptance-criteria grep check
  (`grep -c "on_select" app/components/lab_charts.py app/views/strategy_lab.py` must print
  0 for each file — RESEARCH Pitfall 2 / no click-to-select on the heatmap)
- **Issue:** `heatmap_figure`'s docstring explained "No on_select — the selected rule is a
  static marker overlay..." which itself contains the literal substring the criterion
  checks is absent, causing a false-positive match against a comment rather than code.
- **Fix:** Reworded to "No click-to-select —..." (same meaning, doesn't repeat the
  substring).
- **Files modified:** `app/components/lab_charts.py`
- **Verification:** `grep -c "on_select"` now prints 0 for both files; full suite + ruff
  re-confirmed clean.
- **Committed in:** `a6d6dd9` (part of Task 2's commit — fixed before committing)

---

**Total deviations:** 3 auto-fixed (1 pre-existing bug surfaced by new tests, 1 blocking
performance fix per the plan's own instructed fallback sequence, 1 acceptance-criteria
false-positive from a docstring). **Impact on plan:** None material — no architecture,
contract, or numeric change to any reported metric; the D-09 fix is exactly the
vectorisation path the plan itself specified as the first thing to try.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- LAB-05..08 are fully implemented and tested; the Strategy Lab (LAB-01..10) is now
  feature-complete for Phase 1's scope. Plan 06 (per the roadmap) covers final
  human-verification checkpoints (the heatmap's visual diverging scale and marked cell at
  defaults — flagged in the plan's `<verification>` section as a `<human-check>` item for
  Plan 06 to collect) plus any remaining Overview-page or cross-page polish.
- No blockers.

---
*Phase: 01-foundation-overview-strategy-lab*
*Completed: 2026-10-08*

## Self-Check: PASSED

All 9 claimed files found on disk; all 4 claimed commit hashes found in git log.
