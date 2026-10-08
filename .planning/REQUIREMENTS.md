# Requirements: SPY Market Lens

**Defined:** 2026-10-07
**Core Value:** Every number and every explanation on the page is honest and traceable: no look-ahead, total-return prices and costs, and event explanations that cite sources dated inside the move's window or say "unexplained".

## v1 Requirements

### Data & Storage

- [x] **DATA-01**: The price job writes SPY daily OHLCV and adjusted close from 1993-01-29 to the latest trading day to `data/prices.parquet`
- [x] **DATA-02**: The price job pins yfinance `auto_adjust=False` and flat columns, retries on failure, and on final failure exits non-zero, leaving the last good snapshot untouched
- [x] **DATA-03**: The price job validates the snapshot before writing (no non-holiday gaps, no history rewritten beyond tolerance, row count never shrinks)
- [x] **DATA-04**: `data/meta.json` records last refresh time, last trading day, row counts and detector version
- [x] **DATA-05**: The app reads every `data/` file through one cached storage module, and no page makes a network call

### Overview

- [x] **OVER-01**: Visitor can view SPY price as a line or candlestick chart over a chosen date range (sidebar)
- [x] **OVER-02**: Visitor can toggle SMA/EMA overlays on the price chart
- [x] **OVER-03**: Visitor can toggle shaded drawdown regimes (−5%, −10%, −20%)
- [x] **OVER-04**: Visitor sees a KPI strip: YTD return, distance from all-time high, current drawdown, 20-day realised volatility
- [x] **OVER-05**: Visitor sees a table of the largest drawdowns (peak, trough, recovery date, depth, days underwater)
- [x] **OVER-06**: Visitor can switch between total-return and price-only series (sidebar)

### Strategy Lab

- [x] **LAB-01**: Visitor can pick a rule: short MA type and period, long MA type and period, optional 200D trend filter
- [x] **LAB-02**: Visitor can set trading cost (bps) and start/end dates
- [x] **LAB-03**: Visitor sees the strategy equity curve against buy-and-hold, with trades marked
- [x] **LAB-04**: Visitor sees a metrics table: CAGR, max drawdown, Sharpe, Sortino, Calmar, time in market, trades, for strategy and B&H
- [x] **LAB-05**: Visitor sees a short × long heatmap of excess return across the rule grid, with an overfitting caption (look for plateaus, not spikes)
- [x] **LAB-06**: Visitor sees a rolling-start robustness chart of excess return by start year
- [x] **LAB-07**: Visitor can set a split date and see in-sample vs out-of-sample metrics side by side
- [x] **LAB-08**: Visitor sees a CAGR vs max-drawdown scatter of all grid rules plus buy-and-hold
- [x] **LAB-09**: The default view leads with the Phase 0 headline ("0 of 24 rules beat buy-and-hold") in plain language
- [x] **LAB-10**: New rule types plug in through a `Strategy` interface without changes to the page

### Event Detection

- [x] **DET-01**: The detector flags shock days (|log return| > 2.5 × 60-day σ lagged one day)
- [x] **DET-02**: The detector flags gap opens (|open / previous close − 1| > 1.5%)
- [x] **DET-03**: The detector finds drawdown episodes (peak-to-trough ≥ 5% on closes, ending at a new high) and rally episodes (trough-to-peak ≥ 8% within 30 trading days)
- [x] **DET-04**: Flagged days within 3 trading days merge into one episode with an `anchor_date`, a severity score and a search window
- [ ] **DET-05**: Episode IDs are deterministic and stable across nightly re-runs (a replay test proves that appending data never changes a closed episode)
- [x] **DET-06**: All thresholds live in config, and calibration keeps the 1993+ backfill in the low hundreds of episodes
- [x] **DET-07**: Known episodes (2000–02, 2008, Aug 2015, Feb 2018, Q4 2018, Mar 2020, 2022) are detected, and a test asserts it

