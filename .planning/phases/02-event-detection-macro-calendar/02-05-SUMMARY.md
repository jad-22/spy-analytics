---
phase: 02-event-detection-macro-calendar
plan: 05
subsystem: data
tags: [pandas, pyarrow, event-detection, macro-calendar, calibration]

# Dependency graph
requires:
  - phase: 02-event-detection-macro-calendar
    plan: 02
    provides: core/events.py::detect with status ("closed"/"open") and closure_frontier replay-stability proof
  - phase: 02-event-detection-macro-calendar
    plan: 04
    provides: data/macro_calendar.parquet (1138 rows, FOMC/CPI/payrolls 1993..2027, CALENDAR_COLUMNS)
provides:
  - core/calendar.py::tag_episodes(episodes, calendar) -> episodes + TAG_COLUMNS (scheduled_releases, unscheduled_releases, catalyst)
  - jobs/detect_events.py --calendar-path, fail-loud (exit 1, no write) when the macro calendar is missing
  - data/episodes.parquet final artifact (142 episodes, 73 scheduled / 69 surprise)
  - scripts/report_phase2.py -> docs/PHASE2_CALIBRATION.md (script-generated, byte-stable, do-not-hand-edit)
  - docs/ROADMAP.md Phase 2 items 1-4 checked off; "macro calendar US-only?" open question resolved
affects: [phase-03-news-enrichment, phase-04-event-explorer, phase-04-methodology]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "tag_episodes: pure window-membership tag over [search_from, search_to] inclusive on calendar dates (not trading days); catalyst is 'scheduled' iff scheduled_releases is non-empty, so an unscheduled-only or empty window is always 'surprise' -- only a scheduled release makes a move calendar-explainable (RESEARCH Pitfall 2)."
    - "scripts/report_phase2.py is the single source of truth for the DET-07 known-episode probe list (KNOWN_EPISODES); tests/test_detect_events.py imports it rather than duplicating it, so the probe dates can't silently drift between the test and the calibration doc."

key-files:
  created:
    - scripts/report_phase2.py
    - docs/PHASE2_CALIBRATION.md
  modified:
    - core/calendar.py
    - jobs/detect_events.py
    - tests/test_calendar.py
    - tests/test_detect_events.py
    - tests/test_episode_replay.py
    - data/episodes.parquet
    - docs/ROADMAP.md

key-decisions:
  - "catalyst = 'scheduled' iff scheduled_releases non-empty -- an episode whose only in-window release is unscheduled (e.g. Mar 2020's emergency FOMC action) is tagged 'surprise', not a weaker third category, matching the plan's must_haves truth and T-02-20's mitigation."
  - "jobs/detect_events.py now has two independent FileNotFoundError catches (prices, then calendar) instead of one shared except block, so the missing-calendar stderr message (naming jobs.build_macro_calendar / FRED_API_KEY) is only ever printed when the calendar is actually what's missing."
  - "DET-07's probe list moved to scripts/report_phase2.py as the single source of truth; tests/test_detect_events.py imports KNOWN_EPISODES from there instead of keeping a second hand-typed copy."

requirements-completed: [CAL-02, DET-06]

# Metrics
duration: ~8min (first task commit to plan-metadata commit)
completed: 2026-10-09
---

# Phase 2 Plan 05: Episode-Calendar Tagging and Calibration Record Summary

**Every committed episode now carries `scheduled_releases`/`unscheduled_releases`/`catalyst` tags computed from `data/macro_calendar.parquet`, and `docs/PHASE2_CALIBRATION.md` is a script-generated, byte-stable calibration record closing out Phase 2.**

## Performance

- **Duration:** ~8 min (first task commit `cca2b70` to plan-metadata commit)
- **Tasks:** 3 completed
- **Files modified:** 7 modified, 2 created

## Accomplishments

