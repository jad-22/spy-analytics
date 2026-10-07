# Roadmap

Derived from `docs/SPEC.md` (Delivery plan, Pages, Event detection, News enrichment). The
spec's delivery-plan diagram did not survive export, so the phase contents and gates below
were rebuilt from the rest of the spec. Sizes are relative (S/M/L).

| Phase | Goal | Size | Status |
| --- | --- | --- | --- |
| 0 | Correct core engine and re-run the notebook | M | **Done** (2026-10-07) |
| 1 | MVP app: Overview + Strategy Lab on Streamlit Cloud | M | Next |
| 2 | Event detection (shock, gap, drawdown, rally) + macro calendar | M | Can overlap with 1 |
| 3 | News enrichment, one-off backfill, manual review | L | |
| 4 | Event Explorer, Event Study, Methodology, nightly automation | M | |

---

## Phase 0: Core rebuild (done)

- [x] `core/` package: data, indicators, signals, backtest, metrics, grid
- [x] Tests covering every notebook-audit fix (look-ahead, EMA span, equity, costs, legacy loop)
- [x] Acceptance check: 24-rule grid re-run on live data, findings in `docs/PHASE0_FINDINGS.md`
- [x] Fixed common-window off-by-one in `run_ma_grid`
- [x] CI workflow (`ruff` + `pytest`)

**Gate:** tests green, corrected conclusions written down. Met.

## Phase 1: MVP app

Goal: a public URL showing price context and an honest MA backtest, with no external calls at
runtime.

1. `core/storage.py`: cached readers for every `data/` file (prices first), plus `meta.json`.
2. `jobs/refresh_prices.py`: fetch, validate (row count, no gaps beyond holidays, Stooq vs
   yfinance check), write `data/prices.parquet` and `data/meta.json`.
3. `core/regimes.py` (or in `metrics.py`): drawdown series, regime shading (−5/−10/−20%),
   KPI calcs (YTD, distance from ATH, current drawdown, 20D realised vol).
4. `app/Home.py`, `app/components/sidebar.py` (date range, price basis), `charts.py`.
5. `app/pages/1_Overview.py`: price chart (line/candle), MA overlays, regime toggle, KPI strip.
6. `app/pages/2_Strategy_Lab.py`: rule picker, trend filter, cost slider, equity vs B&H,
   metrics table, short × long heatmap, rolling-start chart, in-sample / out-of-sample split.
7. `core/backtest.py` additions: IS/OOS split helper. Add a `Strategy` protocol in
   `signals.py` so new rules plug in without touching the page.
8. Stub `5_Methodology.py` with Phase 0 findings and the disclaimer.
9. `.streamlit/config.toml`, deploy to Streamlit Community Cloud, add URL to README.

**Gate:** the app is deployed, every chart reads only from `data/`, and the Strategy Lab
reproduces the `PHASE0_FINDINGS.md` numbers for the same inputs (covered by a test).

## Phase 2: Event detection

1. `core/events.py`: shock day (|log r| > 2.5 × lagged 60D σ), gap open (> 1.5%), drawdown
   episode (≥ 5%, ends at new high), rally episode (≥ 8% in 30 days); clustering within 3
   days; `anchor_date`; severity score; search windows. All thresholds in `config.py`.
2. `core/calendar.py` + `data/macro_calendar.parquet`: FOMC, CPI, payrolls since history start.
3. `jobs/detect_events.py` → `data/episodes.parquet` with `detector_version`.
4. Calibrate thresholds so the backfill is in the low hundreds of episodes; record in
   Methodology.

**Gate:** the episode count is in the target range, and known events (Aug 2015, Feb 2018,
Q4 2018, Mar 2020, 2022 bear) are all detected. A test asserts this.

## Phase 3: News enrichment and backfill

1. `core/news/schema.py` (pydantic `EventExplanation`), `base.py` (`NewsProvider`),
   `null.py`, `claude_search.py` (Claude API + web search tool, JSON-only prompt).
2. Validation: source dated in window → else `unexplained`; confidence < 0.5 or conflicts →
   `needs_review`. Store raw response, model ID and prompt version.
3. `jobs/enrich_events.py` with per-run episode cap and per-request search cap.
4. Check current model IDs and web-search pricing before the backfill; estimate cost.
5. Run the backfill, then review it with `jobs/review_events.py` → `data/event_overrides.json`.

**Gate:** every episode is `explained`, `unexplained` or reviewed, and nothing is
`needs_review` unless it has been explicitly hidden. Spend stays within the agreed budget.

## Phase 4: Explorer, Study, automation

1. `3_Event_Explorer.py`: markers by category/severity, `on_select="rerun"` detail panel,
   filterable table, "coincident, not causal" label.
2. `4_Event_Study.py`: average path −5 to +60 days by category, recovery-time distribution,
   events per year.
3. Complete `5_Methodology.py`: thresholds, sources, LLM caveats, last refresh.
4. `jobs/nightly.py` + `.github/workflows/nightly.yml`: weekday evenings UK time; refresh,
   detect, enrich new episodes, commit `data/`. API key only in Actions secrets.
5. README: screenshots, live link, "may take a moment to wake" note.

**Gate:** the nightly job has run unattended for a week, and the app has had a full review
for accessibility and copy.

---

## Open questions (from spec; decide before the phase noted)

- [ ] History start: 2010 (matches notebook) or 1993 (adds 2000 and 2008)? **Before Phase 2**:
      it changes episode count and backfill cost. It also changes the Phase 1 default range.
- [ ] Macro calendar: US-only, or add BoE/ECB? **Before Phase 2.**
- [ ] Public or private GitHub repo? **Before Phase 1 deploy.** Streamlit Community Cloud works
      with both.
