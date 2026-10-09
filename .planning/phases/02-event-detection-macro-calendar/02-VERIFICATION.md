---
phase: 02-event-detection-macro-calendar
verified: 2026-10-09T08:32:14Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 2: Event Detection & Macro Calendar Verification Report

**Phase Goal:** The system deterministically detects every major SPY shock, gap, drawdown and rally episode since 1993 and tags each with any scheduled US macro catalyst inside its window.
**Verified:** 2026-10-09
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria 1-5)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Detector flags shock days (\|log return\| > 2.5×lagged 60D σ), gap opens (>1.5%), drawdown episodes (≥5%, steepest leg), rally episodes (≥8%/30d), merges flags within 3 trading days into one episode with deterministic `anchor_date`, severity and search window | VERIFIED | `core/events.py` implements `shock_zscores`, `gap_days`, `drawdown_legs`, `rally_legs`, `cluster_legs`, `detect` exactly per D-01 steepest-leg clustering. `tests/test_events.py` (13+ hand-checkable unit tests: sigma lag, gap boundary, drawdown/rally leg math, trading-day-vs-calendar-day clustering, D-01 non-absorption, trigger precedence, severity formula) and `tests/test_detect_events.py` (schema/e2e on real data) all pass. Ran directly: `.venv\python.exe -m pytest tests/test_events.py tests/test_detect_events.py -q` → all pass. |
| 2 | Replay test proves episode IDs are stable: detecting through date A then later date B never changes a previously closed episode's ID or boundaries | VERIFIED | `core/events.py::closure_frontier` (02-02) plus the CR-01 code-review fix (commit `cd0d603`, `Leg.reach_pos` carries the rally merged-span end into the closure test) resolve the one genuine blocker found by code review (a closed rally episode could silently reopen and change `end_date`/`move_pct`/`severity`/`status` on append). `tests/test_episode_replay.py` (9+ tests incl. the CR-01 regression test `test_closed_rally_survives_append_that_extends_its_merged_span`, a 5-seed random-walk prefix-replay test with every detector enabled `test_closed_episodes_stable_at_every_prefix_with_all_detectors`, and the original 6-cutoff real-data replay test) all pass. Ran directly: all green. |
| 3 | All seven known historical episodes (2000-02, 2008, Aug 2015, Feb 2018, Q4 2018, Mar 2020, 2022) are detected, asserted by a passing test | VERIFIED | Independently re-queried the committed `data/episodes.parquet` outside of any test: every one of the 7 DET-07 probe dates falls inside exactly one episode (`2000-04-14_drawdown`, `2008-10-13_drawdown`, `2015-08-24_drawdown`, `2018-02-05_drawdown`, `2018-12-26_drawdown`, `2020-03-16_drawdown`, `2022-11-10_drawdown`), Feb 2018 and Q4 2018 land on distinct episode_ids, and `tests/test_detect_events.py::test_known_episodes_detected`/`test_feb_and_q4_2018_are_separate` pass. |
| 4 | All detection thresholds live in config (not hard-coded); 1993+ backfill produces an episode count in the low hundreds | VERIFIED | `core/config.py` `Settings` carries every DET threshold with rationale comments; `tests/test_events.py::test_events_module_has_no_numeric_literals` (AST scan, only 0/1 allowed) and `test_events_module_is_pure` pass. Independently counted the committed artifact: `data/episodes.parquet` has 142 rows (within `SETTINGS.episode_count_bounds = (100, 300)`), all `status == "closed"`. `docs/PHASE2_CALIBRATION.md` is script-generated (`scripts/report_phase2.py`) and byte-stable on rerun. |
| 5 | `data/macro_calendar.parquet` lists FOMC/CPI/payrolls dates from 1993 with a source URL each; every episode is tagged scheduled vs surprise | VERIFIED | Independently loaded `data/macro_calendar.parquet`: 1138 rows, columns `date, release, release_type, scheduled, source_url`, CPI/payrolls from 1993-01/1993-01, FOMC scheduled from 1993-02-03, every row's `source_url` starts `https://`. `data/episodes.parquet` carries `scheduled_releases`/`unscheduled_releases`/`catalyst` (73 scheduled / 69 surprise); directly confirmed the Mar 2020 episode (`2020-03-16_drawdown`) lists `unscheduled_releases=["FOMC 2020-03-15"]`, `scheduled_releases=[]`, `catalyst="surprise"` — the emergency Sunday rate cut correctly never counts as a scheduled catalyst (RESEARCH Pitfall 2 honored). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `core/events.py` | Pure detector: log_returns, shock_zscores, shock_days, gap_days, drawdown_legs, rally_legs, cluster_legs, closure_frontier, detect | VERIFIED | Present; AST purity test confirms no network/core.data/core.storage import; no numeric literals other than 0/1 |
| `jobs/detect_events.py` | I/O job: prices → total-return → detect → tag_episodes → episodes.parquet; fails loud, atomic write | VERIFIED | `--calendar-path` wired; two independent `FileNotFoundError` catches (prices, calendar); `_write_episodes` loads meta before writing, rejects empty frames, writes via `os.replace` (WR-04 fix, commit `0cc85d1`); `check_calendar_coverage` fails the job if the calendar ends before any episode's search window (WR-02 fix, commit `7eed15d`) |
| `core/calendar.py` | Pure parsers + merge + validate + tag_episodes | VERIFIED | `parse_fomc_historical`, `parse_fomc_calendars`, `parse_fred_release_dates`, `merge_calendar`, `validate_macro_calendar`, `check_calendar_coverage`, `tag_episodes`, `CALENDAR_COLUMNS`, `TAG_COLUMNS` all present and tested |
| `core/data.py` (extended) | FRED/Fed network fetchers, key never leaked | VERIFIED | `fetch_text`, `fetch_fred_release_dates`, `fetch_fred_release_name`; no `raise_for_status`/`resp.url` in FRED functions; no `--api-key` CLI arg in the job; grep for the test sentinel key across `core`/`jobs` is empty |
| `jobs/build_macro_calendar.py` | Idempotent (D-03), local-key-only (D-02) builder | VERIFIED | Key read only from `FRED_API_KEY` env var; `--accept-history-change` escape hatch added (WR-03 fix, commit `e5829a0`) |
| `data/episodes.parquet` | Committed 1993+ backfill, final (status + tags) | VERIFIED | 142 rows, all `closed`, 73 scheduled/69 surprise, schema matches `EPISODE_COLUMNS` + `TAG_COLUMNS` |
| `data/macro_calendar.parquet` | Committed 1993+ FOMC/CPI/payrolls calendar | VERIFIED | 1138 rows, built live by Jason with his own FRED key (02-04); every `source_url` is `https://`, no key material |
| `docs/PHASE2_CALIBRATION.md` | Script-generated calibration record | VERIFIED | Generated by `scripts/report_phase2.py`; header states "do not hand-edit"; confirmed byte-stable on rerun per 02-05 SUMMARY |
| `tests/test_events.py`, `tests/test_detect_events.py`, `tests/test_episode_replay.py`, `tests/test_calendar.py`, `tests/test_build_macro_calendar.py`, `tests/test_macro_calendar_data.py` | Full coverage of DET/CAL rules | VERIFIED | All six files collected and passing: 127/127 in a scoped run; 252/252 in the full repo suite |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `jobs/detect_events.py` | `core/events.py::detect` | `detect(prices_tr, SETTINGS)` | WIRED | Confirmed in source and by passing e2e test |
| `jobs/detect_events.py` | `core/calendar.py::tag_episodes`/`check_calendar_coverage` | pipeline call before write | WIRED | `episodes = tag_episodes(detect(...), calendar)`; coverage check precedes write |
| `core/events.py::detect` | `core/events.py::closure_frontier` | `status` column | WIRED | `frontier = closure_frontier(close, settings)`; CR-01-fixed `reach_pos` logic confirmed in source |
| `jobs/build_macro_calendar.py` | `core/data.py` fetchers | tenacity-retried, monkeypatchable module-level names | WIRED | Confirmed in source; offline tests mock these names |
| `jobs/build_macro_calendar.py` | `os.environ` | `SETTINGS.fred_api_key_env` lookup only | WIRED | No CLI key argument; confirmed by grep |

