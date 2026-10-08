---
phase: 01-foundation-overview-strategy-lab
reviewed: 2026-10-08T00:00:00Z
depth: standard
files_reviewed: 40
files_reviewed_list:
  - .github/workflows/ci.yml
  - .github/workflows/nightly.yml
  - .streamlit/config.toml
  - app/Home.py
  - app/components/lab_charts.py
  - app/components/lab_compute.py
  - app/components/lab_sidebar.py
  - app/components/price_charts.py
  - app/components/sidebar.py
  - app/components/store.py
  - app/components/theme.py
  - app/views/overview.py
  - app/views/strategy_lab.py
  - core/config.py
  - core/data.py
  - core/grid.py
  - core/indicators.py
  - core/market_calendar.py
  - core/metrics.py
  - core/regimes.py
  - core/signals.py
  - core/storage.py
  - core/validate.py
  - jobs/refresh_prices.py
  - pyproject.toml
  - requirements.txt
  - scripts/profile_lab_grid.py
  - scripts/rerun_notebook_grid.py
  - tests/test_app_overview.py
  - tests/test_app_purity.py
  - tests/test_app_strategy_lab.py
  - tests/test_grid.py
  - tests/test_market_calendar.py
  - tests/test_metrics.py
  - tests/test_phase0_regression.py
  - tests/test_refresh_prices.py
  - tests/test_regimes.py
  - tests/test_signals.py
  - tests/test_storage.py
  - tests/test_validate_snapshot.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-10-08
**Depth:** standard
**Files Reviewed:** 40
**Status:** issues_found

## Summary

Reviewed the Phase 1 foundation (Overview page, Strategy Lab, the `core/` backtest-adjacent
modules, the nightly data-refresh job/validation gate, and the CI/nightly workflows) with a
priority on look-ahead/off-by-one correctness, `core/` purity, network isolation of the app,
nightly-workflow safety, and the D-13 validation gate.

The honesty-critical paths hold up under direct tracing: `core/signals.py`'s crossover/trend-filter
targets are strictly causal (confirmed by `test_no_look_ahead` and by manual trace — MAs are
backward-looking rolling/ewm windows, unaffected by slicing to a smaller end date); the
`grid_window` / `evaluate_strategy` / `heatmap_grid` / `is_oos_split` warm-up math consistently
starts the common window one bar after the slowest signal's first valid value, matching
`core/backtest.py`'s shift-by-one exposure convention; `core/` has zero Streamlit/network imports
(verified by grep and by the `test_app_purity.py`/`test_core_has_no_streamlit_import` tests); the
app never imports `yfinance`/`requests`/`core.data` (verified by grep); and the nightly workflow's
permissions, concurrency group, and commit scope (`data/prices.parquet data/meta.json` only, never
`git add -A`) are correctly minimal. `ruff check .` and the full `pytest` suite (124 tests) both
pass.

One genuine, reproducible crash bug was found in the Strategy Lab's rolling-start chart path (see
CR-01) — it is not reachable through the live app today given the committed 1993+ snapshot and the
current `SETTINGS.rolling_horizon_years = 5`, but it is a real unhandled exception that breaks the
pattern every sibling function in `core/grid.py` otherwise follows (raise a descriptive
`ValueError`, caught by the view). Three further warnings and two dead-code items round out the
rest.

## Critical Issues

### CR-01: `rolling_start_strategy`/`rolling_figure` crash instead of raising a descriptive error when no rolling-start date exists

**File:** `core/grid.py:195-209`, `app/components/lab_charts.py:100-108`

