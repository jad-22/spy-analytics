# SPY Market Lens

## What This Is

A public Streamlit portfolio app that turns Jason's 2022 moving-average notebook into an honest
SPY backtesting lab, and explains every major SPY dip or spike with sourced, categorised news.
Visitors see price, strategy trades and world events on one interactive timeline, with the
methodology and its assumptions visible. Audience: recruiters, hiring managers and peers viewing
the portfolio, plus Jason as the analyst.

## Core Value

Every number and every explanation on the page is honest and traceable. Backtests have no
look-ahead and use total-return prices and costs. Event explanations cite sources dated inside
the move's window, or are marked "unexplained". If the app is wrong in public, the portfolio
piece fails.

## Requirements

### Validated

- ✓ Corrected backtest engine: next-open fills, no look-ahead, total-return prices, costs in bps, matched buy-and-hold benchmark (Phase 0)
- ✓ SMA/EMA indicators with `span=n` EMAs; MA crossover, 200D trend filter and AND-combination rules (Phase 0)
- ✓ Metrics: total return, CAGR, max drawdown, Sharpe, time in market, fills (Phase 0)
- ✓ 24-rule grid on a common window and rolling-start robustness (Phase 0)
- ✓ Price loading from yfinance with Stooq fallback, plus a parquet snapshot (Phase 0)
- ✓ Notebook re-run documented: 0 of 24 rules beat buy-and-hold (`docs/PHASE0_FINDINGS.md`) (Phase 0)
- ✓ CI: ruff + pytest on every push (Phase 0)
- ✓ Event detection: shock days, gap opens, drawdown and rally episodes, clustering, severity, replay-stable closed/open status; 142 episodes since 1993 — Validated in Phase 2: Event Detection & Macro Calendar
- ✓ US macro calendar (FOMC, CPI, payrolls; 1138 rows, 1993–2027) tagging scheduled vs surprise catalysts — Validated in Phase 2: Event Detection & Macro Calendar

### Active

- [ ] Overview page: price chart (line/candle), MA overlays, drawdown regime shading, KPI strip
- [ ] Strategy Lab: rule picker, trend filter, costs, equity vs B&H, metrics, short × long heatmap, rolling-start chart, in-sample/out-of-sample split
- [ ] Nightly price refresh writing `data/` snapshots; app reads only committed files
- [ ] News enrichment via Claude API + web search into validated, cited JSON records
- [ ] Manual review and overrides for event records
- [ ] Event Explorer: event markers, detail panel, filterable table
- [ ] Event Study: average path by category, recovery times, events per year
- [ ] Methodology page: definitions, thresholds, sources, corrected notebook findings, LLM caveats, disclaimer
- [ ] Nightly GitHub Actions job: refresh → detect → enrich new → commit → redeploy
- [ ] Deployed on Streamlit Community Cloud from a public GitHub repo

### Out of Scope

- Investment advice or live trading signals — portfolio piece; clear disclaimer instead
- Intraday or real-time data — daily bars refreshed once per trading day are enough
- Claims of causation between news and moves — shown as coincident context only
- Runtime LLM or price API calls from the app — cost and abuse risk; offline jobs only
- General multi-strategy backtester — scope creep that weakens the events story; `Strategy` interface leaves room later
- Hosted database / SQL Server — a few thousand rows fit in committed Parquet/JSON
- Notebook's hand-picked "oracle" trades (~743%) — hindsight; mentioned only as a lesson in Methodology text
- Non-US central banks (ECB, BoE) in the macro calendar — US releases drive most SPY moves; can be added later
- GDELT / finance-news-API providers — `NewsProvider` interface allows adding one later without app changes

## Context

- Brownfield: Phase 0 (complete, commit `dc4e67b`) rebuilt the notebook logic as a tested
  `core/` package (13 tests). The 2022 notebook stays in `notebooks/` for history.
- Phase 0 headline: with bugs fixed, none of the 24 MA crossover rules beats buy-and-hold
  (2010–2022, any price basis or cost). The rules mainly reduce drawdowns: −18.5% for the
  best rule vs −32% for buy-and-hold. The Strategy Lab should make this trade-off visible.
- Full spec: `docs/SPEC.md`. Earlier hand-written roadmap: `docs/ROADMAP.md` (superseded by
  `.planning/ROADMAP.md`).
- Local env: Windows, conda-created Python 3.12 env at `.venv` (`.venv\python.exe`).
- Price history: yfinance SPY data starts 1993-01-29. Total-return adjustment uses
  `adj_close / close`. Stooq fallback is assumed adjusted and needs verifying against yfinance.

## Constraints

- **Tech stack**: Python 3.12, pandas/pyarrow, Plotly, Streamlit multipage, pydantic, `anthropic` SDK with web search, pytest + ruff — per spec
- **Hosting**: Streamlit Community Cloud, which has an ephemeral filesystem — all data committed to `data/` by GitHub Actions
- **Security**: Anthropic API key only in GitHub Actions secrets, never in Streamlit Cloud or the repo
- **Budget**: one-off news backfill ≤ ~$25 of Claude API spend; hard caps on episodes per run and searches per request
- **Honesty**: no look-ahead in any signal; every reported figure regenerated by a script, not hand-edited
- **Purity**: `core/` has no Streamlit imports; app never imports `jobs/`
- **Copyright**: own-words summaries, links out, no stored article text

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hybrid news: Claude API + web search, plus deterministic US macro calendar | Works for any date, structured cited JSON in one call; calendar makes "scheduled vs surprise" reliable | — Pending |
| Focused Strategy Lab (MA crossovers + 200D filter) behind a `Strategy` interface | The notebook's real lesson is window-dependence; rigour beats breadth | — Pending |
| Read-only Streamlit app fed by committed Parquet/JSON, refreshed nightly | Ephemeral FS, no secrets in app, avoids rate limits | — Pending |
| History starts 1993 (SPY inception) for the app and events | Includes 2000 and 2008, the richest events for the Event Study; Phase 0 findings stay on 2010 for notebook parity | — Pending |
| Macro calendar US-only (FOMC, CPI, payrolls) | Simplest; drives most SPY moves | ✓ Good — built in Phase 2; FRED lists non-print revision dates, kept in an explicit config list; rebuild needs the FRED key locally |
| Public GitHub repo | Code is part of the portfolio; free Actions minutes | — Pending |
| Drop the notebook's oracle trades from the UI | Hindsight, not attainable; lesson noted in Methodology | — Pending |
| Strategy Lab and events story weighted equally | Both are portfolio headlines | — Pending |
| Only "closed" episodes are enriched; closure waits for any span future data could extend | Phase 3 API spend must never be wasted on an episode that later changes | ✓ Good — replay tests at every prefix (Phase 2) |
| Corrected engine: 0/24 MA rules beat B&H | Verified on live data, both windows, raw and TR, 0 and 5 bps | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-09 after Phase 2*