### Macro Calendar

- [ ] **CAL-01**: `data/macro_calendar.parquet` lists FOMC decision, CPI and payrolls release dates from 1993, each with a source URL
- [ ] **CAL-02**: Each episode is tagged with any scheduled releases inside its window (scheduled vs surprise)

### News Enrichment

- [ ] **NEWS-01**: The `NewsProvider` interface has a `NullProvider` (tests/offline) and a `ClaudeSearchProvider` (Claude API + web search)
- [ ] **NEWS-02**: Each explanation is validated against a pydantic schema (headline, summary, category, region, scheduled, drivers, sources, confidence)
- [ ] **NEWS-03**: Sources come from the web search tool's structured results (never model prose). Without one source dated inside the window, the episode is stored as `unexplained`
- [ ] **NEWS-04**: Confidence < 0.5 or conflicting sources produce `needs_review`
- [ ] **NEWS-05**: Each record stores the raw response, model ID, prompt version and enriched-at time
- [ ] **NEWS-06**: Enrichment is incremental and idempotent: only episodes without a current record are sent
- [ ] **NEWS-07**: Hard caps on episodes per run and searches per request, with total backfill spend ≤ $25; model ID and pricing verified against official docs before the run
- [ ] **NEWS-08**: The one-off backfill covers every detected episode since 1993

### Review & Curation

- [ ] **REV-01**: Jason can accept, edit or reject event records with a local-only review tool
- [ ] **REV-02**: Overrides live in `data/event_overrides.json` and win over model output at read time (never merged into `events.json` on disk)

### Event Explorer

- [ ] **EXPL-01**: Visitor sees a price chart with event markers coloured by category and sized by severity, and drawdown episodes shaded
- [ ] **EXPL-02**: Marker styling shows status (explained / needs-review / unexplained) on the chart itself
- [ ] **EXPL-03**: Visitor can click a marker or table row to open the event detail panel
- [ ] **EXPL-04**: The detail panel shows dates, day and episode move, headline, summary, category, region, scheduled flag, dated source links, confidence, +1D/+5D/+20D forward returns and days to recover
- [ ] **EXPL-05**: Visitor can filter events by category, direction, year and confidence
- [ ] **EXPL-06**: Every panel carries a "coincident, not causal" label

### Event Study

- [ ] **STUDY-01**: Visitor sees the average cumulative return path from day −5 to +60 by category
- [ ] **STUDY-02**: Visitor sees the recovery-time distribution by category
- [ ] **STUDY-03**: Visitor sees event counts per year by category
- [ ] **STUDY-04**: Visitor can choose categories and horizon

### Methodology

- [ ] **METH-01**: The Methodology page explains definitions, thresholds and data sources
- [ ] **METH-02**: The Methodology page presents the corrected notebook findings (from `docs/PHASE0_FINDINGS.md`), with the hand-picked "oracle" trades mentioned only as a lesson
- [ ] **METH-03**: The Methodology page states LLM caveats and the not-investment-advice disclaimer, and shows the last refresh time

### Operations

- [x] **OPS-01**: The app is deployed on Streamlit Community Cloud from a public GitHub repo, with its URL in the README
- [ ] **OPS-02**: A nightly GitHub Actions job (weekday evenings UK time) refreshes prices, detects episodes, enriches new ones and commits `data/`
- [ ] **OPS-03**: The Anthropic API key exists only as a GitHub Actions secret
- [ ] **OPS-04**: Nightly failures are visible (failed run, notification), and the job keeps the workflow from going stale under the 60-day inactivity rule
- [x] **OPS-05**: The data commit does not trigger a CI loop

## v2 Requirements

