---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: ready_to_plan
last_updated: 2026-10-09T08:33:47.957Z
last_activity: 2026-10-08
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 11
  completed_plans: 11
  percent: 50
stopped_at: Phase 02 complete (5/5) — ready to discuss Phase 3
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-07)

**Core value:** Every number and every explanation on the page is honest and traceable — no
look-ahead, total-return prices and costs, event explanations cite in-window sources or say
"unexplained".
**Current focus:** Phase 3 — news enrichment, backfill & review

## Current Position

Phase: 3
Plan: Not started
Status: Ready to plan
Last activity: 2026-10-09

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 5
- Average duration: - min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 02 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 14min | 4 tasks | 22 files |
| Phase 01 P05 | 17m | 2 tasks | 9 files |
| Phase 01 P06 | 20min | 3 tasks | 3 files |
| Phase 02 P01 | 15min | 3 tasks | 8 files |
| Phase 02 P02 | 12min | 2 tasks | 4 files |
| Phase 02 P03 | 25min | 3 tasks | 11 files |
| Phase 02 P05 | 8min | 3 tasks | 9 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Phase 0: Corrected engine confirms 0/24 MA rules beat buy-and-hold (2010-2022, any basis/cost) — Strategy Lab must lead with this finding, not bury it.
- Roadmap: Phases 1 and 2 have no dependency and may be planned/executed in parallel; Phase 3 (LLM backfill, irreversible spend) is gated on Phase 2's episode-ID-stability replay test; Phase 4 needs real enriched data from Phase 3 before Event Explorer/Study are demo-worthy.
- [Phase 01]: Phase 1 Plan 01: tenacity.Retrying used as a callable (not @retry decorator) so fetch_with_retry calls the bare module-level fetch_yfinance name, letting tests monkeypatch it directly
- [Phase 01]: Phase 1 Plan 01: app/components/store.py functions read SETTINGS as a module-level global at call time (not a bound default), so tests can monkeypatch store.SETTINGS to point at a missing snapshot for the empty-state test
- [Phase 01]: D-09 resolved by measurement: naive heatmap_grid was 2.70s cold-sum (DEBOUNCE NEEDED); two numerically-neutral vectorisations (shared per-period MA computation, skipping unused summarise() ratios) brought it to 1.49s against the 2.0s threshold -- REACTIVE OK, no st.form debounce added
- [Phase 01]: Phase 1 (01-06): left core/config.py rewrite_tolerance_pct and core/validate.py unchanged after the live GitHub Actions nightly run reproduced the same D-13 volume-only rejection seen in 01-02's local repro (Yahoo revises most-recent-day volume post-close) -- tolerance change is a user decision, not an auto-fix
- [Phase 01]: D-13 gate exempts volume from the rewrite tolerance (user decision 2026-10-08): Yahoo revises latest-session volume post-close; OHLC + adj_close still guarded
- [Phase 02]: D-01 steepest-leg clustering confirmed empirically: 142 episodes on real 1993+ data, all seven DET-07 known episodes map to exactly one episode each, Feb 2018 and Q4 2018 on separate episode_ids
- [Phase 02]: closure_frontier combines three independent lower bounds (future shock/gap day, future rally lookback, live running-peak position) with a plain min(), not a settings-driven weighting
- [Phase 02]: closure_frontier's running-peak frontier candidate fires at any depth below peak, not only once a dip reaches drawdown_threshold, since a shallow dip could still deepen into a qualifying leg on the next appended row
- [Phase 02]: "(notation vote)" entries on the current fomccalendars.htm page are excluded entirely from parse_fomc_calendars (not a rate-decision meeting) -- keeps FOMC per-year counts within the (7,8) bound
- [Phase 02]: merge_calendar relies on the job always re-fetching the full calendar_start..horizon window each run, so fresh always wins; existing only gates the D-03 missing-past-row check
- [Phase 02]: A "(cancelled)" FOMC meeting (2020 March 17-18) produces no row at all, distinct from "(unscheduled)" emergency meetings which are stored as real scheduled=False decisions
- [Phase 02]: catalyst is scheduled iff scheduled_releases non-empty -- an unscheduled-only or empty window in [search_from, search_to] is always surprise (Mar 2020 emergency FOMC action never counts as a scheduled catalyst)
- [Phase 02]: DET-07 probe list (KNOWN_EPISODES) centralized in scripts/report_phase2.py as the single source of truth; tests/test_detect_events.py imports it instead of duplicating

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3: Model ID (`claude-haiku-5-5` in research STACK.md) and its pricing are unverified against official Anthropic docs — must confirm before scoping or running the backfill (see ROADMAP.md Phase 3, Success Criterion 1).
- Phase 1: Stooq fallback is confirmed broken (CAPTCHA-gated endpoint) — nightly price job should rely on yfinance + retries + last-good-snapshot, not a second scraped fallback.
- Phase 1: Verify `st.plotly_chart(on_select="rerun")` actually fires on the Strategy Lab heatmap (documented Streamlit gaps exist for imshow/heatmap selection); have a table-row fallback ready.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-10-08T23:30:34.948Z
Stopped at: Completed 02-05-PLAN.md
Resume file: None