- `core/calendar.py::tag_episodes(episodes, calendar) -> pd.DataFrame`: appends
  `TAG_COLUMNS = (scheduled_releases, unscheduled_releases, catalyst)`. For each episode,
  selects calendar rows with `date` in `[search_from, search_to]` inclusive on calendar
  dates (including non-trading days), formats each as `f"{release} {date:%Y-%m-%d}"`
  sorted by `(date, release)`; `scheduled=True` rows go to `scheduled_releases`,
  `scheduled=False` rows go to `unscheduled_releases`; `catalyst` is `"scheduled"` iff
  `scheduled_releases` is non-empty, else `"surprise"`. Pure: does not mutate either
  input, preserves episode row order and `EPISODE_COLUMNS`, raises `ValueError` if the
  calendar is missing a `CALENDAR_COLUMNS` column. No import of `core.events` (keeps
  `core/calendar.py` and `core/events.py` decoupled pure siblings, per 02-PATTERNS.md).
- `jobs/detect_events.py`: new `--calendar-path` (default `SETTINGS.macro_calendar_path`);
  loads the committed calendar via `core.storage.load_macro_calendar` before writing;
  a missing calendar prints `"macro calendar missing at PATH; run
  jobs.build_macro_calendar locally (needs FRED_API_KEY)"` to stderr and exits 1 without
  touching `data/episodes.parquet` or `data/meta.json`. `episodes =
  tag_episodes(detect(prices, SETTINGS), calendar)` is the new single pipeline call.
- `data/episodes.parquet` regenerated: same 142 episodes as before (detection logic
  unchanged), now carrying tags -- 73 `"scheduled"` / 69 `"surprise"`. The Mar 2020
  episode (`2020-03-16_drawdown`) confirms `unscheduled_releases == ["FOMC
  2020-03-15"]`, `scheduled_releases == []`, `catalyst == "surprise"` (the emergency
  Sunday-announced rate cut never counts as a scheduled catalyst).
- `tests/test_episode_replay.py`'s six-cutoff real-data replay test now runs
  `tag_episodes` on both the truncated and full-history detection output and asserts
  `catalyst`, `scheduled_releases` and `unscheduled_releases` are identical (as lists)
  for every already-closed episode -- extending DET-05's replay-stability contract to
  CAL-02's tag columns.
