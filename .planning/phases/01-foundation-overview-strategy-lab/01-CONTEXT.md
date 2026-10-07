# Phase 1: Foundation, Overview & Strategy Lab - Context

**Gathered:** 2026-10-07
**Status:** Ready for planning

<domain>
## Phase Boundary

A public Streamlit URL shows the Overview page (SPY price context) and the Strategy Lab (honest
MA backtests), both reading only committed `data/` files through one cached storage module with
zero runtime network calls. A scheduled GitHub Actions job refreshes `data/prices.parquet` and
`data/meta.json` (validated, with retries, keeping the last good snapshot on failure) and commits
without a CI loop. New rule types plug in through a `Strategy` interface. Requirements: DATA-01..05,
OVER-01..06, LAB-01..10, OPS-01, OPS-05.

Not in this phase: event detection, macro calendar, news, Event Explorer/Study, Methodology page,
failure notifications and the 60-day keepalive (OPS-04, Phase 4).

</domain>

<decisions>
## Implementation Decisions

### Headline & default window (LAB-09)
- **D-01:** Strategy Lab opens on the window **2010-10-19 → 2022-12-16**, total return, 0 bps, no
  trend filter. That reproduces the Phase 0 table (`docs/PHASE0_FINDINGS.md`) exactly. Visitors can
  widen to 1993 → latest.
- **D-02:** The headline is a **live recount**: "N of 24 rules beat buy-and-hold in this window",
  recomputed from the current sidebar settings. A fixed caption anchors the Phase 0 result
  ("On the notebook's 2010–2022 window: 0 of 24"). This refines the UI-SPEC's verbatim
  `## 0 of 24 rules beat buy-and-hold`: at default settings it still reads "0 of 24". Keep the
  UI-SPEC caption text alongside it.
- **D-03:** "Beat buy-and-hold" means **higher total return than B&H over the same window**, with the
  same fills and costs. This is the PHASE0_FINDINGS definition. The count always uses the 24 notebook
  rules ({SMA,EMA}×{10,20,50} short vs {SMA,EMA}×{100,200} long), whatever the picker or heatmap shows.
- **D-04:** The default selected rule is **EMA10 vs SMA200, no filter, 0 bps**, the notebook's
  claimed winner.

### Rule picker & heatmap grid (LAB-01, LAB-05, LAB-08)
- **D-05:** The picker accepts **any period in a bounded range**: short 5–60, long 50–250, with SMA/EMA
  chosen separately for each leg. Short must be less than long, and the planner decides how to enforce that.
- **D-06:** The heatmap uses a **denser grid**, short 5–60 step 5 × long 100–250 step 10 (about 12×16
  cells). It shows excess total return vs B&H on the diverging scale centred at 0 (UI-SPEC), with the
  selected rule's cell highlighted. Keep the overfitting caption ("look for plateaus, not spikes").
- **D-07:** The heatmap shows **one type pair**, the selected rule's SMA/EMA combination. It does not
  show small multiples or tabs.
- **D-08:** The CAGR vs max-drawdown scatter (LAB-08) plots the **24 notebook rules plus B&H**,
  consistent with the headline count.
- **D-09:** Grid results are computed **live in the app**, cached with `st.cache_data` on primitive
  inputs (window, cost, basis, filter, type pair). The planner should profile this: about 192 backtests
  per heatmap plus 24 for the headline and scatter. Add the UI-SPEC's `st.form` "Update grid" fallback
  only if profiling shows it is needed. Do not precompute in the job.
- **D-10:** **All views share the sidebar settings** (window, cost, price basis, 200D trend filter).
  The headline, heatmap, scatter and selected-rule charts all answer the same question. The only
  exception is D-11.

### Robustness views (LAB-06, LAB-07)
- **D-11:** The rolling-start chart shows the **selected rule's excess return per start year with a
  5-year horizon** (the existing `core.grid.rolling_start` default). It always spans **full history
  1993 → latest**, ignoring the sidebar window, with a caption saying so. Its purpose is to show
  window dependence. It still uses the sidebar cost, basis and filter.
- **D-12:** The default in-sample/out-of-sample split is **2022-12-16**. In-sample is the notebook
  window and out-of-sample is 2023 → latest data, a true out-of-sample test of the notebook's rule.
  The IS/OOS section therefore runs from the sidebar start date to the **latest data**, regardless of
  the sidebar end date. Make this explicit in the UI. The split date stays user-adjustable.

### Nightly price job (DATA-01..04, OPS-05)
- **D-13:** **History-rewrite validation**: historical raw OHLCV must match the committed snapshot
  within a tight tolerance (about 0.01%). `adj_close` may be restated, but only by a **single common
  factor** across the overlapping history, which is how dividend rescaling works. Any other change,
  any non-holiday gap, or a shrinking row count fails the job, exits non-zero and leaves the old
  snapshot untouched. The tolerances go in `core/config.py`.
- **D-14:** Schedule: **weekdays ~21:30 UTC** (≈22:30 UK), plus `workflow_dispatch` for manual runs.
  GitHub cron is UTC and ignores BST/GMT changes, which is accepted.