### Data-Flow Trace (Level 4)

Not applicable in the UI sense (this phase produces no rendered page — "no UI in this phase" per `02-CONTEXT.md`). Instead, the equivalent trace is artifact-to-artifact: `data/prices.parquet` → `core.events.detect` → `data/episodes.parquet`, and `federalreserve.gov`/FRED → `core.calendar` parsers → `data/macro_calendar.parquet` → `tag_episodes` → `data/episodes.parquet`. Both artifacts were independently re-read from disk (not from SUMMARY claims) and contain real, non-empty, non-static computed data (142 episodes with varied triggers/severities; 1138 calendar rows spanning 1993–2027) — FLOWING.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `.venv\python.exe -m pytest -q` | 252 passed | PASS |
| Ruff clean | `.venv\python.exe -m ruff check .` | All checks passed | PASS |
| Episode count in bounds | load `data/episodes.parquet`, `len(d)` | 142 (within 100–300) | PASS |
| All 7 DET-07 probes resolve to exactly one episode each | re-queried directly against committed parquet | 7/7 matched, Feb/Q4 2018 distinct | PASS |
| Mar 2020 tagged surprise with unscheduled FOMC listed | re-queried directly against committed parquet | confirmed | PASS |
| No FRED key leakage in git history | `git log -p` grep for `api_key=` across calendar/data/job files | only placeholder doc strings (`FRED_API_KEY=...`), no real key | PASS |
| CR-01 fix present and tested | grep `reach_pos`/`closure_frontier` in `core/events.py`; regression test present | confirmed in source and `tests/test_episode_replay.py` | PASS |

