---
phase: 01-foundation-overview-strategy-lab
plan: 03
subsystem: ui
tags: [streamlit, plotly, pandas, drawdowns, app-test]

# Dependency graph
requires:
  - phase: 01-foundation-overview-strategy-lab (plan 01)
    provides: "core/storage.py, app/components/store.py (DATA-05 cached read layer), app/components/sidebar.py, app/components/theme.py, app/views/overview.py skeleton"
provides:
  - "core/regimes.py: drawdown_series, regime_spans, drawdown_table, overview_kpis (pure, tested)"
  - "MASpec.from_label classmethod on core/indicators.py (parses 'sma50'/'ema200' style labels)"
  - "app/components/price_charts.py: price_figure(window, chart_type, overlays, regimes) -> go.Figure"
  - "Complete app/views/overview.py: chart-type switch, MA overlays, drawdown regime shading, 4-metric KPI strip, largest-drawdowns table"
affects: [01-04, 01-05, 01-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "core/regimes.py follows core/metrics.py style: float casts, NaN guards via pandas ops, no try/except, TRADING_DAYS import from core.metrics (no duplicate constant)"
    - "price_figure is a pure go.Figure builder: takes already-sliced window/overlays/regimes, no Streamlit caching or import inside app/components/price_charts.py"
    - "Overlay traces cycle through theme's categorical color order (BH_GRAY, GAIN_GREEN, LOSS_RED, STRATEGY_BLUE) rather than reusing the close trace's STRATEGY_BLUE first"
    - "Drawdown regime vrects are added shallowest-threshold-first so the deepest band composites on top (darkest), matching the UI-SPEC's 'one hue, nested' requirement"
    - "st.sidebar.pills (selection_mode='multi') used for drawdown regimes with an st.sidebar.multiselect fallback via hasattr(st.sidebar, 'pills') for older Streamlit"

key-files:
  created:
    - core/regimes.py
    - app/components/price_charts.py
    - tests/test_regimes.py
  modified:
    - core/indicators.py
    - app/views/overview.py
    - tests/test_app_overview.py

key-decisions:
  - "Drawdown table's 'recovery' column uses st.column_config.Column (plain), not DateColumn, because the UI-SPEC's literal 'NaT displays as Not recovered' requirement needs a string substitution for unrecovered rows; Peak and Trough stay DateColumn since they are always valid dates"
  - "regime_spans built as a plain Python loop over the drawdown boolean mask (not a vectorised pandas groupby) — simplest correct implementation for this scale (thousands of rows, called a handful of times per render) and easiest to verify against the hand-computed behaviour spec"

requirements-completed: [OVER-01, OVER-02, OVER-03, OVER-04, OVER-05, OVER-06]

# Metrics
duration: 8min
completed: 2026-10-08
---

# Phase 1 Plan 03: Overview Depth Summary

**Overview page gains a candlestick/line switch, full-history MA overlays with no warm-up gap, nested drawdown-regime shading, a 4-metric KPI strip and a largest-drawdowns table — all backed by a new pure `core/regimes.py`.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-10-08T00:58:00+01:00
- **Completed:** 2026-10-08T01:06:00+01:00
- **Tasks:** 2
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments

- `core/regimes.py` gives every Overview number a pure, tested function:
  `drawdown_series`, `regime_spans`, `drawdown_table` (episode walk sorted by depth,
  `days_underwater` as a bar count, `recovery` NaT when unrecovered), and `overview_kpis`
  (YTD return with the prior-calendar-year-close baseline and first-bar-of-year fallback,
  current drawdown, distance from all-time high, 20-day realised vol annualised with
  `sqrt(TRADING_DAYS)`).
- `MASpec.from_label` on `core/indicators.py` parses `"sma50"`/`"ema200"`-style config labels
  back into `MASpec` instances, raising `ValueError` on anything else — this is what keeps the
  Overview sidebar's MA multiselect to the fixed `SETTINGS.overview_ma_options` tuple (T-01-12).
- `app/components/price_charts.py`'s `price_figure` builds the whole chart: `go.Scattergl` over
  `SETTINGS.scattergl_threshold_bars`, `go.Candlestick` with the range slider off otherwise,
  MA overlay traces cycling the theme's categorical colors, and nested `add_vrect` drawdown
  bands drawn shallowest-first so the deepest band composites darkest.
- `app/views/overview.py` is now the full OVER-01..06 page: a "Chart type" radio, a "Moving
  averages" multiselect (SMA50+SMA200 on by default), a "Drawdown regimes" pills control
  (−10%/−20% on by default, multiselect fallback for older Streamlit), the 4-metric KPI strip
  in bordered `st.container`s, a candlestick-range warning caption past
  `SETTINGS.candlestick_warn_bars`, and a "Largest drawdowns" table with `"Not recovered"`
  text for unrecovered episodes — every number computed from `core/regimes.py` on the chosen
  price basis.
- Full suite: 49 tests pass (`pytest -q`, up from 31 after Plan 01); `ruff check .` is clean.
  New `tests/test_regimes.py` (13 hand-computed test functions) and five new/extended
  `tests/test_app_overview.py` AppTest cases cover the KPI strip, candlestick switch,
  drawdown table, all-regimes-and-MAs selection, and a direct `price_figure` unit test
  proving the SMA 200 overlay has no warm-up gap at the window start.

## Task Commits

Each task was committed atomically:

1. **Task 1: core/regimes.py — drawdowns, regime spans, drawdown table, KPIs (TDD)**
   - `957876c` (test) — failing `tests/test_regimes.py`, confirmed RED (`ModuleNotFoundError: core.regimes`)
   - `b4f1075` (feat) — `core/regimes.py` + `MASpec.from_label`, confirmed GREEN
2. **Task 2: Full Overview page — chart type, MA overlays, regime shading, KPI strip, drawdown table**
   - `7d82b17` (feat) — `app/components/price_charts.py`, full `app/views/overview.py`, extended `tests/test_app_overview.py`

## Files Created/Modified

- `core/regimes.py` - `drawdown_series`, `regime_spans`, `drawdown_table`, `overview_kpis` (pure, no Streamlit import)
- `core/indicators.py` - added `MASpec.from_label` classmethod
- `app/components/price_charts.py` - `price_figure(window, chart_type, overlays, regimes) -> go.Figure`
- `app/views/overview.py` - sidebar chart-type/MA/regime controls, KPI strip, chart, largest-drawdowns table
- `tests/test_regimes.py` - 13 hand-computed test functions for `core/regimes.py` and `MASpec.from_label`
- `tests/test_app_overview.py` - extended with KPI strip, candlestick switch, drawdown table, all-regimes-and-mas, and a direct `price_figure` no-warmup-gap unit test

## Decisions Made

- `drawdown_table`'s `recovery` column is rendered through `st.column_config.Column` (plain),
  not `DateColumn`, specifically so a NaT can be replaced with the literal string
  `"Not recovered"` per the UI-SPEC copy contract — a `DateColumn` would either reject the
  string or silently blank the cell. `Peak`/`Trough` stay `DateColumn` since those are always
  valid dates.
- MA overlay trace colors cycle `(BH_GRAY, GAIN_GREEN, LOSS_RED, STRATEGY_BLUE)` — the same
  order as `.streamlit/config.toml`'s `chartCategoricalColors` rotated to start after
  `STRATEGY_BLUE`, since the close/SPY trace itself already uses that color and a first
  overlay in the same blue would be visually ambiguous.
- Drawdown regime `vrect`s are added in ascending `abs(threshold)` order (shallowest −5%
  first, deepest −20% last) so nested bands composite with the deepest reading darkest,
  matching the UI-SPEC's "one hue, never three" requirement without needing three unrelated
  colors.

## Deviations from Plan

None — plan executed as written. The `recovery` column's `Column` (vs `DateColumn`) choice
above is a Claude's-discretion implementation detail within OVER-05's stated copy contract
("Recovery ... as DateColumn; a NaT recovery displays as 'Not recovered'"), not a deviation
from a `must_haves` or `threat_model` requirement.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `core/regimes.py` and `app/components/price_charts.py` are now reusable building blocks:
  the Strategy Lab plans (01-02/01-04/01-05, built in parallel in this same wave structure)
  do not depend on this plan's files, but later phases needing drawdown/KPI logic on any
  price series can call `core/regimes.py` directly.
- OVER-01..06 are fully implemented and covered by both unit tests (`core/regimes.py`) and
  `AppTest` end-to-end cases. The plan's own `<verification>` end-of-phase `<human-check>`
  (collected by Plan 06) is the only remaining open item for this plan's scope — a visual
  check that the default view (5 years, line, SMA50/200, −10/−20% bands, KPI strip,
  drawdown table) reads correctly in a running browser.
- No blockers.

---
*Phase: 01-foundation-overview-strategy-lab*
*Completed: 2026-10-08*

## Self-Check: PASSED

All 3 claimed created files found on disk (`core/regimes.py`, `app/components/price_charts.py`,
`tests/test_regimes.py`); all 3 claimed commit hashes (`957876c`, `b4f1075`, `7d82b17`) found
in `git log`. Full suite (49 tests) and `ruff check .` both green.
