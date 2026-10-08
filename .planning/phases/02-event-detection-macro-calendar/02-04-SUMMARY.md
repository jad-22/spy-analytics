---
phase: 02-event-detection-macro-calendar
plan: 04
subsystem: data
tags: [fred-api, federalreserve-gov, parquet, live-run]

requires:
  - phase: 02-event-detection-macro-calendar
    plan: 03
    provides: offline-tested jobs/build_macro_calendar.py
affects: [02-05-episode-calendar-tagging, phase-04-nightly]
provides:
  - data/macro_calendar.parquet (1138 rows, FOMC/CPI/payrolls 1993..2027)
  - tests/test_macro_calendar_data.py (committed-data checks, run in CI offline)
  - Settings.fred_non_release_dates, fred_double_release_months, fomc_non_decision_meetings
  - validate_macro_calendar one-release-per-month guard
  - tests/fixtures/macro/fred_live_release_dates.json (full live FRED date lists, dates only)

key-files:
  created:
    - data/macro_calendar.parquet
    - tests/test_macro_calendar_data.py
    - tests/fixtures/macro/fred_live_release_dates.json
    - tests/fixtures/macro/fomchistorical2003.htm
  modified:
    - core/calendar.py
    - core/config.py
    - jobs/build_macro_calendar.py
    - tests/test_calendar.py
    - tests/test_build_macro_calendar.py

key-decisions:
  - "FRED non-print dates are an explicit, commented config list, not a positional rule: the 'first date per month' rule (423a536) dropped the real January CPI print in 2005-2024 because BLS's seasonal-factor update precedes it"
  - "Unlisted second FRED date in a month fails the build loudly (keeps last calendar) rather than being tagged as a scheduled print; 1996-02 is the only allowed double (shutdown backlog)"
  - "2003-09-15 FOMC session (no policy statement) excluded via Settings.fomc_non_decision_meetings"
  - "FOMC calendars parser no longer requires a Statement link, so future meetings (2026-10-28, 2026-12-09, all of 2027) are in the forward calendar"

requirements-completed: [CAL-01]

duration: ~1 day elapsed (three live runs by Jason)
completed: 2026-10-09
---

# Phase 02 Plan 04: Live macro calendar build Summary

**CAL-01's committed artifact: data/macro_calendar.parquet, 1138 rows built locally by Jason with his own FRED key, validated in CI offline.**

## Live-run results

- RESEARCH A1 confirmed live: `FRED release_id 10 = Consumer Price Index`, `FRED release_id 50 = Employment Situation`.
- Final run: `CPI: dropped 20 listed non-print date(s)`, `payrolls: dropped 8 listed non-print date(s)`, `wrote 1138 rows`.
- Idempotency: the committed file is identical (`assert_frame_equal`) to an offline rebuild from the same sources (cached public Fed pages + the live FRED date dump), whose second run printed `added 0 / removed 0`. Jason pasted only the first live run's output.

| release | scheduled | count | first | last |
|---|---|---|---|---|
| CPI | True | 407 | 1993-01-15 | 2026-12-10 |
| FOMC | False | 45 | 1993-01-06 | 2020-03-15 |
| FOMC | True | 279 | 1993-02-03 | 2027-12-08 |
| payrolls | True | 407 | 1993-01-08 | 2026-12-04 |

## Deviations from Plan

The plan's failure handling ("unseen page shape -> fixture + failing test + fix, rerun") was followed three times:

1. **[Rule 1 - Bug] FRED lists revision days as release dates.** Run 1 failed `2000: 14 CPI releases`. A first fix (423a536, keep earliest date per month) was wrong: run 2 showed it dropped the real January CPI print in 2005-2024 (BLS seasonal-factor update comes 2-6 days earlier). Replaced (8d8c4fa) by an explicit `fred_non_release_dates` list (28 dates, commented by group) plus a one-release-per-month guard in `validate_macro_calendar`. Tests use the full live date lists as a fixture.
2. **[Rule 1 - Bug] 2003 had 9 scheduled FOMC meetings.** The Fed's 2003 page lists a 2003-09-15 "Meeting" with no policy statement, the day before the 09-16 decision. Excluded via `fomc_non_decision_meetings` (bf6dda3), real page added as a fixture.
3. **[Rule 2 - Missing] Future FOMC meetings were dropped.** Found by auditing every public Fed page offline: `parse_fomc_calendars` required a "Statement" link, losing 2026-10-28, 2026-12-09 and all of 2027. Fixed in bf6dda3 with a test that prose dates still never match.

These fixes were made inline by the orchestrator, not an executor agent.

## Known follow-up

- The nightly rebuild (Phase 4) will fail loudly the first time FRED adds an unlisted non-print date (likely BLS's February 2027 seasonal-factor update). The fix is to verify it and append it to `fred_non_release_dates`; the last good calendar stays in place meanwhile.

## Commits

- c79900f test(02-04): committed-data test (pre-flight)
- 423a536 fix(02-04): first-per-month rule (superseded)
- bf6dda3 fix(02-04): future FOMC meetings, 2003-09-15 exclusion
- 8d8c4fa fix(02-04): explicit FRED non-print list + one-per-month guard
- 47c551c data(02-04): live macro calendar

## Self-Check: PASSED

- data/macro_calendar.parquet exists; tests/test_macro_calendar_data.py runs (7 passed, not skipped)
- Full suite 217 passed; ruff clean
- No .env or key in any commit (`git diff --cached` checked for `api_key=` before each commit)