- `scripts/report_phase2.py` (`python -m scripts.report_phase2`, no network): reads
  `data/episodes.parquet` and `data/macro_calendar.parquet` via `core.storage` plus
  every DET/CAL `Settings` field (by name, listed explicitly so an unrelated future field
  can't silently appear or vanish) and writes `docs/PHASE2_CALIBRATION.md`: thresholds
  (incl. `detector_version` and the D-01 steepest-leg note), episode counts by
  trigger/status/catalyst/direction/decade, the DET-07 known-episode table (episode_id,
  start, end, trigger, `move_pct`, catalyst), and macro calendar coverage (rows per
  release, first/last date, unscheduled FOMC count). Verified byte-stable: staging the
  first run's output and re-running produces no `git diff`.
- `docs/ROADMAP.md`: Phase 2 items 1-4 checked off (item 4 now references the
  calibration doc), and the "macro calendar: US-only, or add BoE/ECB?" open question is
  resolved `[x]` as US-only per CAL-01.

## Task Commits

Each task was committed atomically:

1. **Task 1: Failing tagging tests (unit + end-to-end on real data)** - `cca2b70` (test)
2. **Task 2: Implement tag_episodes, wire the job, regenerate the final artifact** - `3aac49d` (feat)
3. **Task 3: Script-generated calibration record and roadmap update** - `7477e13` (docs)

_No separate plan-metadata commit was requested ahead of this one; SUMMARY.md/STATE.md/ROADMAP.md (`.planning/`) updates follow this one._

## Files Created/Modified

- `core/calendar.py` - Added `TAG_COLUMNS` and `tag_episodes()`
- `jobs/detect_events.py` - Added `--calendar-path`; two independent `FileNotFoundError`
  catches (prices, calendar); pipeline now tags episodes before writing
- `tests/test_calendar.py` - 7 `tag_episodes` tests (precedence, exclusion, inclusive
  bounds, sort order, purity, missing-column `ValueError`)
- `tests/test_detect_events.py` - `--calendar-path` wired into the module fixture; 5 new
  e2e tests (tag columns present, in-window invariant, catalyst<->scheduled_releases
  equivalence, Mar 2020 assertion, missing-calendar exit-1); `KNOWN_EPISODES` now
  imported from `scripts.report_phase2` instead of a local duplicate
- `tests/test_episode_replay.py` - Real-data replay test now tags both before/after
  detection runs and compares `catalyst` + both release-list columns
- `data/episodes.parquet` - Regenerated with `TAG_COLUMNS`; 142 episodes, unchanged counts
- `scripts/report_phase2.py` - New: generates `docs/PHASE2_CALIBRATION.md`
- `docs/PHASE2_CALIBRATION.md` - New: script-generated calibration record
- `docs/ROADMAP.md` - Phase 2 items 1-4 checked off; US-only open question resolved

## Decisions Made

- `catalyst` is `"scheduled"` iff `scheduled_releases` is non-empty; an unscheduled-only
  or empty window is always `"surprise"` -- no third "mixed" category, matching the
  plan's must-haves and T-02-20's mitigation plan exactly.
- `jobs/detect_events.py` splits the old single `except (ValueError, FileNotFoundError)`
  block into two sequential `try`/`except FileNotFoundError` blocks (prices, then
  calendar) so the calendar-specific remediation message is never shown for an unrelated
  missing-prices failure.
- Moved the DET-07 probe list (`KNOWN_EPISODES`) into `scripts/report_phase2.py` as the
  single source of truth, with `tests/test_detect_events.py` importing it -- avoids two
  hand-typed copies of the same seven dates drifting apart.

## Deviations from Plan

None - plan executed exactly as written. All three tasks' acceptance criteria were met
on the first implementation pass; the only design choice not spelled out verbatim in the
plan (splitting the job's exception handling into two blocks, and centralizing
`KNOWN_EPISODES` in the script) followed directly from the plan's own explicit
instructions ("fails... if the macro calendar is missing", "reuse the probe list by
importing it from a small constant in the script, kept identical to
tests/test_detect_events.py") rather than introducing new scope.

## Issues Encountered

Ruff's `ISC004` flagged two implicit string concatenations inside list literals in
`scripts/report_phase2.py` (the D-01 note and the calibration doc's header sentence).
Fixed by wrapping each in parentheses before the first commit of Task 3's work landed;
verified the resulting string values are byte-identical to the original concatenation
and reran `ruff check .` clean.

## User Setup Required

None - no external service configuration required. This plan has no network calls; it
reads the already-committed `data/prices.parquet` and `data/macro_calendar.parquet` and
writes `data/episodes.parquet` and `docs/PHASE2_CALIBRATION.md`.

## Next Phase Readiness

- Phase 2's roadmap gate is now fully met: episode count (142) is in the target range,
  all seven DET-07 known episodes are detected (table in
  `docs/PHASE2_CALIBRATION.md`), and every episode carries a scheduled/surprise tag
  Phase 3's news enrichment can condition its prompt on.
- `data/episodes.parquet`'s `status == "closed"` + `TAG_COLUMNS` combination is the
  exact input contract Phase 3's paid Claude API backfill should filter to.
- No blockers for Phase 3.

---
*Phase: 02-event-detection-macro-calendar*
*Completed: 2026-10-09*

## Self-Check: PASSED

- All claimed files verified present on disk: `core/calendar.py`, `jobs/detect_events.py`,
  `scripts/report_phase2.py`, `docs/PHASE2_CALIBRATION.md`, `data/episodes.parquet`,
  `docs/ROADMAP.md`.
- All three claimed commit hashes (`cca2b70`, `3aac49d`, `7477e13`) verified present in
  `git log --oneline --all`.
- Full suite: 229 passed; `ruff check .`: all checks passed (re-verified after Task 3).
- `docs/PHASE2_CALIBRATION.md` rerun verified byte-stable (`git diff --exit-code` clean
  after a second run against the staged first-run output).
