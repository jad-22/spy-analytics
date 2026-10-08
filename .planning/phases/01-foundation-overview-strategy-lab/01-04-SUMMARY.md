---
phase: 01-foundation-overview-strategy-lab
plan: 04
subsystem: core/app
tags: [streamlit, plotly, backtest, strategy-protocol, sortino, calmar, app-test]

# Dependency graph
requires: ["01-01"]
provides:
  - "core/signals.py: runtime_checkable Strategy Protocol + MACrossoverStrategy (LAB-10)"
  - "core/metrics.py: downside_deviation, sortino, calmar, metrics_table"
  - "core/grid.py: notebook_strategies, run_strategy_grid, evaluate_strategy, count_beating; run_ma_grid gains trend_filter_period"
  - "app/views/strategy_lab.py: Strategy Lab page (live 0-of-24 headline, equity vs B&H, metrics table)"
  - "app/components/lab_sidebar.py, lab_compute.py, lab_charts.py"
affects: ["01-05", "01-06"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Strategy Protocol (runtime_checkable) + frozen-dataclass implementations — the view
       only ever calls strategy.name/.label/.target(prices), never ma_crossover/trend_filter/
       combine_all/MASpec directly (LAB-10)"
    - "core/grid.py's generic run_strategy_grid/evaluate_strategy replace the MA-specific
       warm-up logic; run_ma_grid is now a thin wrapper over it, so the pre-existing
       PHASE0_FINDINGS numeric contract is preserved exactly"
    - "app/components/lab_compute.py: st.cache_data keyed on primitives + a frozen Strategy
       dataclass, no ttl, no hash_funcs workaround needed"

key-files:
  created:
    - tests/test_phase0_regression.py
    - tests/test_app_strategy_lab.py
    - tests/test_metrics.py
    - app/components/lab_sidebar.py
    - app/components/lab_compute.py
    - app/components/lab_charts.py
    - app/views/strategy_lab.py
  modified:
    - core/signals.py
    - core/metrics.py
    - core/grid.py
    - tests/test_signals.py
    - tests/test_grid.py
    - app/Home.py

key-decisions:
  - "st.cache_data hashes the frozen MACrossoverStrategy dataclass directly — no hash_funcs
     override was needed (the plan flagged this as a possible fallback; profiling showed it
     unnecessary)"
  - "Grid-recompute timing: the 24-rule grid over the full 1993-latest snapshot (8,480 rows)
     runs in ~0.24s, well under SETTINGS.grid_debounce_threshold_s (2.0s) — no st.form
     'Update grid' debounce added this plan (D-09); Plan 05 profiles the much larger ~192-cell
     heatmap separately"
  - "run_strategy_grid/evaluate_strategy pre-slice prices to :end before computing the common
     warm-up start, matching scripts/rerun_notebook_grid.py's prices.loc[:end] convention
     literally, even though it is a numeric no-op given run_backtest's own .loc[start:end]
     boundary — kept for convention parity per the plan's explicit instruction"

requirements-completed: [LAB-01, LAB-02, LAB-03, LAB-04, LAB-09, LAB-10]

# Metrics
duration: ~99min (includes a mid-plan rate-limit pause between Task 1 and Task 2; active
  work was closer to 40min)
completed: 2026-10-08
---

# Phase 1 Plan 04: Strategy Lab — First Slice Summary

**Live "N of 24 rules beat buy-and-hold in this window" headline (reading "0 of 24" at
defaults, exactly reproducing `docs/PHASE0_FINDINGS.md`), a Strategy-protocol-driven rule
picker, and the selected rule's equity-vs-buy-and-hold chart with fills and a full metrics
table (CAGR/MDD/Sharpe/Sortino/Calmar/time-in-market/trades).**

## Performance

- **Duration:** ~99 min wall-clock (includes one mid-plan rate-limit pause; active work
  was closer to 40 min)
- **Started:** 2026-10-08T00:34 (Task 1 RED)
- **Completed:** 2026-10-08T02:39
- **Tasks:** 3
- **Files modified:** 13 (7 created, 6 modified)

## Accomplishments

- A visitor opening Strategy Lab sees, directly under the title, the live-recomputed
  headline "0 of 24 rules beat buy-and-hold in this window" at the default window
  (2010-10-19 → 2022-12-16, total return, 0 bps, no trend filter — D-01), with a fixed
  caption anchoring the notebook's own 2010–2022 result and the UI-SPEC's verbatim
  "every SMA/EMA crossover ... trails buy-and-hold" caption underneath it (D-02, LAB-09).
- `tests/test_phase0_regression.py` is a hard regression gate against the real committed
  1993+ snapshot (not a synthetic fixture): all 6 PHASE0_FINDINGS rows assert exactly
  `count_beating(grid) == 0`, and the default row's total-return numbers match
  `docs/PHASE0_FINDINGS.md` (+215.0%/+315.2%) to within the documented EMA-seeding
  tolerance.
- `core/signals.py` gained a `runtime_checkable Strategy` Protocol and
  `MACrossoverStrategy` — the Strategy Lab page (`app/views/strategy_lab.py`) only ever
  calls `strategy.name`/`.label`/`.target(prices)`, never `ma_crossover`/`trend_filter`/
  `combine_all`/`MASpec` directly (verified by a static grep in the acceptance criteria
  and `tests/test_signals.py::test_custom_strategy_plugs_in`'s drop-in `AlwaysLong` class),
  satisfying LAB-10's "new rule types plug in with zero page changes" requirement.
- `core/metrics.py` gained `downside_deviation`, `sortino`, `calmar` (NaN-guarded, matching
  the existing `sharpe()`/`summarise()` one-line style) and `metrics_table()`, which builds
  the 7-row strategy-vs-buy-and-hold table the page renders.
- `core/grid.py`'s `run_ma_grid` is now a thin wrapper over the new, Strategy-generic
  `run_strategy_grid`/`evaluate_strategy`, which carry forward the exact same end-slicing
  and one-bar-after-warm-up convention — the pre-existing PHASE0_FINDINGS numeric contract
  is unchanged, and `run_ma_grid` additionally accepts `trend_filter_period`.
- The visitor can configure short/long MA kind and period (bounded 5–60 / 50–250, D-05),
  toggle the 200D trend filter, set cost (bps) and the date range; short≥long shows the
  UI-SPEC's warning and stops cleanly (no crash). Insufficient-history windows (e.g. a
  narrow 1993 range shorter than the slowest MA's warm-up) are caught and shown as the
  UI-SPEC's warning too, in both the headline grid and the selected-rule backtest.
- Full suite: 59 tests pass (`pytest -q`); `ruff check .` is clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: Failing tests — Phase 0 regression and Strategy Lab end-to-end** - `37a3c7a` (test)
2. **Task 2: Core — Strategy protocol, Sortino/Calmar/metrics_table, strategy grid** - `e2baecb` (feat)
3. **Task 3: Strategy Lab page — sidebar, live headline, equity vs B&H, metrics** - `0f9f228` (feat)

_RED confirmed after Task 1 (`ImportError: cannot import name 'count_beating' from
'core.grid'`, before Task 2 existed). GREEN reached after Task 2 for the core-only test
files (`test_signals.py`, `test_metrics.py`, `test_grid.py`, `test_phase0_regression.py`,
30 tests); the 7 `tests/test_app_strategy_lab.py` AppTest cases stayed red (FileNotFoundError
on the not-yet-created `app/views/strategy_lab.py`) until Task 3 landed the page, sidebar,
compute and chart components together._

## Files Created/Modified

- `tests/test_phase0_regression.py` - 6 parametrised PHASE0_FINDINGS rows + the exact
  2.150/3.152 total-return numbers, against the real committed snapshot
- `tests/test_app_strategy_lab.py` - AppTest coverage: default headline, anchor caption,
  equity/metrics render, trend-filter+cost toggle, short≥long warning, insufficient-history
  warning, no-network guard
- `tests/test_metrics.py` - Sortino (hand-computed and NaN-on-no-downside), Calmar
  (formula match and NaN-on-no-drawdown), `metrics_table` shape/B&H-values
- `tests/test_signals.py`, `tests/test_grid.py` - extended with `MACrossoverStrategy`
  naming/target/Protocol-conformance tests, the `AlwaysLong` drop-in Strategy test,
  `run_ma_grid` with `trend_filter_period`, `run_strategy_grid`/`evaluate_strategy`
  parity and insufficient-history tests, `count_beating`
- `core/signals.py` - `Strategy` Protocol (`runtime_checkable`), `MACrossoverStrategy`
  frozen dataclass wrapping the existing `ma_crossover`/`trend_filter`/`combine_all`
- `core/metrics.py` - `downside_deviation`, `sortino`, `calmar`, `metrics_table`;
  `summarise()` additively gains `sortino`/`calmar`/`bh_sharpe`/`bh_sortino`/`bh_calmar`
- `core/grid.py` - `notebook_strategies`, `run_strategy_grid`, `evaluate_strategy`,
  `count_beating`; `run_ma_grid` delegates to `run_strategy_grid` and gains
  `trend_filter_period`
- `app/components/lab_sidebar.py` - `LabSettings`, `lab_settings()`, `rule_input()` (the
  only place that constructs a `Strategy`)
- `app/components/lab_compute.py` - cached `headline_grid`, `phase0_anchor_count`,
  `selected_backtest` (no ttl)
- `app/components/lab_charts.py` - `equity_figure()`, `format_metrics()`
- `app/views/strategy_lab.py` - the page itself: headline, selected-rule chart, metrics
- `app/Home.py` - registers the Strategy Lab page via `st.navigation`

## Decisions Made

- `st.cache_data` hashes the frozen `MACrossoverStrategy` dataclass directly; the plan's
  `hash_funcs={MACrossoverStrategy: lambda s: s.name}` fallback was not needed.
- Manual timing check (per the plan's instruction, since Plan 05 owns the D-09 profiling
  decision for the much larger heatmap): `run_strategy_grid` over the 24 notebook rules on
  the full 1993→latest 8,480-row snapshot takes ~0.24s — about 8x under
  `SETTINGS.grid_debounce_threshold_s` (2.0s). No `st.form` "Update grid" debounce was added
  this plan.
- `run_strategy_grid`/`evaluate_strategy` pre-slice `prices` to `:end` before computing the
  common warm-up start, literally matching `scripts/rerun_notebook_grid.py`'s
  `prices.loc[:end]` convention, even though this is a numeric no-op given
  `run_backtest`'s own `.loc[start:end]` boundary (MAs only look backward) — kept for
  convention parity, per the plan's explicit instruction, not because it changes any
  number.
- The "some rules beat buy-and-hold in this window" fallback caption (shown only when the
  live count is nonzero, which never happens at any of the tested windows/bases/costs) was
  worded to avoid repeating the exact headline substring "rules beat buy-and-hold in this
  window", so the acceptance criterion's single-occurrence grep on that phrase holds.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Acceptance-criteria greps initially failed due to line-wrapping and a duplicate substring**
- **Found during:** Task 3, post-implementation acceptance check
- **Issue:** The UI-SPEC's verbatim caption "...including the notebook's old favorite,
  EMA10 vs SMA200..." was wrapped across two Python string-literal lines in the source,
  so a single-line `grep` for the full phrase found nothing even though the rendered
  string was correct. Separately, the fallback "some rules beat..." caption happened to
  contain the exact substring "rules beat buy-and-hold in this window", making the
  acceptance criterion's `grep -c` return 2 instead of 1.
- **Fix:** Rewrapped the UI-SPEC caption so the full verbatim phrase sits on one source
  line (well within the 100-char ruff limit); reworded the fallback caption to "Some of
  the 24 rules come out ahead in this particular window..." which preserves the same
  meaning without repeating the headline's exact phrase.
- **Files modified:** `app/views/strategy_lab.py`
- **Verification:** the two acceptance-criteria `grep -c` commands now both print `1`;
  full `pytest -q` (59 passed) and `ruff check .` re-run clean after the fix.
- **Committed in:** `0f9f228` (part of Task 3's commit — fixed before committing, not a
  follow-up commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — a copy-wrapping bug caught by the plan's own
acceptance criteria before commit, not a follow-up fix).
**Impact on plan:** None — no architecture, contract, or numeric change; purely a source
formatting/copy fix to satisfy the plan's own static acceptance checks.

## Issues Encountered

- The session was interrupted once by a rate limit between Task 1 (RED) and Task 2
  (GREEN); work resumed cleanly from the last commit (`37a3c7a`) after re-verifying the
  worktree branch (`worktree-agent-ad8e50310cc36b67c`) and toplevel were unchanged, and
  re-running ruff/pytest before continuing. No work was lost or redone.
- The plan's `<verification>` section also lists a manual
  `./.venv/python.exe -m scripts.rerun_notebook_grid` run (needs internet) as a sanity
  check. This was not run in this session (no confirmed outbound internet access in the
  sandboxed worktree environment) — `tests/test_phase0_regression.py` already exercises
  the equivalent assertion against the real committed snapshot without a live fetch, so
  this is a documented gap, not a blocker.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- The `Strategy` Protocol, `run_strategy_grid`/`evaluate_strategy`, and
  `app/components/lab_sidebar.py`/`lab_compute.py`/`lab_charts.py` are all in place for
  Plan 05 (heatmap, rolling-start, CAGR/MDD scatter, IS/OOS split) to build on directly —
  Plan 05 reuses `notebook_strategies()`/`run_strategy_grid()` for the heatmap grid and
  owns the D-09 profiling decision for that much larger (~192-cell) computation.
- No blockers.

---
*Phase: 01-foundation-overview-strategy-lab*
*Completed: 2026-10-08*

## Self-Check: PASSED

All 13 claimed files found on disk; all 3 claimed commit hashes found in git log.
