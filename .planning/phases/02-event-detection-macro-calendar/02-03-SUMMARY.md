---
phase: 02-event-detection-macro-calendar
plan: 03
subsystem: data
tags: [pandas, requests, tenacity, fred-api, federalreserve-gov, parquet]

# Dependency graph
requires:
  - phase: 02-event-detection-macro-calendar
    plan: 01
    provides: core/storage.py load_episodes/write_episodes pattern, jobs/ job-shape precedent
affects: [02-04-fred-key-local-live-run, 02-05-episode-calendar-tagging, phase-03-news-enrichment, phase-04-event-explorer]
provides:
  - core/calendar.py pure parsers (parse_fomc_historical, parse_fomc_calendars, parse_fred_release_dates, merge_calendar, validate_macro_calendar, CALENDAR_COLUMNS)
  - core/data.py network fetchers (fetch_text, fetch_fred_release_dates, fetch_fred_release_name) -- the FRED api_key never appears in any exception message
  - core/storage.py load_macro_calendar/write_macro_calendar
  - jobs/build_macro_calendar.py: idempotent (D-03), local-key-only (D-02) CAL-01 builder, proven against five real captured federalreserve.gov fixtures and synthetic FRED JSON fixtures
  - tests/fixtures/macro/: 5 real federalreserve.gov pages + 2 synthetic FRED release/dates JSON fixtures, enabling fully offline CI (no network, no key)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FOMC header classification: 'Conference Call' or an '(unscheduled)' parenthetical annotation -> release_type=unscheduled, scheduled=False; a plain 'Meeting' -> scheduled=True; a '(cancelled)' meeting is dropped entirely (no decision was made on that date) -- verified against the real 1993/2008/2015/2020 fixtures, no hand-maintained override list needed"
    - "merge_calendar's 'fresh always wins' design: the job always rebuilds the full calendar_start..horizon window every run, so merge_calendar's only real job is the D-03 stability check (raise if a previously committed past row vanished from the fresh fetch); the merged output is always fresh itself, deduped and sorted"
    - "FRED api_key never touches an exception message: fetch_fred_release_dates/fetch_fred_release_name never call resp.raise_for_status() or reference resp.url, and wrap requests.RequestException in a ValueError naming only the exception type (T-02-09)"

key-files:
  created:
    - core/calendar.py
    - jobs/build_macro_calendar.py
    - tests/test_calendar.py
    - tests/test_build_macro_calendar.py
    - tests/fixtures/macro/fomchistorical1993.htm
    - tests/fixtures/macro/fomchistorical2008.htm
    - tests/fixtures/macro/fomchistorical2015.htm
    - tests/fixtures/macro/fomchistorical2020.htm
    - tests/fixtures/macro/fomccalendars.htm
    - tests/fixtures/macro/fred_release_dates_10.json
    - tests/fixtures/macro/fred_release_dates_50.json
  modified:
    - core/config.py
    - core/data.py
    - core/storage.py

key-decisions:
  - "A '(notation vote)' entry on the current fomccalendars.htm page (e.g. 'August 22 (notation vote) Statement on Longer-Run Goals and Monetary Policy Strategy') is not an FOMC rate-decision meeting -- excluded entirely from parse_fomc_calendars's output rather than tagged scheduled or unscheduled, since including it would push several years' FOMC counts outside the (7,8) bound and misrepresent what it is"
  - "A '(cancelled)' meeting on a historical page (2020's 'March 17-18 (cancelled) Meeting') produced no decision and is dropped entirely, not stored as a scheduled=False row -- distinct from '(unscheduled)' emergency meetings, which ARE real decisions and ARE stored"
  - "merge_calendar does not attempt a field-by-field reconciliation between existing and fresh; since the job always re-fetches the complete calendar_start..horizon window every run, the output is always fresh (deduped/sorted) and existing's only role is the D-03 missing-past-row integrity check"

requirements-completed: [CAL-01]

# Metrics
duration: 25min
completed: 2026-10-08
---

# Phase 2 Plan 03: Macro Calendar Builder Summary

**jobs/build_macro_calendar.py builds a 1993+ FOMC/CPI/payrolls calendar from real federalreserve.gov pages and the FRED API, proven idempotent and key-leak-safe entirely offline against five real captured HTML fixtures plus two synthetic FRED JSON fixtures.**

## Performance

