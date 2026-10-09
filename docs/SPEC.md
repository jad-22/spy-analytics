# SPY Market Lens — Project Spec

Oct 6, 2026 · @Jason

## Overview

SPY Market Lens turns the 2022 moving-average notebook into a public Streamlit portfolio app that backtests SPY strategies honestly and explains every major dip or spike with sourced news.

**Goals**

- Correct and extend the original MA crossover analysis (no look-ahead, total-return prices, costs).
- Detect significant SPY moves automatically and attach a cited, categorised explanation to each.
- Let a visitor see price, strategy trades and world events on one interactive timeline.
- Show analytical rigour to a portfolio audience: methodology visible, assumptions labelled.

**Audience:** recruiters, hiring managers and peers viewing a public portfolio, plus Jason as the analyst.

**Non-goals**

- Investment advice or live trading signals. The app carries a clear disclaimer.
- Real-time intraday data. Daily bars, refreshed once per trading day.
- Proving causation between news and price moves. Events are shown as coincident context.

## Key decisions

Three decisions shape the build: a hybrid news pipeline led by Claude API web search, a focused Strategy Lab rather than a general backtester, and a read-only Streamlit Cloud app fed by committed data files.

| Decision | Recommendation | Why | Rejected alternatives |
| --- | --- | --- | --- |
| News source | **Hybrid.** Claude API with server-side web search explains each episode; a deterministic macro calendar (FOMC decisions, CPI and payrolls releases) tags scheduled catalysts. | Works for any date since 2010, returns structured JSON with citations in one call, and the calendar makes "scheduled vs surprise" reliable without an LLM. | GDELT only: free but noisy, needs your own ranking and summarising. Finance news APIs: free tiers usually have short history, so a 2010+ backfill is weak. |
| Backtest scope | **Focused Strategy Lab.** Any SMA/EMA crossover pair plus a 200D trend filter, behind a small `Strategy` interface so more rules can be added later. Robustness via rolling start dates and an in-sample / out-of-sample split; costs in bps. | Your notebook's own conclusion was that results depend on the window. Showing that rigorously is more impressive to a portfolio reader than many strategies. | General multi-strategy backtester (scope creep, weakens the events story). Events only (throws away the existing analysis). |
| Deployment and storage | **Streamlit Community Cloud, read-only app.** Prices, events and news live as Parquet/JSON in the repo's `data/` folder, refreshed nightly by GitHub Actions, which commits and triggers a redeploy. | Streamlit Cloud's filesystem is ephemeral, so nothing written at runtime persists. Keeping API keys only in GitHub Actions secrets means public visitors can never spend your API credits. Snapshotting prices also avoids rate limits on shared cloud IPs. | Runtime LLM calls (cost and abuse risk). Hosted database (unnecessary for a few thousand daily rows). SQL Server (not reachable from Streamlit Cloud without exposing it). |

Price data: yfinance with dividend-adjusted (total return) prices as primary, Stooq as fallback, both only inside the nightly job.

## Notebook audit

The notebook's strategy-return figures (including "EMA10 vs SMA200 beats buy-and-hold by 59%") are not reliable, so Phase 0 rebuilds the backtest before any UI work.

| # | Issue | Location | Impact | Fix in Phase 0 |
| --- | --- | --- | --- | --- |
| 1 | Value changes on every signal, including buys made while out of the market | Returns loop | Equity collapses to roughly "last signal price / first close"; all strategy returns invalid | Vectorised equity: position × open-to-open return |
| 2 | `value = data['Close'].values[-1]` when still in position | End of returns loop | Portfolio value replaced by a share price | Removed by vectorised equity |
| 3 | Crossover test reads `short[t+1]` | `get_buy_sell_signal` | Look-ahead bias | Sign change of `short − long` between t−1 and t; trade at t+1 open |
| 4 | `ewm(period)` sets `com`, not `span` | MA creation | "EMA10" is about a 21-day EMA | `ewm(span=n, adjust=False)` |
| 5 | `mass_generate_signals_from` reads global `data` | Further Analysis | 2021 re-run mixes two datasets | Pure functions, no globals |
| 6 | Hand-picked buy/sell windows | Improvements section | Hindsight; the 743% is unattainable | Shown only as a labelled "oracle" bound, if at all |
| 7 | Unadjusted closes, no costs | Throughout | Buy-and-hold understated, switching overstated | Total-return prices; cost in bps per side |
| 8 | `series[-1]` positional indexing | Several cells | Breaks on current pandas | `.iloc[-1]` |

Acceptance check: re-run the notebook's MA grid on 2010-11 to 2022-12 with the fixed engine and record the corrected conclusions in the Methodology page.

## Architecture

The system splits into an offline nightly job that does all fetching and LLM work, and a read-only Streamlit app that only reads committed files.

&#91;embedded content: architecture · nightly job, data files, read-only app\]