- **V2-01**: ECB/BoE decisions in the macro calendar
- **V2-02**: Additional `Strategy` rule families (e.g. momentum, volatility targeting)
- **V2-03**: GDELT or finance-news-API `NewsProvider`
- **V2-04**: Cash yield on uninvested periods (T-bill rate)
- **V2-05**: Full-metrics expander (quantstats-style)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Investment advice / live trading signals | Portfolio piece; disclaimer instead |
| Intraday or real-time data | Daily bars refreshed once per trading day are enough |
| Causal claims about news | Events shown as coincident context only |
| Runtime LLM calls, chatbot or Q&A in the app | Cost and abuse risk; no secrets in the app |
| Parameter auto-optimiser / "best rule" button | Undermines the honest-negative-result narrative; data-snooping |
| User accounts or saved runs | Read-only app, no backend |
| Hosted database / SQL Server | A few thousand rows fit in committed files |
| Hand-picked "oracle" trades in the UI | Hindsight; lesson text only (Methodology) |
| Stooq live fallback | Endpoint now needs a CAPTCHA-issued key; retry + last snapshot instead |
| General multi-strategy backtester | Scope creep; `Strategy` interface leaves room |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| DATA-04 | Phase 1 | Complete |
| DATA-05 | Phase 1 | Complete |
| OVER-01 | Phase 1 | Complete |
| OVER-02 | Phase 1 | Complete |
| OVER-03 | Phase 1 | Complete |
| OVER-04 | Phase 1 | Complete |
| OVER-05 | Phase 1 | Complete |
| OVER-06 | Phase 1 | Complete |
| LAB-01 | Phase 1 | Complete |
| LAB-02 | Phase 1 | Complete |
| LAB-03 | Phase 1 | Complete |
| LAB-04 | Phase 1 | Complete |
| LAB-05 | Phase 1 | Complete |
| LAB-06 | Phase 1 | Complete |
| LAB-07 | Phase 1 | Complete |
| LAB-08 | Phase 1 | Complete |
| LAB-09 | Phase 1 | Complete |
| LAB-10 | Phase 1 | Complete |
| OPS-01 | Phase 1 | Complete |
| OPS-05 | Phase 1 | Complete |
| DET-01 | Phase 2 | Complete |
| DET-02 | Phase 2 | Complete |
| DET-03 | Phase 2 | Complete |
| DET-04 | Phase 2 | Complete |
| DET-05 | Phase 2 | Pending |
| DET-06 | Phase 2 | Complete |
| DET-07 | Phase 2 | Complete |
| CAL-01 | Phase 2 | Pending |
| CAL-02 | Phase 2 | Pending |
| NEWS-01 | Phase 3 | Pending |
| NEWS-02 | Phase 3 | Pending |
| NEWS-03 | Phase 3 | Pending |
| NEWS-04 | Phase 3 | Pending |
| NEWS-05 | Phase 3 | Pending |
| NEWS-06 | Phase 3 | Pending |
| NEWS-07 | Phase 3 | Pending |
| NEWS-08 | Phase 3 | Pending |
| REV-01 | Phase 3 | Pending |
| REV-02 | Phase 3 | Pending |
| OPS-03 | Phase 3 | Pending |
| EXPL-01 | Phase 4 | Pending |
| EXPL-02 | Phase 4 | Pending |
| EXPL-03 | Phase 4 | Pending |
| EXPL-04 | Phase 4 | Pending |
| EXPL-05 | Phase 4 | Pending |
| EXPL-06 | Phase 4 | Pending |
| STUDY-01 | Phase 4 | Pending |
| STUDY-02 | Phase 4 | Pending |
| STUDY-03 | Phase 4 | Pending |
| STUDY-04 | Phase 4 | Pending |
| METH-01 | Phase 4 | Pending |
| METH-02 | Phase 4 | Pending |
| METH-03 | Phase 4 | Pending |
| OPS-02 | Phase 4 | Pending |
| OPS-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 58 total
- Mapped to phases: 58
- Unmapped: 0 ✓

---
*Requirements defined: 2026-10-07*
*Last updated: 2026-10-07 after roadmap creation (traceability mapped, 58/58 covered)*
