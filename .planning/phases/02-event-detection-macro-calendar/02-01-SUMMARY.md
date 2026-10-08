---
phase: 02-event-detection-macro-calendar
plan: 01
subsystem: data
tags: [pandas, numpy, event-detection, backtesting-data, pyarrow]

# Dependency graph
requires:
  - phase: 00-foundation
    provides: core/config.py Settings pattern, core/storage.py load/write contracts, data/prices.parquet
  - phase: 01-data-pipeline
    provides: data/prices.parquet (1993-01-29..2026-10-07, total-return basis), jobs/refresh_prices.py job shape
provides:
  - core/events.py pure detector (log_returns, shock_zscores, shock_days, gap_days, drawdown_legs, rally_legs, cluster_legs, detect)
  - jobs/detect_events.py job writing data/episodes.parquet and bumping meta.json detector_version
  - core/storage.py load_episodes/write_episodes
  - data/episodes.parquet: committed 1993+ backfill (142 episodes)
affects: [02-02-replay-stability, 02-03-macro-calendar, 02-04-calendar-tagging, 02-05-episode-finalisation, phase-03-news-enrichment, phase-04-event-explorer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Steepest-leg clustering (D-01): drawdown/rally legs cluster on peak->trough / trough->peak, never on the full peak->recovery span -- keeps the 1993+ backfill in the low hundreds (142) instead of fragmenting into years-long mega-episodes"
    - "Trigger precedence drawdown>rally>shock>gap resolved via settings.trigger_precedence tuple, never dict/set iteration order"
    - "Anchor day = largest |log return| within [start_pos,end_pos] via np.nanargmax (ties resolve to the earliest position automatically)"
    - "All detection thresholds live in core.config.Settings; core/events.py takes a Settings argument and contains no hard-coded threshold literals"

key-files:
  created:
    - core/events.py
    - jobs/detect_events.py
    - tests/test_detect_events.py
    - tests/test_events.py
    - data/episodes.parquet
  modified:
    - core/config.py
    - core/storage.py
    - data/meta.json

key-decisions:
  - "D-01 (steepest-leg clustering) confirmed empirically: 142 episodes on the real 1993-05-19..2026-06-05 window, all seven DET-07 known episodes map to exactly one episode each, Feb 2018 and Q4 2018 land on separate episode_ids"
  - "rally_threshold temporarily set to an unreachable value (10.0) via dataclasses.replace in two core/events.py tests to isolate drawdown/shock/gap clustering behaviour from an otherwise-inevitable co-occurring rally leg on any sharp crash+recovery fixture -- a test-only override, not a production default change"

patterns-established:
  - "Pattern 1 (steepest-leg interval merge) from 02-RESEARCH.md applied verbatim in core/events.py::cluster_legs"
  - "Pattern 2 (deterministic episode_id = f'{anchor_date:%Y-%m-%d}_{trigger}') applied verbatim"

requirements-completed: [DET-01, DET-02, DET-03, DET-04, DET-06, DET-07]

# Metrics
duration: 15min
completed: 2026-10-08
---

# Phase 2 Plan 01: Event Detection Summary

**Pure shock/gap/drawdown/rally detector with steepest-leg clustering (core/events.py), producing a committed 142-episode SPY backfill (1993-2026) that correctly isolates all seven known crashes.**

## Performance

- **Duration:** ~15 min (first commit to last)
- **Started:** 2026-10-08T20:44Z
- **Completed:** 2026-10-08T20:58Z
- **Tasks:** 3 completed
- **Files modified:** 8 (core/config.py, core/events.py, core/storage.py, jobs/detect_events.py, tests/test_detect_events.py, tests/test_events.py, data/episodes.parquet, data/meta.json)

## Accomplishments
- `core/events.py`: pure, config-driven detector implementing DET-01 (shock days, sigma lagged one day), DET-02 (gap days), DET-03 (drawdown/rally legs via a causal running-peak scan), DET-04 (steepest-leg clustering per D-01, trigger precedence, deterministic anchor/episode_id, severity)
- `jobs/detect_events.py`: reads `data/prices.parquet` on the total-return basis, calls `core.events.detect`, writes `data/episodes.parquet`, bumps `meta.json`'s `detector_version`, fails loud on any error without touching `data/`
- Ran the job against the real committed 1993+ history: **142 episodes** (75 shock, 30 drawdown, 28 rally, 9 gap), well inside the (100, 300) DET-06 bound and close to research's ~151 estimate (the ~6% difference traces to rally-leg merge boundary details, not a bug -- all tests pass and the count stays well inside bounds)
- All seven DET-07 known episodes verified present, each as exactly one episode: 2000-02 -> `2000-04-14_drawdown`, 2008 -> `2008-10-13_drawdown`, Aug 2015 -> `2015-08-24_drawdown`, Feb 2018 -> `2018-02-05_drawdown`, Q4 2018 -> `2018-12-26_drawdown`, Mar 2020 -> `2020-03-16_drawdown`, 2022 -> `2022-11-10_drawdown` (Feb 2018 and Q4 2018 confirmed on separate episode_ids, per DET-07)
- 24 new tests across `tests/test_detect_events.py` (end-to-end, real data) and `tests/test_events.py` (13 hand-checkable per-primitive tests: sigma lag, gap boundary, drawdown/rally leg math, trading-day-vs-calendar-day clustering including a holiday-skipped Thu/Mon case, D-01 non-absorption via recovery span, trigger precedence, earliest-on-tie anchor selection, severity formula, config-driven threshold flow)

## Task Commits

Each task was committed atomically:

1. **Task 1: Failing end-to-end test for the detector job on real data** - `7b4cd53` (test)
2. **Task 2: Detector + job + storage — make the end-to-end test pass** - `0b2a8c3` (feat)
3. **Task 3: Hand-checkable unit tests per rule, then commit the 1993+ backfill artifact** - `b779a02` (test)

_No separate plan-metadata commit was requested by this execution request; SUMMARY.md/STATE.md/ROADMAP.md updates will follow this one._

## Files Created/Modified
- `core/events.py` - Pure detector: `Leg` dataclass, `log_returns`, `shock_zscores`, `shock_days`, `gap_days`, `drawdown_legs`, `rally_legs`, `cluster_legs`, `detect`, `EPISODE_COLUMNS`
- `jobs/detect_events.py` - I/O job: loads prices, converts to total return, calls `detect`, writes `data/episodes.parquet` + bumps `detector_version`
- `core/config.py` - Added episode-detection `Settings` fields (shock/gap/drawdown/rally thresholds, merge window, search windows, severity step, trigger precedence, episode count bounds); `detector_version` bumped 0 -> 1
- `core/storage.py` - Added `load_episodes`/`write_episodes`, same `FileNotFoundError`-propagating contract as `load_prices`/`load_meta`
- `tests/test_detect_events.py` - End-to-end real-data test: schema, DET-06 count bounds, DET-07 known episodes, meta version bump
- `tests/test_events.py` - 13 hand-checkable unit tests pinning every detection rule
- `data/episodes.parquet` - Committed 1993-05-19..2026-06-05 backfill (142 rows)
- `data/meta.json` - `detector_version` now `1`

## Decisions Made
- D-01 (steepest-leg clustering, from `02-CONTEXT.md`) implemented exactly as specified: drawdown legs cluster on peak->trough, rally legs on trough->peak, never on the full peak->recovery span. Confirmed empirically on real data: 142 episodes, all DET-07 probes land on exactly one episode each.
- `detector_version` bumped from 0 to 1 in `core/config.py`'s `Settings` default, per the plan's instruction, marking "Phase 2 steepest-leg detector" as the first real detector version.
- Anchor-day tie-breaking (same |log return| magnitude on two different days in a cluster) resolves to the earliest day via `np.nanargmax`'s first-occurrence-on-tie behavior -- verified with a dedicated hand-constructed exact-tie fixture in `tests/test_events.py`.

## Deviations from Plan

None - plan executed exactly as written. Both end-to-end (Task 1) and hand-checkable (Task 3) tests passed on the first implementation pass with no bugs found in `core/events.py` requiring a fix; no deviation-rule triggers occurred.

## Issues Encountered

None. The real-data episode count (142) differs from research's scratch-script estimate (~151) by about 6% -- the plan explicitly anticipated this ("rally-leg merge details differ from the research scratch script") and instructed not to tune thresholds unless the count leaves the (100, 300) bound, which it does not.

## User Setup Required

None - no external service configuration required. This plan has no network calls; it reads the already-committed `data/prices.parquet`.

## Next Phase Readiness
- `data/episodes.parquet` (142 rows, schema-complete per `EPISODE_COLUMNS`) is ready for 02-02 (replay-stability / `status` column, DET-05) and 02-05 (macro-calendar tagging join, CAL-02).
- `core/events.py`'s pure primitives (`shock_days`, `gap_days`, `drawdown_legs`, `rally_legs`, `cluster_legs`) are independently unit-tested and importable for any downstream plan needing to re-run or extend detection logic.
- No blockers for 02-02/02-03 work.

---
*Phase: 02-event-detection-macro-calendar*
*Completed: 2026-10-08*

## Self-Check: PASSED

All claimed files verified present on disk (core/events.py, jobs/detect_events.py,
tests/test_detect_events.py, tests/test_events.py, data/episodes.parquet, core/config.py,
core/storage.py, data/meta.json). All claimed commit hashes (7b4cd53, 0b2a8c3, b779a02)
verified present in `git log --oneline --all`.