- **D-15:** CI loop guard: add **`paths-ignore: data/**`** to `ci.yml`, and push the data commit with
  the default `GITHUB_TOKEN` (which doesn't trigger workflows). Don't use `[skip ci]`. The push still
  redeploys Streamlit Cloud, which watches the repo directly.
- **D-16:** Job scope this phase: **refresh → validate → commit `data/prices.parquet` + `data/meta.json`**.
  GitHub's built-in failed-run email is enough for now. Issue-based notifications, the 60-day
  keepalive and detect/enrich steps come in Phase 4.
- **D-17:** Remove the Stooq fallback from the price path (already decided: REQUIREMENTS Out of Scope,
  CLAUDE.md). Use yfinance with retries (`auto_adjust=False`, flat columns), and on final failure keep
  the last snapshot.

### Claude's Discretion
- Overview defaults: last ~5 years, line chart, SMA50 + SMA200 overlays on, drawdown regimes off
  by default (or −10/−20 on, as the planner judges), top 10 drawdowns in the table, 20-day realised
  volatility annualised (√252). Candlestick over long ranges should follow the Plotly
  performance guidance in CLAUDE.md, e.g. keep the range slider off and use `Scattergl` for long line views.
- Exact widget types for period inputs (number input vs slider) within the UI-SPEC labels.
- The shape of the `Strategy` interface (LAB-10). It must return a target exposure series, per the
  `core/backtest.py` conventions, and wrap the existing MA crossover and trend-filter rules.
- Sortino and Calmar implementations in `core/metrics.py`, each with tests.
- The `meta.json` schema beyond DATA-04's required fields.
- Retry and backoff library (`tenacity` suggested by research) and the retry count.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope & requirements
- `.planning/PROJECT.md` — core value, constraints, key decisions
- `.planning/REQUIREMENTS.md` — DATA, OVER, LAB, OPS-01/05 requirement text
- `.planning/ROADMAP.md` §Phase 1 — goal and success criteria
- `docs/SPEC.md` — full product spec (page contents, data model, repo layout)
- `CLAUDE.md` — honesty rules, purity rules, and corrections to the research stack (no `ttl`, no Stooq, unverified model IDs)

### UI contract
- `.planning/phases/01-foundation-overview-strategy-lab/01-UI-SPEC.md` — theme tokens, copy, layout, `st.navigation`, caching rules. D-02 refines its headline copy.

### Phase 0 findings & engine
- `docs/PHASE0_FINDINGS.md` — the 0/24 result, its window and definitions. The default view must reproduce it.
- `core/backtest.py` docstring — fill and exposure conventions every rule must follow

### Research
- `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md`, `.planning/research/FEATURES.md`, `.planning/research/SUMMARY.md` — read these with CLAUDE.md's corrections applied

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `core/grid.py`: `run_ma_grid(prices, pairs, cost_bps)`, `default_pairs(...)` (the 24 notebook rules), and `rolling_start(prices, short, long, horizon_years=5)` feed the headline, scatter, heatmap and rolling chart.
- `core/indicators.py`: `MASpec` (kind and period, `.label`, `.compute`), `sma`, `ema` (`span=n`), `add_mas` for the Overview overlays.
- `core/signals.py`: `ma_crossover`, `trend_filter(close, 200)`, `combine_all`, and `crossings` for the trade markers.
- `core/backtest.py`: `run_backtest(prices, target, cost_bps)` → `BacktestResult`.
- `core/metrics.py`: `total_return`, `cagr`, `max_drawdown`, `sharpe`, `summarise`. It needs Sortino and Calmar added.
- `core/data.py`: `fetch_yfinance` (already `auto_adjust=False` and flattens the MultiIndex), `to_total_return`, `write_prices`, `read_prices`. `fetch_stooq` and `load_prices`'s fallback are to be removed (D-17).
- `core/config.py`: the `Settings` dataclass. It currently starts in 2010, so add the 1993 history start, grid ranges, default window and split, and validation tolerances.
- `data/prices.parquet`: existing snapshot (from Phase 0, starting 2010). The job must backfill from 1993-01-29.

### Established Patterns
- `core/` is pure: no Streamlit and no network calls outside `core/data.py`. The app reads only through a new cached `core/storage.py`-style reader (per UI-SPEC: the app's storage module; keep Streamlit caching in the app layer, not in `core/`).
- Every rule returns a target exposure series. Fill at open t+1.
- Thresholds go in config. Every audit fix gets a test. Ruff line length is 100.

### Integration Points
- New `app/` (`Home.py` with `st.navigation`, plus the Overview and Strategy Lab pages) and new `jobs/refresh_prices.py`.
- `.github/workflows/ci.yml` needs `paths-ignore`. A new `.github/workflows/nightly.yml` is needed.
- `pyproject.toml` needs streamlit, plotly, and tenacity if used. Streamlit Cloud installs from `pyproject.toml` or `requirements.txt`, which must be verified on first deploy.
- `.streamlit/config.toml` comes from the UI-SPEC.

</code_context>

<specifics>
## Specific Ideas

- The first impression should be the notebook's favourite rule (EMA10/SMA200) visibly trailing
  buy-and-hold on the notebook's own window, followed by a true out-of-sample check from 2023 onwards.
- The headline must stay honest if a visitor finds a window where some rules win. The live count
  plus the fixed Phase 0 anchor handles that.

</specifics>

<deferred>
## Deferred Ideas

- Failure notifications (auto-issue) and the 60-day workflow keepalive belong in Phase 4 (OPS-04).
- A horizon picker for rolling-start (3/5/10y) and a whole-grid band view could be added later if wanted.
- Heatmap small multiples across all four MA-type pairs could be added later if wanted.

</deferred>

---

*Phase: 01-foundation-overview-strategy-lab*
*Context gathered: 2026-10-07*