The commit in step four triggers a Streamlit Cloud redeploy, so the public app is never more than one trading day stale and never holds a secret.

## Pages

Five pages share one sidebar (date range, price type) and read only from cached files; no page calls an external API.

| Page | Purpose | Key components | Interactions |
| --- | --- | --- | --- |
| Overview | Market context at a glance | Plotly price chart (line or candlestick) with toggleable SMA/EMA overlays; shaded drawdown regimes (−5%, −10%, −20%); KPI strip: YTD return, distance from all-time high, current drawdown, 20D realised volatility | Range slider, MA toggles, regime toggle |
| Strategy Lab | Honest backtest of MA rules | Rule picker (short MA type and period, long MA type and period, optional 200D trend filter); equity curve vs buy-and-hold; metrics table (CAGR, max drawdown, Sharpe, time in market, trades); short × long heatmap of excess return; rolling-start robustness chart; in-sample vs out-of-sample split | Cost slider (bps), start/end dates, split date |
| Event Explorer | Explain dips and spikes | Price chart with event markers coloured by category and sized by move; drawdown episodes shaded; detail panel for the selected event; filterable events table | Click a marker (`st.plotly_chart(on_select="rerun")`) or a table row to load the panel; filter by category, direction, year, confidence |
| Event Study | Turn news into analysis | Average cumulative return path from day −5 to +60 by category; recovery-time distribution; count of events per year by category | Category multi-select, horizon selector |
| Methodology | Credibility | Definitions, thresholds, data sources, corrected notebook findings, LLM caveats, disclaimer, last-refresh timestamp | None |

**Event detail panel contents:** date range, SPY move (day and episode), headline, two to three sentence summary, category and region, scheduled or surprise flag, linked sources with publish dates, confidence, and forward returns at +1D, +5D, +20D with days to recover.

## Event detection

An event is a cluster of statistically unusual days, so each news search covers one story; thresholds are config values, calibrated in Phase 2 to keep the backfill in the low hundreds of episodes.

| Trigger | Rule (default) | Why |
| --- | --- | --- |
| Shock day | \|log return\| > 2.5 × rolling 60-day σ (σ lagged one day) | Volatility-adjusted: a −2% day in calm 2017 counts; −2% in March 2020 does not flood the list |
| Gap open | \|open / previous close − 1\| > 1.5% | Catches overnight news (earnings season, foreign markets, policy) |
| Drawdown episode | Peak-to-trough ≥ 5% on closes; ends at new high | Captures slow declines with no single shock day |
| Rally episode | Trough-to-peak ≥ 8% within 30 trading days | Captures relief rallies and V-shaped recoveries |

**Clustering:** flagged days within 3 trading days of each other merge into one episode. The episode keeps its largest single-day move as `anchor_date`.

**Search window:** `start_date − 2 days` to `end_date + 1 day` for shocks; for drawdown episodes, the 5 trading days around the steepest leg.

**Severity score** (for marker size and ranking): max |z| of the episode, plus 1 point per 5% of episode move.

## News enrichment

Each episode is enriched once, offline, into a validated JSON record; unvalidated answers are stored as "unexplained" rather than shown as fact.

**Provider interface** (`core/news/base.py`)

```python
class NewsProvider(Protocol):
    name: str
    def explain(self, episode: Episode) -> EventExplanation: ...
```

Implementations: `ClaudeSearchProvider` (`jobs/claude_provider.py`, D-03 -- the only networked provider; `core/` stays network-free), `NullProvider` (`core/news/null.py`; tests and offline dev). A GDELT provider can be added later without touching the app.

**Pipeline per episode**

1. Build the request: dates, direction, SPY move, search window, and any scheduled macro releases in the window.
2. Call the Claude API with the web search tool enabled and a system prompt that requires JSON only, sources dated inside the window, and "unexplained" when nothing fits.
3. Parse and validate against the schema (pydantic).
4. Store the record, the raw response and the model and prompt version.

**Output schema**

```json
{
  "episode_id": "2020-03-09_shock",
  "status": "explained | unexplained | needs_review",
  "headline": "string, <= 90 chars",
  "summary": "2-3 sentences, own words",
  "category": "monetary_policy | inflation_data | growth_data | geopolitics | pandemic_health | banking_credit | earnings_tech | fiscal_trade_policy | energy_commodities | other",
  "region": "US | Europe | China | Global | Other",
  "scheduled": true,
  "drivers": ["string"],
  "sources": [{"title": "string", "url": "https://...", "publisher": "string", "published": "YYYY-MM-DD"}],
  "confidence": 0.0
}
```

**Validation rules**

- At least one source with a `published` date inside the search window, otherwise `unexplained`.
- `confidence` < 0.5 or conflicting sources → `needs_review`.
- Summary written in the model's own words; no quoted passages beyond a short phrase.