**Issue:** Every other grid function in `core/grid.py` (`grid_window`, `evaluate_strategy`,
`heatmap_grid`, `is_oos_split`) explicitly raises `ValueError(_INSUFFICIENT_HISTORY)` when the
strategy's warm-up leaves no usable window, which `app/views/strategy_lab.py` catches and turns
into the `_INSUFFICIENT_HISTORY_WARNING` message. `rolling_start_strategy` does not: it builds
`pd.date_range(first, last, freq=freq)` where `last = prices.index[-1] - DateOffset(years=horizon_years)`.
When `first` (the strategy's warm-up date) falls within `horizon_years` of the end of the data,
`first > last` and `pd.date_range` silently returns an **empty** `DatetimeIndex` — no exception,
no rows. The resulting empty `DataFrame` is then passed to `rolling_figure`, which does
`df.index.year` on what is now a plain `RangeIndex` (since `.set_index("start")` on an empty frame
with no rows doesn't coerce back to `DatetimeIndex`), raising:

```
AttributeError: 'RangeIndex' object has no attribute 'year'
```

Reproduced directly:
```python
rolling_start_strategy(df, strategy, horizon_years=5)  # -> empty DataFrame, no error
rolling_figure(empty_df)  # -> AttributeError: 'RangeIndex' object has no attribute 'year'
```

This bypasses `strategy_lab.py`'s `except ValueError` guard entirely (an `AttributeError` is not
caught), so the page would hard-crash instead of showing the insufficient-history warning. It is
not reachable today through the UI with the committed 30-year snapshot and the fixed
`rolling_horizon_years=5` (warm-up never exceeds ~250 bars), but it's a real, demonstrated
unhandled-exception path that will break the moment `rolling_horizon_years` is raised, a shorter
instrument/history is ever used, or the committed snapshot is truncated — and it silently
diverges from the error-handling convention every other function in this module follows.

Also note `first` can itself be `None` (strategy has no valid target at all over the full
series) — in that case `pd.date_range(None, last, freq=freq)` raises a *different*,
confusingly-worded `ValueError` ("Of the four parameters: start, end, periods, and freq, exactly
three must be specified") that happens to still be a `ValueError` (so it's caught), but for the
wrong reason and with a message that doesn't match `_INSUFFICIENT_HISTORY`.

**Fix:**
```python
def rolling_start_strategy(prices: pd.DataFrame, strategy: Strategy, horizon_years: int = 5,
                           freq: str = "YS", cost_bps: float = 0.0) -> pd.DataFrame:
    target = strategy.target(prices)
    first = target.first_valid_index()
    if first is None:
        raise ValueError(_INSUFFICIENT_HISTORY)
    last = prices.index[-1] - pd.DateOffset(years=horizon_years)
    starts = pd.date_range(first, last, freq=freq)
    if len(starts) == 0:
        raise ValueError(_INSUFFICIENT_HISTORY)
    rows = []
    for s in starts:
        ...
```

## Warnings

### WR-01: Warm-up/common-start logic duplicated four times in `core/grid.py`

**File:** `core/grid.py:45-57` (`grid_window`), `93-104` (`evaluate_strategy`), `163-174`
(`heatmap_grid`), `232-243` (`is_oos_split`)

**Issue:** The exact same five-statement pattern — `pos = prices.index.get_loc(first_valid) + 1`,
bounds-check `pos >= len(prices.index)`, `common_start = prices.index[pos]`, optionally
`max(common_start, pd.Timestamp(start))`, bounds-check `common_start > prices.index[-1]` — is
copy-pasted across four functions instead of being factored into one helper (`grid_window`
itself, or a small private function, could serve all four call sites). The current test suite
happens to catch divergence (e.g. `test_heatmap_grid_shape_and_matches_run_ma_grid` cross-checks
`hm.start == expected_start` from `grid_window`), but any future edit to the warm-up rule (e.g. an
off-by-one fix) requires finding and changing all four copies correctly, and a future edit to only
one of them would silently break the "every page uses the same no-look-ahead convention" guarantee
this project is built on.

**Fix:** Extract the shared block into one function, e.g. `_warmup_start(prices, first_valid,
start=None) -> pd.Timestamp`, raising `_INSUFFICIENT_HISTORY` internally, and call it from all
four sites (including `heatmap_grid`'s `last_first_valid`/`is_oos_split`'s `effective_start`
computation).

### WR-02: `adj_close`/`high`/`low`/`volume` NaNs are not validated, and can silently corrupt the total-return basis

**File:** `core/data.py:19-28` (`_finalise`), `core/validate.py:37-39` (adj_close ratio check)

**Issue:** `_finalise` only drops rows with `NaN` in `open`/`close`
(`df.dropna(subset=["open", "close"])`); a row with a `NaN` `adj_close` (or `high`/`low`) passes
through untouched. `to_total_return()` (`core/data.py:49-58`) then computes
`factor = df["adj_close"] / df["close"]` and scales `open/high/low/close` by it — a `NaN`
`adj_close` for one day produces `NaN` prices for that day on the `total_return` basis, which
`run_backtest`'s `.dropna()` will then silently drop from every rule's interval return series,
producing a one-day hole in every strategy and the benchmark for that date. `validate_snapshot`'s
adj_close-consistency check (`core/validate.py:37`) makes this worse by calling `.dropna()` on the
ratio series *before* comparing max/min — so a newly-introduced `NaN` adj_close row is quietly
excluded from the check rather than flagged, and the D-13 gate will pass a snapshot containing it.
This is a narrow, yfinance-data-quality-dependent edge case (not currently observed in the
committed snapshot), but the project's stated bar is "every number on the page is honest and
traceable" — a silently-dropped trading day in a reported backtest is exactly the kind of failure
this gate exists to catch.

**Fix:** In `_finalise`, extend the `dropna(subset=...)` to all price columns used downstream
(`open, high, low, close, adj_close`), or raise if any remain after the drop; in
`validate_snapshot`, treat a new `NaN` in `adj_close`/`close`/`open` for a date present in `old`
as a rewrite-tolerance violation rather than silently dropping it from the ratio check.

### WR-03: `--retry-wait-max` CLI flag can silently produce a longer wait than requested

**File:** `jobs/refresh_prices.py:70-71`

**Issue:**
```python
wait_max = args.retry_wait_max
wait_min = 0.0 if wait_max <= 0 else SETTINGS.fetch_wait_min_s
```
`wait_min` is never clamped to `wait_max`. The module's own docstring advertises
`python -m jobs.refresh_prices --retry-wait-max 5` as supported usage; for any
`0 < --retry-wait-max < SETTINGS.fetch_wait_min_s` (currently `2.0`), this passes
`wait_exponential(multiplier=1, min=2.0, max=<user value>)` to tenacity. Confirmed directly:
`wait_exponential(min=2.0, max=1.0)` on the first attempt returns `2.0`, i.e. tenacity honors
`min` over a conflicting `max` rather than raising — so a user who asks for a 1-second cap gets a
2-second wait instead, with no warning. Low real-world impact (the nightly workflow never passes
this flag; the only non-zero use is the docstring's own `5` example, which is unaffected), but it
is a genuine logic gap in a documented, user-facing flag.

**Fix:**
```python
wait_min = 0.0 if wait_max <= 0 else min(SETTINGS.fetch_wait_min_s, wait_max)
```

## Info

### IN-01: `core/signals.py::crossings` is unused outside its own test

**File:** `core/signals.py:40-43`

**Issue:** `crossings()` is exercised only by `tests/test_signals.py::test_crossover_target_and_crossings`;
no view, job, or script calls it. Either it's groundwork for a not-yet-built feature (e.g. marking
buy/sell decision dates distinctly from fill dates on a future chart) or it's dead code.

**Fix:** If it's intentional groundwork, add a one-line comment saying so (consistent with this
codebase's practice of noting forward-looking design, e.g. `detector_version: int = 0  # Phase 2
bumps this` in `core/config.py`); otherwise remove it.

### IN-02: `core/indicators.py::add_mas` is unused anywhere in the codebase

**File:** `core/indicators.py:44-48`

**Issue:** `add_mas()` has no callers in `app/`, `core/`, `jobs/`, `scripts/`, or `tests/` — the
Overview page builds its MA overlays directly via `MASpec.from_label(label).compute(full_close)`
(`app/views/overview.py:94`) rather than this helper. Dead code.

**Fix:** Remove, or wire it in if it was meant to replace the dict-comprehension in
`overview.py:94`.

---

_Reviewed: 2026-10-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
