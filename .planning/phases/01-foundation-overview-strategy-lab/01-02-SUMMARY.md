---
phase: 01-foundation-overview-strategy-lab
plan: 02
subsystem: data
tags: [pandas, github-actions, ci-cd, data-validation]

# Dependency graph
requires:
  - phase: 01-foundation-overview-strategy-lab
    provides: "Plan 01: core/storage.py, core/config.py Settings (tolerances, session_complete_after_et), jobs/refresh_prices.py with the _write_snapshot() single call site, the real 1993-01-29+ data/prices.parquet snapshot"
provides:
  - "core/market_calendar.py: NYSEHolidayCalendar + nyse_holidays()/nyse_sessions(), verified against 33 years of real SPY sessions"
  - "core/validate.py: validate_snapshot() (D-13 gate) and drop_incomplete_session() (partial-bar guard)"
  - "jobs/refresh_prices.py: validate_snapshot gate wired before _write_snapshot; rejects bad snapshots with exit 1, no write"
  - ".github/workflows/nightly.yml: weekdays 21:30 UTC + workflow_dispatch, contents:write, default GITHUB_TOKEN"
  - ".github/workflows/ci.yml: paths-ignore data/** loop guard"
affects: [01-03, 01-04, 01-05, 01-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "NYSE session calendar built from pandas.tseries.holiday rules, not a new dependency (pandas_market_calendars rejected per plan's own open-question decision)"
    - "validate_snapshot(new, old, cfg) raises ValueError per D-13 branch in a fixed order: row count, last date, OHLCV rewrite tolerance, adj_close common-factor, missing session gap"
    - "Nightly workflow hand-rolls git add/commit/push with the default GITHUB_TOKEN instead of a third-party commit action (RESEARCH's explicit recommendation)"

key-files:
  created:
    - core/market_calendar.py
    - core/validate.py
    - tests/test_market_calendar.py
    - tests/test_validate_snapshot.py
    - .github/workflows/nightly.yml
  modified:
    - jobs/refresh_prices.py
    - tests/test_refresh_prices.py
    - .github/workflows/ci.yml

key-decisions:
  - "MLK Day restricted to start_date 1998-01-01 (NYSE added it to its calendar that year) rather than pandas' own USMartinLutherKingJr default of 1986, per the plan's explicit test requirement"
  - "New Year's Day uses sunday_to_monday (not nearest_workday) so a Saturday Jan 1 does not generate a phantom Friday Dec 31 holiday — matches the plan's explicit 2021-12-31 exclusion test"
  - "Did not loosen core/config.py's rewrite_tolerance_pct after the live job re-run flagged a volume-only revision on the most recent committed day (see Issues Encountered) — left the D-13 tolerance exactly as decided in CONTEXT.md and documented the finding instead"

requirements-completed: [DATA-01, DATA-02, DATA-03, OPS-05]

# Metrics
duration: ~25min active (plus a rate-limit pause between the RED test commit and the GREEN implementation commit)
completed: 2026-10-08
---

# Phase 1 Plan 02: Nightly Validation Gate and Scheduling Summary

**NYSE session calendar from pandas holiday rules, a D-13 validate_snapshot() gate wired into jobs/refresh_prices.py, and a weekday-21:30-UTC nightly.yml with a paths-ignore CI-loop guard.**

## Performance

- **Duration:** ~25 min of active work (test/implementation/wiring), interrupted once by a
  rate-limit pause between the RED test commit (`0724eca`) and the GREEN implementation
  commit (`3378491`); resumed cleanly from the existing worktree state with no rework.
- **Started:** 2026-10-08T01:05 (first commit)
- **Completed:** 2026-10-08T02:39 (last task commit)
- **Tasks:** 2
- **Files modified:** 8 (5 created, 3 modified)

## Accomplishments

- `core/market_calendar.py` builds the NYSE trading-session calendar entirely from
  `pandas.tseries.holiday` primitives (no new dependency) plus a hand-verified
  `NYSE_SPECIAL_CLOSURES` tuple (9/11, Hurricane Sandy, four state/presidential funerals).
  `test_committed_snapshot_has_no_missing_sessions` verifies the calendar against the real
  33-year `data/prices.parquet` snapshot with zero missing sessions.
- `core/validate.py`'s `validate_snapshot()` enforces every D-13 branch — row-count shrink,
  last-date regression, OHLCV rewrite beyond `cfg.rewrite_tolerance_pct`, non-common-factor
  `adj_close` restatement, and missing NYSE sessions — each with its own test.
  `drop_incomplete_session()` strips today's bar when fetched before
  `cfg.session_complete_after_et` (US/Eastern).
- `jobs/refresh_prices.py` now calls `drop_incomplete_session()` then `validate_snapshot()`
  before the existing `_write_snapshot()` call site; a `ValueError` prints
  `"snapshot rejected: {reason}; keeping last snapshot"` to stderr and returns 1 without
  touching `data/prices.parquet` or `data/meta.json`.
- `.github/workflows/nightly.yml` schedules the refresh for weekdays ~21:30 UTC plus
  `workflow_dispatch`, uses only the default `GITHUB_TOKEN` (no PAT), `contents: write`
  permissions, a `nightly-refresh` concurrency group, and a hand-rolled
  add/commit/push step with no `[skip ci]` marker.
- `.github/workflows/ci.yml` adds `paths-ignore: ["data/**"]` under `push` as defense in
  depth against a CI loop, alongside the already-safe GITHUB_TOKEN-push behavior.
- Full suite: 63 tests pass (`pytest -q`); `ruff check .` is clean.
- Ran `python -m jobs.refresh_prices` locally against the real committed snapshot — see
  Issues Encountered for the result (exit 1, a genuine D-13 volume-tolerance rejection, not
  a gate bug).

## Task Commits

Each task was committed atomically, split into RED/GREEN per its `tdd="true"` frontmatter:

1. **Task 1: NYSE session calendar and validate_snapshot gate (D-13, DATA-03)**
   - `0724eca` (test) — failing tests for `core.market_calendar` and `core.validate`
   - `3378491` (feat) — `core/market_calendar.py` and `core/validate.py` implementations
2. **Task 2: Wire the gate into the job, nightly workflow, CI loop guard**
   - `8f7ec14` (feat) — `jobs/refresh_prices.py` wiring, updated
     `tests/test_refresh_prices.py`, `.github/workflows/nightly.yml`,
     `.github/workflows/ci.yml`

_RED confirmed for Task 1 by moving `core/market_calendar.py` and `core/validate.py` out of
the tree and re-running `pytest tests/test_market_calendar.py tests/test_validate_snapshot.py`
(`ModuleNotFoundError` on both). GREEN reached immediately after restoring the files — all 29
new tests passed on the first run._

## Files Created/Modified

- `core/market_calendar.py` - `NYSEHolidayCalendar`, `NYSE_SPECIAL_CLOSURES`,
  `nyse_holidays(start, end)`, `nyse_sessions(start, end)`
- `core/validate.py` - `validate_snapshot(new, old, cfg)`, `drop_incomplete_session(df, now_utc, cfg)`
- `jobs/refresh_prices.py` - inserted the gate between fetch and `_write_snapshot()`;
  loads `old` via `core.storage.load_prices` only if `prices_path` exists
- `tests/test_market_calendar.py` - holiday inclusion/exclusion, session-range, and the
  real-snapshot gap check (29 parametrized + standalone cases combined with
  test_validate_snapshot.py)
- `tests/test_validate_snapshot.py` - one test per D-13 branch plus `drop_incomplete_session`
  partial-bar behavior, using a local `nyse_frame` fixture (not `conftest.py`'s
  `tiny_prices`/`random_prices`, which sit on `pd.bdate_range` and include holidays)
- `tests/test_refresh_prices.py` - added a local `_gapless_frame()` helper on real NYSE
  sessions; switched the two success-path tests off `tiny_prices` (which includes the
  2024-01-01 New Year's Day row); added
  `test_main_exits_1_on_validation_failure_and_keeps_files`,
  `test_main_exits_1_when_fetched_history_shrinks`, and
  `test_main_first_run_without_existing_snapshot_writes`
- `.github/workflows/nightly.yml` - new scheduled workflow (D-14, D-15, D-16)
- `.github/workflows/ci.yml` - added `paths-ignore: ["data/**"]` under `push`

## Decisions Made

- MLK Day's `start_date` is `1998-01-01` (a custom `Holiday`, not pandas' own
  `USMartinLutherKingJr` which defaults to 1986) because the test suite requires excluding
  1997-01-20 — NYSE added MLK Day to its calendar in 1998, four years after the federal
  holiday existed.
- New Year's Day uses `sunday_to_monday` observance specifically so a Saturday January 1st
  does not shift to the prior Friday — required to pass the 2021-12-31 exclusion test and
  matches the plan's explicit note that "NYSE does not close the prior Friday when Jan 1 is
  a Saturday."
- `tests/test_refresh_prices.py`'s success-path tests build their own gapless frame via
  `core.market_calendar.nyse_sessions("2024-01-02", "2024-01-10")` rather than reusing
  `conftest.py`'s `tiny_prices` (which starts on 2024-01-01, a NYSE holiday) — per the plan's
  explicit instruction, and without touching `conftest.py` itself (Phase 0 tests depend on
  it unchanged).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ruff RUF012 on `NYSEHolidayCalendar.rules`**
- **Found during:** Task 1 ruff pass
- **Issue:** `rules = [...]` as a bare class attribute holding a mutable list tripped
  `RUF012` (mutable default value for a class attribute).
- **Fix:** Annotated it `rules: ClassVar[list[Holiday]] = [...]` — this is pandas'
  own `AbstractHolidayCalendar.rules` contract (a genuine class-level default, not
  instance state), so `ClassVar` is the correct annotation, not a workaround.
- **Files modified:** `core/market_calendar.py`
- **Verification:** `ruff check core tests` — all checks passed
- **Committed in:** `3378491` (part of Task 1's feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — lint-only, no behavior change).
**Impact on plan:** None. No change to the planned contracts, file list, or architecture.

## Issues Encountered

**Live job re-run against the real snapshot rejected on a volume-only revision, not a bug.**
Running `python -m jobs.refresh_prices` locally (per the plan's own overall `<verification>`
step) against the real committed `data/prices.parquet` exited 1:

```
snapshot rejected: volume rewritten beyond tolerance on 1 rows, first 2026-10-07; keeping last snapshot
```

Investigation: every OHLC column matched exactly between the freshly-fetched frame and the
committed snapshot across the full overlap (33 years, zero mismatches). The *only* mismatch
was `volume` on the single most recent trading day (2026-10-07), which came back ~0.69% higher
than what Yahoo reported the previous time it was fetched (30,958,200 vs. 30,746,070). This
matches a well-documented Yahoo Finance / exchange behavior: consolidated-tape volume for the
most recently completed session continues to be revised for a day or two after close as
off-exchange trade reports are reconciled, independent of the OHLC prices themselves.

Both `data/prices.parquet` and `data/meta.json` were confirmed byte-identical before and after
the rejected run (verified via `md5sum`), so the gate behaved exactly as specified — this is
the D-13 gate correctly doing its job on a real, if benign, discrepancy, not a defect in
`validate.py` or `market_calendar.py`.

Per the plan's explicit instruction ("do not loosen tolerances without a test and SUMMARY
note"), the `rewrite_tolerance_pct` value in `core/config.py` was **not** changed — that
tolerance is a D-13 decision owned by `01-CONTEXT.md`, and loosening it is an architectural
call for the user, not something to auto-fix mid-plan. Flagging as a blocker for a future
plan/decision below.

## User Setup Required

None - no external service configuration required. `.github/workflows/nightly.yml` uses only
the default `GITHUB_TOKEN` that GitHub Actions provides automatically; no secrets or PAT setup
needed.

## Next Phase Readiness

- `core/market_calendar.py` and `core/validate.py` are available for any later plan that
  needs NYSE session awareness (e.g., Phase 2's event-detector day boundaries).
- **Blocker/Concern carried forward:** the nightly job may reject its own most-recent-day
  volume on a non-trivial fraction of real runs, because Yahoo Finance revises the latest
  session's consolidated volume for a day or two after close, and D-13's `rewrite_tolerance_pct`
  (0.01%) is tight enough to catch that revision. If this repeats in practice (observable once
  `nightly.yml` is actually running on a schedule), the fix is almost certainly to special-case
  the single most-recent committed day's volume column the same way `drop_incomplete_session`
  already special-cases *today's* bar — not to loosen the tolerance for all historical rows.
  This needs a CONTEXT.md decision before being implemented, since D-13 did not anticipate it.
- No other blockers. Tasks 1 and 2's acceptance criteria (NYSE calendar vs. real data, gate
  branch coverage, nightly schedule/trigger shape, CI loop guard) all pass as specified.

---
*Phase: 01-foundation-overview-strategy-lab*
*Completed: 2026-10-08*

## Self-Check: PASSED

All 8 claimed files found on disk; all 3 claimed commit hashes found in git log.
