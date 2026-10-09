# Roadmap: SPY Market Lens

## Overview

Phase 0 (complete) rebuilt the notebook's backtest logic as a tested, honest `core/` engine
with no look-ahead. From here, the project ships in four phases: a deployed Overview + Strategy
Lab vertical slice reading only committed price data (Phase 1), a deterministic event detector
and US macro calendar that can run in parallel with Phase 1 (Phase 2), an LLM-driven news
enrichment pipeline and one-off historical backfill with manual review (Phase 3, gated on
Phase 2's stable episode IDs), and the Event Explorer/Event Study/Methodology pages plus full
nightly automation that ties refresh, detection and enrichment together (Phase 4). By the end,
every chart on the public app is backed only by committed `data/` files refreshed unattended
every weekday night.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation, Overview & Strategy Lab** - Deployed public app with price-only Overview and Strategy Lab pages, reading only committed data (completed 2026-10-08)
- [x] **Phase 2: Event Detection & Macro Calendar** - Deterministic, replay-stable episode detection and a sourced US macro calendar (runs in parallel with Phase 1) (completed 2026-10-08)
- [ ] **Phase 3: News Enrichment, Backfill & Review** - Sourced, validated LLM explanations for every episode since 1993, within budget, with manual review and overrides
- [ ] **Phase 4: Event Explorer, Event Study, Methodology & Nightly Automation** - Full event UI, aggregate event-study stats, methodology page, and unattended nightly pipeline

## Phase Details

### Phase 1: Foundation, Overview & Strategy Lab

**Goal**: A public URL shows SPY price context and an honest MA backtest, with every page reading only committed `data/` files and no runtime network calls.
**Mode:** mvp
**Depends on**: Phase 0 (complete — corrected `core/` engine)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, OVER-01, OVER-02, OVER-03, OVER-04, OVER-05, OVER-06, LAB-01, LAB-02, LAB-03, LAB-04, LAB-05, LAB-06, LAB-07, LAB-08, LAB-09, LAB-10, OPS-01, OPS-05
**Success Criteria** (what must be TRUE):

  1. Visitor can open the public Streamlit URL and see the Overview page: a price chart (line/candle) with a chosen date range, SMA/EMA overlays, shaded drawdown regimes (−5/−10/−20%), a KPI strip (YTD return, distance from ATH, current drawdown, 20-day realised vol), a largest-drawdowns table, and a total-return/price-only toggle.
  2. Visitor can configure a Strategy Lab rule (short/long MA type and period, optional 200D trend filter, trading cost, start/end dates) and see the strategy equity curve against buy-and-hold with trades marked, a metrics table (CAGR, max drawdown, Sharpe, Sortino, Calmar, time in market, trades), a short × long heatmap with an overfitting caption, a rolling-start robustness chart, an in-sample/out-of-sample split, and a CAGR-vs-max-drawdown scatter across the grid.
  3. The Strategy Lab's default view states "0 of 24 rules beat buy-and-hold" in plain language, matching the Phase 0 findings.
  4. A nightly GitHub Actions job refreshes `data/prices.parquet` and `data/meta.json` (validated, with retries and no silent gap/shrink), commits without triggering a CI loop, and every app page reads through one cached storage module with zero network calls.
  5. New strategy rule types can be added through a `Strategy` interface without changing the Strategy Lab page.

**Plans:** 6/6 plans complete

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Walking skeleton: cached storage module, st.navigation app, Overview price line, refresh job with 1993 backfill + meta.json (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Nightly safety: NYSE calendar, D-13 validation gate, nightly.yml, ci.yml paths-ignore (wave 2)
- [x] 01-03-PLAN.md — Overview complete: KPIs, MA overlays, candlestick, drawdown regimes, drawdown table (wave 2)
- [x] 01-04-PLAN.md — Strategy Lab slice: Strategy protocol, Sortino/Calmar, live "N of 24" headline, equity vs B&H, metrics, Phase 0 regression test (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-05-PLAN.md — Strategy Lab robustness: heatmap, scatter, rolling-start, IS/OOS, D-09 profiling decision (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-06-PLAN.md — Ship: docs, public repo + Streamlit Cloud deploy (checkpoint), live nightly/CI-loop verification (wave 4)

**UI hint**: yes

### Phase 2: Event Detection & Macro Calendar

**Goal**: The system deterministically detects every major SPY shock, gap, drawdown and rally episode since 1993 and tags each with any scheduled US macro catalyst inside its window.
**Mode:** mvp
**Depends on**: Phase 0 (prices); independent of Phase 1 — can run in parallel
**Requirements**: DET-01, DET-02, DET-03, DET-04, DET-05, DET-06, DET-07, CAL-01, CAL-02
**Success Criteria** (what must be TRUE):

  1. Running the detector over price history flags shock days (|log return| > 2.5 × lagged 60-day σ), gap opens (> 1.5%), drawdown episodes (≥ 5%, ending at a new high) and rally episodes (≥ 8% within 30 trading days), merging flags within 3 trading days into one episode with a deterministic `anchor_date`, severity score and search window.
  2. A replay test proves episode IDs are stable: detecting on data through date A, then through a later date B, never changes a previously closed episode's ID or boundaries.
  3. All seven known historical episodes (2000-02, 2008, Aug 2015, Feb 2018, Q4 2018, Mar 2020, 2022) are detected, asserted by a passing test.
  4. All detection thresholds live in config (not hard-coded), and the 1993+ backfill produces an episode count in the low hundreds.
  5. `data/macro_calendar.parquet` lists FOMC decision, CPI and payrolls release dates from 1993 with a source URL each, and every detected episode is tagged with any such release inside its window (scheduled vs surprise).

**Plans:** 5/5 plans complete
Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Detection slice: core/events.py (shock/gap/drawdown/rally, D-01 steepest-leg clustering), jobs/detect_events.py, committed episodes.parquet, DET-06 count + DET-07 known-episode tests (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Replay stability: closed/open status via closure frontier, real-data replay test at six cutoffs, no-literal/purity guards (wave 2)
- [x] 02-03-PLAN.md — Macro calendar builder offline: Fed/FRED fetchers in core/data.py, pure parsers in core/calendar.py, idempotent job (D-03), key hygiene (D-02), real-page fixtures (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-04-PLAN.md — Live local calendar build with Jason's FRED key (checkpoint), A1 release-id confirmation, committed macro_calendar.parquet + CI data test (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 02-05-PLAN.md — CAL-02 tagging (scheduled vs surprise) wired into detect job, final episodes.parquet, script-generated docs/PHASE2_CALIBRATION.md (wave 4)

### Phase 3: News Enrichment, Backfill & Review

**Goal**: Every detected episode since 1993 has a sourced, schema-validated explanation — or is honestly marked `unexplained`/`needs_review` — produced within the $25 budget, with Jason able to review and override results locally.
**Mode:** mvp
**Depends on**: Phase 2 (stable episode IDs)
**Requirements**: NEWS-01, NEWS-02, NEWS-03, NEWS-04, NEWS-05, NEWS-06, NEWS-07, NEWS-08, REV-01, REV-02, OPS-03
**Success Criteria** (what must be TRUE):

  1. The current Haiku-tier (or chosen) Claude model ID and its official per-token pricing are verified against Anthropic's own docs before any backfill spend, and the budget estimate is updated against the verified numbers.
  2. For any episode, the `NewsProvider` interface (a `NullProvider` for tests/offline, a `ClaudeSearchProvider` using the Claude API + web search for real runs) returns a pydantic-validated record — headline, summary, category, region, scheduled flag, drivers, sources (parsed from the web search tool's structured results, never model prose), confidence — and episodes without a source dated inside the window are stored as `unexplained`.
  3. Episodes with confidence < 0.5 or conflicting sources are marked `needs_review`; re-running enrichment only sends episodes without a current record (incremental, idempotent); each record stores the raw response, model ID, prompt version and enriched-at time.
  4. The one-off backfill covers every detected episode since 1993, stays within the $25 cap enforced by hard per-run episode and per-request search caps with spend logged, and the Anthropic API key exists only as a GitHub Actions secret (never in Streamlit Cloud or the repo).
  5. Jason can accept, edit or reject any event record using a local-only review tool; his overrides live in `data/event_overrides.json`, win over model output at read time, and are never merged back into `events.json` on disk.

**Plans**: 7 plans
Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Offline enrichment slice: config (D-01 prices/caps), pydantic schema + status rules, NewsProvider/NullProvider, incremental job

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02-PLAN.md — ClaudeSearchProvider (web search + structured output), source cross-validation, sanitized raw response, spend ledger, budget guard, Sonnet escalation
- [x] 03-03-PLAN.md — Local review CLI (accept/edit/reject) and read-time override merge

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-04-PLAN.md — Script-generated budget report vs verified pricing, CLAUDE.md correction, backfill.yml (key as secret), enrichment report, data-integrity tests

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 03-05-PLAN.md — Provision secret, paid 9-episode spike, go/adjust/abort decision

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 03-06-PLAN.md — Full 1993+ backfill via workflow, coverage + spend verification, escalation decision

**Wave 6** *(blocked on Wave 5 completion)*

- [ ] 03-07-PLAN.md — Manual review by Jason, gate tests, roadmap close-out

### Phase 4: Event Explorer, Event Study, Methodology & Nightly Automation

**Goal**: Visitors can explore every enriched event on an interactive chart, see aggregate event-study statistics, read the full methodology, and the whole pipeline refreshes itself nightly without Jason's attention.
**Mode:** mvp
**Depends on**: Phase 1 (app skeleton), Phase 2 (episodes), Phase 3 (enriched events)
**Requirements**: EXPL-01, EXPL-02, EXPL-03, EXPL-04, EXPL-05, EXPL-06, STUDY-01, STUDY-02, STUDY-03, STUDY-04, METH-01, METH-02, METH-03, OPS-02, OPS-04
**Success Criteria** (what must be TRUE):

  1. Visitor sees a price chart with event markers coloured by category and sized by severity, styled by status (explained/needs-review/unexplained), with drawdown episodes shaded; clicking a marker or table row opens a detail panel showing dates, day/episode move, headline, summary, category, region, scheduled flag, dated source links, confidence, +1D/+5D/+20D forward returns and days to recover; events are filterable by category, direction, year and confidence; every panel carries a "coincident, not causal" label.
  2. Visitor sees the average cumulative return path from day −5 to +60 by category, a recovery-time distribution by category, and event counts per year by category, with selectable categories and horizon.
  3. The Methodology page explains definitions, thresholds and data sources; presents the corrected Phase 0 findings from `docs/PHASE0_FINDINGS.md` (the hand-picked "oracle" trades mentioned only as a lesson); states LLM caveats and the not-investment-advice disclaimer; and shows the last refresh time.
  4. A nightly GitHub Actions job (weekday evenings UK time) refreshes prices, detects new episodes, enriches only the new ones, and commits `data/` end-to-end without triggering a CI/redeploy loop; failures are visible (failed run, notification) and the workflow stays active past GitHub's 60-day inactivity auto-disable.

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phase 1 and Phase 2 may execute in parallel (no dependency between them). Phase 3 requires
Phase 2 complete. Phase 4 requires Phases 1, 2 and 3 complete.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Core engine rebuild | - | Complete | 2026-10-07 |
| 1. Foundation, Overview & Strategy Lab | 6/6 | Complete   | 2026-10-08 |
| 2. Event Detection & Macro Calendar | 5/5 | Complete    | 2026-10-09 |
| 3. News Enrichment, Backfill & Review | 4/7 | In Progress|  |
| 4. Event Explorer, Event Study, Methodology & Nightly Automation | 0/TBD | Not started | - |
