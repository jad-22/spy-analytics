---
phase: 02-event-detection-macro-calendar
plan: 02
subsystem: data
tags: [pandas, numpy, event-detection, replay-stability, pyarrow]

# Dependency graph
requires:
  - phase: 02-event-detection-macro-calendar
    plan: 01
    provides: core/events.py pure detector (Leg, log_returns, shock_zscores, shock_days, gap_days, drawdown_legs, rally_legs, cluster_legs, detect), jobs/detect_events.py, data/episodes.parquet (142-episode 1993+ backfill, no status column)
provides:
  - core/events.py::closure_frontier(close, settings) -> int, the proven DET-05 replay-stability boundary
  - "status" column ("closed"/"open") on every episode row, immediately before detector_version in EPISODE_COLUMNS
  - tests/test_episode_replay.py: synthetic + real-data (six-cutoff) replay-stability proof
  - tests/test_events.py: AST guards for DET-06 (no non-0/1 literals) and core/events.py purity (no network/core.data/core.storage/jobs imports)
  - data/episodes.parquet regenerated with status column (142 episodes, all "closed")
affects: [02-03-macro-calendar, 02-04-calendar-tagging, 02-05-episode-finalisation, phase-03-news-enrichment, phase-04-event-explorer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "closure_frontier: an episode cluster is 'closed' iff end_pos + merge_window_days < frontier AND every drawdown leg in it has recovered; frontier = min(next unseen position, next unseen position minus rally_window_days, and -- only when the series' last close is below its own running all-time peak -- that peak's position). Proven never touched by future append-only data; see core/events.py::closure_frontier docstring for the full proof."
    - "Open-episode IDs/fields may still change as more data arrives; only 'closed' rows are safe for Phase 3's paid enrichment to consume (documented in core/events.py's module docstring)."

key-files:
  created:
    - tests/test_episode_replay.py
  modified:
    - core/events.py
    - tests/test_events.py
    - data/episodes.parquet

key-decisions:
  - "closure_frontier's three candidate positions (future shock/gap day, future rally lookback, live running-peak position) are taken as a plain minimum, not a weighted or settings-driven combination -- each is independently a hard lower bound on what future data can touch, so the minimum is the tightest correct frontier."
  - "The running-peak frontier candidate fires at ANY depth below peak (not just >= drawdown_threshold), per the plan's explicit instruction: a shallow dip may deepen into a qualifying drawdown leg later, so even a 1-tick dip keeps the peak position live."

requirements-completed: [DET-05, DET-06]

# Metrics
duration: 12min
completed: 2026-10-08
---

# Phase 2 Plan 02: Episode Replay Stability Summary

**closure_frontier() proves and tests (synthetic + six real-data cutoffs) that closed episodes in `core/events.py::detect` never change under append-only price data, gating Phase 3's irreversible LLM spend.**

## Performance

- **Duration:** ~12 min (first commit to last)
- **Tasks:** 2 completed
- **Files modified:** 3 (core/events.py, tests/test_events.py, data/episodes.parquet) + 1 created (tests/test_episode_replay.py)

## Accomplishments

- `core/events.py::closure_frontier(close, settings) -> int`: computes the integer position
  before which no future appended row can ever reach back into an already-formed cluster,
  as the minimum of three proven lower bounds -- (a) the first not-yet-seen position (bounds
  a future shock/gap day), (b) that position minus `rally_window_days` (bounds a future
  rally's look-back trough), (c) the series' live running all-time-peak position, only when
  the last close is below it by any depth (bounds a future drawdown leg's start). Full proof
  in the function's docstring.
- `detect()` now tags every episode `status = "closed"` iff `end_pos + merge_window_days <
  frontier` **and** every drawdown leg in the cluster has a recovery date; otherwise `"open"`.
  `status` added to `EPISODE_COLUMNS` immediately before `detector_version` (verified by
  `EPISODE_COLUMNS.index("status") == len(EPISODE_COLUMNS) - 2`).
- `tests/test_episode_replay.py` (9 tests): four synthetic fixtures hand-pin the closure rule
  (a shock cluster closes and survives a 50-bar append including a second, independent shock;
  an episode ending mid-drawdown at the end of data is open with `recovery_date` `NaT`, and
  every episode at/after the running peak is open; a shock 2 bars from the end is open; a
  cluster exactly `merge_window_days + rally_window_days + 1` bars before a new high is
  closed) plus a parametrized real-data test across six cutoffs (2002, 2008, 2011, 2016, 2020,
  2023) proving every closed episode detected on truncated history is byte-identical (dates,
  trigger, triggers, search window, status) and float-identical to `rel=1e-9`
  (`move_pct`/`max_z`/`severity`) in the full-history run, plus a dot-com-specific check that
  no closed episode at the 2002-12-31 cutoff starts at or after that cutoff's running
  all-time-peak date (D-01: the dot-com leg is still open).
- `tests/test_events.py`: added `test_events_module_has_no_numeric_literals` (AST scan,
  DET-06) and `test_events_module_is_pure` (AST import scan, mirrors
  `tests/test_app_purity.py`'s forbidden-module list) -- both pass against the
  unmodified-by-this-task body of `core/events.py`, confirming the module already honored
  config-driven thresholds and the purity boundary from 02-01.
- `data/episodes.parquet` regenerated via `python -m jobs.detect_events`: same 142 episodes
  as 02-01 (detection logic unchanged, only a new derived column added), all 142 tagged
  `"closed"` -- the committed price history ends 2026-10-07 and the latest episode ends
  2026-06-05, well past every episode's `merge_window_days + rally_window_days + 1`-bar
  frontier.

## Task Commits

Each task was committed atomically:

1. **Task 1: Failing replay tests, then closure frontier + status column** - `2d80740` (test)
2. **Task 2: Config-literal and purity guards, regenerate the committed backfill** - `e08f70c` (test)

_No separate plan-metadata commit was requested ahead of this one; SUMMARY.md/STATE.md/ROADMAP.md updates follow this one._

## Files Created/Modified

- `core/events.py` - Added `closure_frontier`; `detect()` now computes and attaches `status`;
  module docstring extended with the DET-05 replay-stability contract and the Yahoo
  adj_close-rounding limitation note
- `tests/test_episode_replay.py` - New: 4 synthetic closure-rule tests + 1 parametrized
  six-cutoff real-data replay-stability test + 1 dot-com-specific open-leg check
- `tests/test_events.py` - Added 2 AST-based guard tests (no non-0/1 literals; purity/import
  boundary)
- `data/episodes.parquet` - Regenerated with the `status` column; row count unchanged (142)

## Decisions Made

- `closure_frontier`'s three lower bounds are combined with a plain `min()` -- each is
  independently a hard structural bound (not a tunable heuristic), so no weighting or
  settings-driven combination logic was needed.
- The running-peak frontier candidate activates at *any* depth below peak, per the plan's
  explicit instruction, not only once a dip reaches `drawdown_threshold` -- a shallow dip
  that hasn't yet qualified as a drawdown leg could still deepen into one on the next
  appended row, so the peak position must stay a live lower bound regardless of current
  depth.

## Deviations from Plan

None - plan executed exactly as written. Both the replay-stability tests (Task 1) and the
purity/literal guards (Task 2) passed on the first implementation pass; the Task 2 guard
tests passed against the *unmodified* 02-01 body of `core/events.py` (no fix was needed --
02-01 already honored the config-driven-thresholds and purity rules this task's tests pin
down), so no `core/config.py` edit or deviation-rule trigger occurred.

## Issues Encountered

None. The regenerated `data/episodes.parquet` has all 142 episodes marked `"closed"`, which
is expected (not a bug): the committed price history's last row (2026-10-07) is far enough
past every episode's end date that every cluster's frontier condition is satisfied. A
future nightly re-run close to "today" would be expected to show at least one `"open"` row
near the end of history -- this plan's synthetic tests already cover that case directly.

## User Setup Required

None - no external service configuration required. This plan has no network calls; it reads
and rewrites only the already-committed `data/prices.parquet` -> `data/episodes.parquet`
pipeline from 02-01.

## Next Phase Readiness

- `data/episodes.parquet` now carries a `status` column safe for 02-03/02-04 (macro-calendar
  tagging) and, critically, for Phase 3: its paid news-enrichment backfill can filter to
  `status == "closed"` rows only, per this plan's documented contract.
- `core/events.py::closure_frontier` is independently unit-tested and importable for any
  downstream job or test that needs to reason about which episodes are safe to treat as
  final.
- No blockers for 02-03/02-04/02-05 work.

---
*Phase: 02-event-detection-macro-calendar*
*Completed: 2026-10-08*

## Self-Check: PASSED

All claimed files verified present on disk (core/events.py, tests/test_episode_replay.py,
tests/test_events.py, data/episodes.parquet). Both claimed commit hashes (2d80740, e08f70c)
verified present in `git log --oneline --all`.