**Curation:** a local-only `scripts/review_events.py` CLI (D-05; no Streamlit page) lets Jason accept, edit or reject records. Overrides live in `data/event_overrides.json` and always win over model output at read time (`core/storage.py::load_effective_events`); `events.json` itself is never rewritten by a review decision.

**Cost controls**

- Backfill runs once; nightly runs only enrich new episodes.
- Hard cap on episodes per run and on searches per request, set in config.
- Model ID set in config. Check current model IDs and web-search pricing in the [Claude API docs](https://docs.claude.com/en/api/overview) before the backfill.
- API key stored only as a GitHub Actions secret, never in Streamlit Cloud.

## Data model

All persisted data is six small files in `data/`, written only by the nightly job and read by the app through `st.cache_data`.

| File | Grain | Key columns |
| --- | --- | --- |
| `prices.parquet` | One row per trading day | `date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `source` |
| `macro_calendar.parquet` | One row per scheduled release | `date`, `release` (FOMC, CPI, payrolls), `source_url` |
| `episodes.parquet` | One row per detected episode | `episode_id`, `start_date`, `end_date`, `anchor_date`, `direction`, `trigger`, `move_pct`, `max_z`, `severity`, `search_from`, `search_to`, `detector_version` |
| `events.json` | One record per episode explanation | Schema in News enrichment, plus `model`, `prompt_version`, `enriched_at` |
| `event_overrides.json` | One record per manual edit | `episode_id`, edited fields, `reviewed_at` |
| `enrichment_spend.json` | One record per paid backfill/escalation run | `run_id`, `model`, `mode`, tokens, `web_search_requests`, `cost_usd` |
| `meta.json` | One record | `last_refresh`, `last_trading_day`, `row_counts`, `detector_version` |

Analytics derived at runtime (MAs, signals, equity curves, forward returns) are never stored; they are cheap to recompute and depend on user inputs.

## Repo and stack

One Python repo holds the app, a tested `core` package and the jobs; the app imports `core` but never the jobs.

```
spy-market-lens/
  app/
    Home.py
    pages/  1_Overview.py  2_Strategy_Lab.py  3_Event_Explorer.py  4_Event_Study.py  5_Methodology.py
    components/  charts.py  sidebar.py  event_panel.py
  core/
    config.py  data.py  indicators.py  signals.py  backtest.py  metrics.py
    events.py  calendar.py  storage.py
    news/  base.py  null.py  schema.py  sources.py  prompt.py  cost.py  overrides.py
  jobs/
    refresh_prices.py  detect_events.py  enrich_events.py  claude_provider.py  nightly.py
  scripts/
    review_events.py  report_phase2.py  report_news_budget.py  report_phase3.py
  data/            (committed Parquet/JSON)
  notebooks/       (original EDA, kept for history)
  tests/
  .github/workflows/  ci.yml  nightly.yml  backfill.yml
  pyproject.toml  README.md  .streamlit/config.toml
```

| Layer | Choice |
| --- | --- |
| Language and packaging | Python 3.12, `pyproject.toml`, `uv` or `pip` |
| Data | pandas, pyarrow, yfinance (Stooq fallback) |
| Charts | Plotly |
| App | Streamlit, multipage via `pages/` |
| Validation | pydantic |
| LLM | `anthropic` SDK with the web search tool |
| Quality | pytest, ruff |
| CI | GitHub Actions: `ci.yml` on every push (lint, tests); `nightly.yml` on weekday evenings UK time (refresh, detect, enrich, commit) |

## Delivery plan

Five phases run in order, each closed by a gate; Phase 0 starts now because it changes no UI decisions and every later phase depends on it.

&#91;embedded content: delivery plan · 5 phases, 5 gates · S/M/L = relative size\]

Phase 3 is the largest because it includes the one-off backfill and manual review; Phases 1 and 2 can overlap if the detector is built while the MVP is deployed.

## Risks and open questions

The biggest risk is a confident but wrong news explanation on a public page; date-window validation, confidence scores and manual review are the main controls.

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| LLM attributes a move to the wrong story | Medium | Sources must be dated in window; `needs_review` status; overrides file; "coincident, not causal" label on every panel |
| yfinance breaks or rate-limits | Medium | Stooq fallback; last good snapshot stays in `data/` |
| API spend creeps up | Low | Offline-only calls, per-run caps, cache forever |
| Nightly commits bloat the repo | Low | Rewrite files in place; prices are about 4,000 rows |
| Streamlit Cloud app sleeps when idle | High | Acceptable for a portfolio; note "may take a moment to wake" in README |
| Copyright on news text | Low | Own-words summaries, links out, no article text stored |

**Open questions**

- [ ] History start: keep 2010 (matches the notebook) or extend to 1993 (SPY inception) to include 2000 and 2008?
- [ ] Should the macro calendar include UK/ECB decisions, or stay US-only?
- [ ] Public GitHub repo as part of the portfolio, or private repo with a public app only?