- **Duration:** ~25 min (first commit to last)
- **Tasks:** 3 completed
- **Files modified:** 3 (core/config.py, core/data.py, core/storage.py) + 9 created (core/calendar.py, jobs/build_macro_calendar.py, 2 test files, 7 fixtures)

## Accomplishments

- Downloaded the five real federalreserve.gov pages live (1993/2008/2015/2020 historical
  per-year pages, current `fomccalendars.htm`) -- all five URLs resolved on the first try, no
  substitution needed. Hand-built two synthetic FRED `release/dates` JSON fixtures (CPI
  release_id=10, payrolls release_id=50) spanning 1993-01..1996-08 in the documented FRED
  schema.
- `core/calendar.py` (new, pure): `parse_fomc_historical`/`parse_fomc_calendars` classify every
  header by its literal text -- `"Conference Call"` or an `"(unscheduled)"` annotation ->
  `scheduled=False`; a plain `"Meeting"` -> `scheduled=True`; a `"(cancelled)"` meeting or a
  `"(notation vote)"` entry is dropped entirely (no decision happened). Verified against the
  real fixtures: 1993's 8 "Meeting" headers parse to exactly the 8 scheduled dates specified in
  the plan (`1993-02-03` .. `1993-12-21`); 2020's two `"(unscheduled)"` emergency actions
  (March 2, March 15) are captured as `scheduled=False`, its `"(cancelled)"` regular meeting
  (March 17-18) produces no row, leaving 7 scheduled meetings for 2020 -- inside the
  `fomc_scheduled_per_year=(7,8)` bound without any hand-maintained override list.
  `parse_fred_release_dates` turns a FRED JSON payload into rows with a pagination guard
  (`count > len(release_dates)` raises) and per-row `source_url`.
- `core/data.py`: `fetch_text`, `fetch_fred_release_dates`, `fetch_fred_release_name` follow
  `fetch_yfinance`'s exact local-import, fail-loud style. Neither FRED function ever calls
  `resp.raise_for_status()` or references `resp.url`; `requests.RequestException` is re-raised
  as `ValueError(f"FRED request failed for release_id={release_id}: {type(exc).__name__}")
  from None` -- the api_key can never leak into an exception message (T-02-09), proven by four
  dedicated leak tests using a sentinel key embedded in a fake connection error/400 response.
- `jobs/build_macro_calendar.py`: no `--api-key` CLI argument (D-02) -- the key is read only
  from `FRED_API_KEY` via `os.environ.get`. Confirms each FRED release_id's name every run
  (`fetch_fred_release_name`) before trusting its dates (RESEARCH A1), failing loud on a
  mismatch. All network calls go through a single `tenacity.Retrying` helper calling
  monkeypatchable module-level fetch names, matching `jobs/refresh_prices.py`'s pattern exactly.
- `core/calendar.py::merge_calendar`/`validate_macro_calendar` prove D-03 (idempotency) and the
  full validation contract (NaT dates, duplicate keys, insecure/`api_key`-bearing `source_url`,
  out-of-range dates, FRED-first-date-too-late, FOMC/monthly per-year count bounds) -- 40 tests
  across `tests/test_calendar.py` and `tests/test_build_macro_calendar.py`, including
  job-level idempotent-rerun, vanished-past-date-rejected-file-unchanged, missing-key, and
  release-name-mismatch scenarios, all asserting `capsys`-captured output never contains the
  sentinel key.
- Full suite: **201 tests pass** (161 pre-existing + 40 new), `ruff check .` clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: Capture real source fixtures and write the failing job test** - `8e8bb6a` (test)
2. **Task 2: Fetchers, pure parsers and the builder job** - `afa9b87` (feat)
3. **Task 3: Idempotency (D-03), validation and secret-leak hardening (D-02)** - `3f8bc8a` (test)

_No separate plan-metadata commit was requested ahead of this one; SUMMARY.md/STATE.md/ROADMAP.md
updates follow this one._

## Files Created/Modified

- `core/calendar.py` - Pure parsers/merge/validation: `parse_fomc_historical`,
  `parse_fomc_calendars`, `parse_fred_release_dates`, `merge_calendar`,
  `validate_macro_calendar`, `CALENDAR_COLUMNS`
- `core/data.py` - Added `fetch_text`, `fetch_fred_release_dates`, `fetch_fred_release_name`
  (local `import requests`, fail-loud, never leak the api_key)