### Probe Execution

Not applicable — this phase has no `scripts/*/tests/probe-*.sh` convention and none is referenced by any PLAN/SUMMARY for Phase 2. Verification was instead performed via the full pytest suite plus direct, independent artifact re-queries (above), which supersede the probe-execution step's intent (run real code in-process, don't trust narration).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| DET-01 | 02-01 | Shock days (\|log return\| > 2.5×lagged 60D σ) | SATISFIED | `shock_zscores`/`shock_days`, tested |
| DET-02 | 02-01 | Gap opens (>1.5%) | SATISFIED | `gap_days`, tested |
| DET-03 | 02-01 | Drawdown (≥5%) / rally (≥8%/30d) episodes | SATISFIED | `drawdown_legs`/`rally_legs`, tested |
| DET-04 | 02-01 | Merge within 3 days, anchor_date, severity, search window | SATISFIED | `cluster_legs`/`detect`, tested |
| DET-05 | 02-02 | Deterministic, replay-stable episode IDs | SATISFIED | `closure_frontier` + CR-01 fix + 6-cutoff and 5-seed replay tests |
| DET-06 | 02-01/02-02/02-05 | Thresholds in config; backfill in low hundreds | SATISFIED | AST no-literal test; 142 episodes; `docs/PHASE2_CALIBRATION.md` |
| DET-07 | 02-01 | All 7 known episodes detected, asserted by test | SATISFIED | Re-verified directly against committed data |
| CAL-01 | 02-03/02-04 | `data/macro_calendar.parquet` FOMC/CPI/payrolls since 1993, sourced | SATISFIED | 1138 rows, verified directly, built live with Jason's own key |
| CAL-02 | 02-05 | Episodes tagged scheduled vs surprise | SATISFIED | `tag_episodes`, verified directly incl. Mar 2020 case |

No orphaned requirements: all nine Phase 2 requirement IDs (DET-01..07, CAL-01, CAL-02) in `.planning/REQUIREMENTS.md`'s traceability table are claimed by at least one plan's frontmatter, and every ID is independently verified above.

### Anti-Patterns Found

None. Scanned every file touched by Phase 2 (`core/events.py`, `core/calendar.py`, `core/config.py`, `core/storage.py`, `core/data.py`, `jobs/detect_events.py`, `jobs/build_macro_calendar.py`, `scripts/report_phase2.py`) for `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`/"not yet implemented"/"coming soon" — zero matches.

**Deferred (info-level, documented, non-blocking):** `02-REVIEW.md`'s IN-01 (zero-sigma `inf` z-score edge case), IN-02 (narrow exception catch in `detect_events`), IN-03 (gap leg stores close-to-close `move`, currently unused), IN-06 (test skip/fail policy inconsistency for a missing committed calendar). `02-REVIEW-FIX.md` explicitly defers these as not affecting committed data or the DET-05 contract — confirmed independently: none of them touch the paths that produce the committed `data/episodes.parquet`/`data/macro_calendar.parquet` values checked above.

**Known forward-looking note (not a Phase 2 gap):** `02-04-SUMMARY.md` documents that the nightly rebuild (Phase 4 work) will fail loudly the first time FRED adds an unlisted non-print date (e.g. a 2027 BLS seasonal-factor update) — by design (fail loud, keep last calendar), and explicitly scoped as Phase 4's problem, not Phase 2's.

### Human Verification Required

None. This phase produces no UI (`02-CONTEXT.md`: "No UI in this phase"). The one human-in-the-loop checkpoint (`02-04` Task 2 — Jason running `jobs.build_macro_calendar` locally with his own FRED key) was already executed and its output recorded in `02-04-SUMMARY.md` (RESEARCH A1 release-name confirmation, idempotent `added 0/removed 0`), and the resulting artifact and its offline validation were independently re-verified above from the committed files.

### Gaps Summary

No gaps. All 5 ROADMAP success criteria are independently verified against the committed codebase and data artifacts (not SUMMARY narration alone): the detector implements all four rules with config-driven thresholds and steepest-leg clustering; the DET-05 replay-stability contract — including the one genuine blocker found by code review (CR-01, a closed rally episode silently reopening) — is fixed in source and covered by a dedicated regression test plus a 5-seed randomized prefix-replay test; all seven known historical episodes are present as single, correctly separated episodes; the episode count (142) sits inside the DET-06 bound; and the macro calendar is a real, sourced, 1138-row artifact correctly distinguishing scheduled FOMC meetings from unscheduled emergency actions, wired into every episode's `catalyst` tag. The full test suite (252 tests) passes and ruff is clean. All four code-review warnings (WR-01..04) and the one critical finding (CR-01) from `02-REVIEW.md` are fixed in source with accompanying tests, confirmed directly in this verification pass rather than taken on SUMMARY claim alone.

---

*Verified: 2026-10-09*
*Verifier: Claude (gsd-verifier)*