- `core/config.py` - Added the CAL-01 settings block (`macro_calendar_path`,
  `calendar_start`, `calendar_first_release_by`, `fred_api_url`, `fred_api_key_env`,
  `fred_releases`, URL templates, `http_timeout_s`, `fomc_scheduled_per_year`,
  `monthly_releases_per_year`, `calendar_horizon_days`)
- `core/storage.py` - Added `load_macro_calendar`/`write_macro_calendar`, same
  `FileNotFoundError`-propagating contract as `load_prices`/`load_episodes`
- `jobs/build_macro_calendar.py` - New builder job: no CLI key arg, confirms FRED release
  names every run, tenacity-retried fetches, fail-loud without writing on any error
- `tests/test_calendar.py` - 29 tests: parser correctness against real fixtures,
  merge/validate behavior, secret-leak hardening, purity guard
- `tests/test_build_macro_calendar.py` - 6 tests: end-to-end success, idempotent rerun,
  vanished-past-date rejection, missing-key, release-name-mismatch
- `tests/fixtures/macro/*` - 5 real federalreserve.gov pages + 2 synthetic FRED JSON fixtures

## Decisions Made

- `"(notation vote)"` entries on the current calendars page (e.g. the Longer-Run Goals strategy
  statement vote) are excluded entirely from `parse_fomc_calendars`'s output -- they are not
  rate-decision meetings, and including them as either scheduled or unscheduled would push
  several years' FOMC counts above the `(7,8)` bound.
- `"(cancelled)"` meetings (2020's March 17-18) produce no row at all, distinct from
  `"(unscheduled)"` emergency meetings (2020's March 2 and March 15), which are real decisions
  and are stored with `scheduled=False`.
- `merge_calendar` does not attempt a field-level reconciliation between `existing` and
  `fresh`; because the job always re-fetches the complete `calendar_start..horizon` window on
  every run, the merged output is always `fresh` itself (deduped, sorted) -- `existing` only
  gates the D-03 missing-past-row check.

## Deviations from Plan

**None requiring a STOP.** The plan explicitly instructed: *"If the 2008/2020 fixtures show an
emergency action without such a label, STOP and record a deviation... do not invent a
hand-maintained override list."* Inspection of the real fixtures found every emergency/cancelled
action already carries an explicit parenthetical label (`"(unscheduled)"`, `"(cancelled)"`), so
no STOP was triggered and no hand-maintained override list was needed -- the general
parenthetical-annotation classification rule handles all observed cases.

One small addition beyond the plan's literal classification rule (which only names
`"conference call"`/`"unscheduled"`): the current calendars page also carries `"(notation
vote)"` annotations for non-meeting procedural votes, which are excluded from the output
entirely (not classified as scheduled or unscheduled, since they are not decision meetings at
all). This is a Rule 2 (auto-add missing critical functionality) addition -- without it, years
containing a notation vote would fail `validate_macro_calendar`'s FOMC per-year count check.
Documented above as a Decision; covered by `test_parse_fomc_calendars_min_year_and_unscheduled`
and the live-fixture count assertions.

## Issues Encountered

None. All three tasks' tests passed against the implementation on the first run with no bugs
requiring iteration; Task 3's tests in particular passed unmodified against Task 2's
implementation (`merge_calendar`'s "fresh always wins" design and `validate_macro_calendar`'s
check ordering already satisfied every D-03/D-02 behavior Task 3 specifies).

## User Setup Required

None for this plan. Per D-02, the FRED API key stays local-only and is never requested, read,
printed, or stored by this execution -- Jason runs the live job himself with his own key in plan
02-04 (`FRED_API_KEY=... python -m jobs.build_macro_calendar`).

## Next Phase Readiness

- `jobs/build_macro_calendar.py` is ready for 02-04's live local run: Jason sets `FRED_API_KEY`
  in his own shell and runs the job once to produce the real committed
  `data/macro_calendar.parquet`. No code changes should be needed -- the job was built and
  tested against the exact real HTML shapes it will parse live.
- `core/calendar.py`'s pure functions (`parse_fomc_historical`, `parse_fomc_calendars`,
  `parse_fred_release_dates`, `merge_calendar`, `validate_macro_calendar`) are independently
  unit-tested and importable for 02-05's episode-tagging join.
- No blockers for 02-04/02-05.

---
*Phase: 02-event-detection-macro-calendar*
*Completed: 2026-10-08*
