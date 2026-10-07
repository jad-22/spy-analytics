# Phase 1: Foundation, Overview & Strategy Lab - Research

**Researched:** 2026-10-07
**Domain:** Read-only Streamlit multipage app (Overview + Strategy Lab) over a committed Parquet
snapshot, plus a nightly GitHub Actions price-refresh job. Built on the already-tested `core/`
engine from Phase 0.
**Confidence:** HIGH overall. The backtest math is already verified (Phase 0 tests green). The
app/plumbing layer (Streamlit, Plotly, tenacity, yfinance, GitHub Actions push-without-CI-loop)
was independently re-verified in this session against the versions actually installed/available
in this repo's `.venv`, not just against the stale `.planning/research/*.md` docs (see
"State of the Art" — several of those docs' pinned versions are now one or two majors behind
what's actually on PyPI and what's already installed locally).

## Summary

Phase 1 adds one new top-level concern (a Streamlit app + a nightly data job) on top of a
`core/` package that is already correct and tested. The architecture is a strict one-way
contract: an offline job fetches/validates/writes `data/prices.parquet` + `data/meta.json`; the
app only ever reads those files through a single cached `core/storage.py` module and recomputes
everything else (indicators, signals, backtests, grids) live and cheaply from the cached
DataFrame. Nothing in `core/` may import Streamlit; nothing in `app/` may import `jobs/`,
`requests`, or `yfinance`.

Three things in this session's re-verification diverge from the project's existing
`.planning/research/*.md` docs and matter for planning: (1) `yfinance` is now at **1.7.0**, not
the `0.2.40`-era API those docs assumed — the jump is *not* a breaking change for this codebase's
usage (`auto_adjust=False` + manual `MultiIndex` flattening still works exactly as written and
all 13 existing tests still pass against it); (2) `streamlit` (1.65.0) and `plotly` (7.1.0) are
both newer majors than the stale docs recommended, and both install and import cleanly alongside
the already-installed `pandas 3.0.6` / `numpy 2.5.3` — verified directly in this session, not
assumed; (3) the Strategy Lab heatmap does **not** need `st.plotly_chart(on_select=...)` to work
at all in Phase 1 (selection is driven by the sidebar picker, not a heatmap click — see
Architectural Responsibility Map and Common Pitfalls) — this resolves the blocker flagged in
`.planning/STATE.md`'s "Blockers/Concerns" for *this* phase; it only matters for Phase 4's Event
Explorer.

**Primary recommendation:** Build `core/storage.py` first (the one new chokepoint every job and
every page depends on), then `jobs/refresh_prices.py`, then the Overview page (prices only),
then the Strategy Lab (needs `core/grid.py` extensions + a new `Strategy` protocol + Sortino/
Calmar in `core/metrics.py`), then the nightly workflow. Use `st.navigation`/`st.Page` from the
very first page — never a `pages/` directory — and give every `st.cache_data` reader no `ttl`
(per `CLAUDE.md`'s override), keyed only on the file path.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Headline & default window (LAB-09)**
- D-01: Strategy Lab opens on the window 2010-10-19 → 2022-12-16, total return, 0 bps, no trend
  filter. Reproduces `docs/PHASE0_FINDINGS.md` exactly. Visitors can widen to 1993 → latest.
- D-02: The headline is a **live recount**: "N of 24 rules beat buy-and-hold in this window",
  recomputed from the current sidebar settings. A fixed caption anchors the Phase 0 result
  ("On the notebook's 2010–2022 window: 0 of 24"). At default settings it still reads "0 of 24".
  Keep the UI-SPEC caption text alongside it.
- D-03: "Beat buy-and-hold" means higher total return than B&H over the same window, same fills
  and costs (the PHASE0_FINDINGS definition). The count always uses the 24 notebook rules
  ({SMA,EMA}×{10,20,50} short vs {SMA,EMA}×{100,200} long), whatever the picker or heatmap shows.
- D-04: Default selected rule is EMA10 vs SMA200, no filter, 0 bps (the notebook's claimed
  winner).

**Rule picker & heatmap grid (LAB-01, LAB-05, LAB-08)**
- D-05: The picker accepts any period in a bounded range: short 5–60, long 50–250, SMA/EMA
  chosen separately per leg. Short must be < long; planner decides enforcement.
- D-06: Heatmap uses a denser grid: short 5–60 step 5 × long 100–250 step 10 (~12×16 cells).
  Shows excess total return vs B&H on a diverging scale centred at 0, selected rule's cell
  highlighted. Keep the overfitting caption ("look for plateaus, not spikes").
- D-07: Heatmap shows **one type pair** — the selected rule's SMA/EMA combination. No small
  multiples, no tabs.
- D-08: CAGR-vs-maxDD scatter (LAB-08) plots the 24 notebook rules plus B&H, consistent with the
  headline count.
- D-09: Grid results are computed **live in the app**, cached with `st.cache_data` on primitive
  inputs (window, cost, basis, filter, type pair). Planner should profile: ~192 backtests per
  heatmap plus 24 for headline/scatter. Add the UI-SPEC's `st.form` "Update grid" fallback only
  if profiling shows it's needed. Do not precompute in the job.
- D-10: All views share the sidebar settings (window, cost, price basis, 200D trend filter).
  Headline, heatmap, scatter and selected-rule charts all answer the same question. Only
  exception is D-11.

**Robustness views (LAB-06, LAB-07)**
- D-11: Rolling-start chart shows the selected rule's excess return per start year with a 5-year
  horizon (`core.grid.rolling_start` default). Always spans full history 1993 → latest, ignoring
  the sidebar window, with a caption saying so. Uses sidebar cost, basis and filter.
- D-12: Default IS/OOS split is 2022-12-16. In-sample is the notebook window; out-of-sample is
  2023 → latest (a true out-of-sample test). The IS/OOS section runs from sidebar start date to
  **latest data**, regardless of sidebar end date. Make this explicit in the UI. Split date stays
  user-adjustable.

**Nightly price job (DATA-01..04, OPS-05)**
- D-13: History-rewrite validation: historical raw OHLCV must match the committed snapshot within
  ~0.01% tolerance. `adj_close` may be restated, but only by a single common factor across
  overlapping history (dividend rescaling). Any other change, any non-holiday gap, or a shrinking
  row count fails the job, exits non-zero, leaves the old snapshot untouched. Tolerances go in
  `core/config.py`.
- D-14: Schedule: weekdays ~21:30 UTC (≈22:30 UK), plus `workflow_dispatch`. Cron is UTC, ignores
  BST/GMT — accepted.
- D-15: CI loop guard: add `paths-ignore: data/**` to `ci.yml`, push the data commit with the
  default `GITHUB_TOKEN` (doesn't trigger workflows). Don't use `[skip ci]`. The push still
  redeploys Streamlit Cloud (which watches the repo directly).
- D-16: Job scope this phase: refresh → validate → commit `data/prices.parquet` +
  `data/meta.json`. GitHub's built-in failed-run email is enough for now. Issue notifications,
  60-day keepalive, detect/enrich steps come in Phase 4.
- D-17: Remove the Stooq fallback from the price path. Use yfinance with retries
  (`auto_adjust=False`, flat columns); on final failure keep the last snapshot.

### Claude's Discretion
- Overview defaults: last ~5 years, line chart, SMA50 + SMA200 overlays on, drawdown regimes off
  by default (or −10/−20 on, planner's judgment), top 10 drawdowns in the table, 20-day realised
  vol annualised (√252). Candlestick over long ranges follows the Plotly performance guidance in
  CLAUDE.md (range slider off, `Scattergl` for long line views).
- Exact widget types for period inputs (number input vs slider) within UI-SPEC labels.
- The shape of the `Strategy` interface (LAB-10). Must return a target exposure series per
  `core/backtest.py` conventions, wrapping the existing MA crossover and trend-filter rules.
- Sortino and Calmar implementations in `core/metrics.py`, each with tests.
- The `meta.json` schema beyond DATA-04's required fields.
- Retry/backoff library (`tenacity` suggested by research) and retry count.

### Deferred Ideas (OUT OF SCOPE)
- Failure notifications (auto-issue) and the 60-day workflow keepalive belong in Phase 4 (OPS-04).
- A horizon picker for rolling-start (3/5/10y) and a whole-grid band view could be added later.
- Heatmap small multiples across all four MA-type pairs could be added later.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | Price job writes SPY OHLCV + adj close from 1993-01-29 to latest to `data/prices.parquet` | `core/data.py::fetch_yfinance` already correct for format; needs `start="1993-01-29"` passed from `jobs/refresh_prices.py` (not the current `core/config.py` `start="2010-01-01"`). See Architecture Patterns. |
| DATA-02 | Pins `auto_adjust=False`, flat columns, retries, exits non-zero on final failure, leaves last snapshot | `fetch_yfinance` already pins `auto_adjust=False` and flattens `MultiIndex` columns — verified unaffected by the yfinance 1.7.0 jump (Code Examples, State of the Art). Wrap with `tenacity.retry` (Don't Hand-Roll). |
| DATA-03 | Validates snapshot before writing (no non-holiday gaps, no history rewrite beyond tolerance, row count never shrinks) | New logic — see Architecture Patterns "Validation gate" and D-13. No existing library does this; it's a ~30-line pure function belonging in `core/data.py` or a new `core/validate.py`, tested directly (Validation Architecture). |
| DATA-04 | `meta.json` records last refresh, last trading day, row counts, detector version | New `core/storage.py` write function. `detector_version` field must exist now (e.g. `0`) even though detection is Phase 2, so the schema doesn't change shape later. |
| DATA-05 | App reads every `data/` file through one cached storage module, no page makes a network call | `core/storage.py` (new, Streamlit-import-free) + `app/`-level `@st.cache_data` wrappers. Architecture Patterns, Anti-Pattern "App importing jobs/". |
| OVER-01..06 | Overview page: price chart (line/candle), MA overlays, drawdown regime shading, KPI strip, drawdown table, total-return/price-only toggle | All computable directly from existing `core/indicators.py`, `core/metrics.py` (needs small `regimes`/KPI helpers — see Architecture Patterns), Plotly patterns in Code Examples. |
| LAB-01..10 | Strategy Lab: rule picker, cost/date controls, equity vs B&H, metrics table, heatmap, rolling-start, IS/OOS, scatter, headline, `Strategy` interface | `core/grid.py`, `core/backtest.py`, `core/signals.py` already provide the engine; needs a denser-grid pairs helper, an IS/OOS split helper, Sortino/Calmar in `core/metrics.py`, and a `Strategy` Protocol (Architecture Patterns, Code Examples). |
| OPS-01 | Deployed on Streamlit Community Cloud from a public repo, URL in README | Deployment mechanics only — `.streamlit/config.toml` per UI-SPEC; Streamlit Cloud installs from `pyproject.toml` directly (verified capability, not independently tested this session — flagged in Open Questions). |
| OPS-05 | Data commit doesn't trigger a CI loop | Confirmed via official GitHub Actions docs this session: `GITHUB_TOKEN`-authored pushes don't trigger further workflow runs, AND `paths-ignore: data/**` independently skips `ci.yml` for data-only commits — both mechanisms verified current (Common Pitfalls, Code Examples). |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Price fetch, validation, retry/backoff | Offline job (`jobs/refresh_prices.py`) | — | Network calls are forbidden in the app tier (DATA-05); this is the only place with internet + no secrets to protect |
| Snapshot validation gate (gap/shrink/rewrite checks) | Offline job, backed by a pure `core/` function | — | Must run before the file is written, so it belongs with the writer, but the check itself is pure and testable in isolation |
| `data/prices.parquet`, `data/meta.json` persistence | Committed file store (`data/`) | — | The entire integration contract between offline job and app is "files committed to git," not a database or API |
| Cached file reads | `core/storage.py` (pure) wrapped by `app/`-level `@st.cache_data` | — | `core/` stays Streamlit-import-free (testable standalone); the app layer owns the caching decorator so `core/storage.py` works in tests/scripts too |
| Indicators, signals, backtest, metrics, grid math | `core/` (pure, already built in Phase 0 + this phase's additions) | — | Recomputed live and cheaply on every rerun from the cached DataFrame; never persisted, per the project's own stated principle |
| Overview / Strategy Lab UI, widgets, Plotly figure construction | `app/pages/*.py` + `app/components/*.py` | — | Thin by design — reads via storage, calls `core/` for math, builds a Plotly figure, nothing else |
| Nightly scheduling, CI-loop avoidance, commit/push | `.github/workflows/nightly.yml` | GitHub's own token/scheduling infra | Outside both the app and `core/` — pure CI/CD configuration, verified against current GitHub Actions docs |
| Streamlit theme, chart color tokens | `.streamlit/config.toml` | `app/` (passes `theme="streamlit"` to every `st.plotly_chart`) | Declared once, consumed automatically — never hand-built per-chart Plotly templates |

## Standard Stack

### Core

| Library | Version (verified) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12.15 (this repo's `.venv`) | Runtime | Matches `pyproject.toml`'s `>=3.12` floor and Streamlit Community Cloud's default. `[VERIFIED: local .venv]` |
| streamlit | 1.65.0 installed and import-tested this session | Multipage app framework | `st.navigation`/`st.Page` confirmed current recommended pattern via live doc fetch this session; supersedes the `pages/` directory sketched in `docs/SPEC.md`. `[VERIFIED: docs.streamlit.io, pip index, local install]` |
| plotly | 7.1.0 installed and import-tested this session | Charts: candlestick, line, markers, shaded regions, heatmap | Candlestick + `add_vrect` + `go.Scattergl` all confirmed working on 7.1.0 in this session (no API break from the project's assumed 5.24 — the only 6.0/7.0 breaking changes are Mapbox traces, `heatmapgl`, `pointcloud`, and legacy `transforms`, none of which this app uses). `[VERIFIED: local import test, plotly.com/python/v6-migration, v7-migration]` |
| tenacity | 9.2.1 installed this session | Retry/backoff for `fetch_yfinance` and the nightly job | Standard Python retry library; confirmed installable alongside pandas 3.0.6/numpy 2.5.3 with no conflict. `[VERIFIED: pip index, local install, slopcheck OK]` |
| pandas | 3.0.6 (already installed in `.venv`) | DataFrame engine | Already in use by `core/`; all 13 existing Phase 0 tests pass unmodified against 3.0.6 (verified this session) — no migration needed despite the major-version jump from the `pyproject.toml` floor of `>=2.2`. `[VERIFIED: local pytest run]` |
| numpy, pyarrow, requests, yfinance | 2.5.3 / 25.0.1 / 2.34.2 / 1.7.0 (already installed) | Numerics, Parquet I/O, HTTP, price fetch | Already Phase 0 dependencies; `yfinance` 1.7.0's `download()` signature still exposes `auto_adjust` and `multi_level_index` exactly as `core/data.py` already uses them (verified via `help(yf.download)` this session). `[VERIFIED: local .venv inspection]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest, ruff | 9.1.1 / 0.16.10 (already installed) | Test runner, linter | Already configured in `pyproject.toml`; extend coverage to `app/`, `jobs/`, new `core/` modules. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `st.navigation` + `st.Page` | `pages/` directory (SPEC.md's literal sketch) | Simpler for a drop-in single-dir layout, but once any session calls `st.navigation` Streamlit permanently ignores `pages/` — mixing the two mid-build is a one-way trap. Already decided against in CONTEXT.md/UI-SPEC. |
| Hand-rolled `git add`/`commit`/`push` in `nightly.yml` | `stefanzweifel/git-auto-commit-action@v7` (confirmed actively maintained, v7.2.0 as of June 2026) | The action saves a few lines of YAML and handles edge cases (no-op when nothing changed) but adds a third-party action to a workflow that writes to a public repo. Given D-16's scope is just "refresh → validate → commit," a 4-line hand-rolled `git` sequence with an explicit `git diff --quiet || (commit && push)` guard is simpler to audit and has zero supply-chain surface. Recommend hand-rolled; note the action as a fallback if the hand-rolled version proves fiddly (e.g. with `[skip ci]` interactions already ruled out by D-15). |
| Sortino via a metrics library (`empyrical`, `quantstats`) | Hand-written in `core/metrics.py` | V2 Requirements already lists a "full-metrics expander (quantstats-style)" as out-of-scope-for-v1; Sortino/Calmar are ~10-line pure functions matching the existing `summarise()` pattern — pulling in a new dependency for two formulas this small fails the "Don't Hand-Roll" test in the *other* direction (the formulas are standard and small enough that hand-rolling with a test is the right call, not a library). |

**Installation:**
```bash
pip install "streamlit>=1.65" "plotly>=7.1" "tenacity>=9.2"
# pandas/numpy/pyarrow/requests/yfinance already satisfied by current .venv
```

**Version verification:** Ran directly this session —
```
.venv/python.exe -m pip index versions streamlit   # 1.65.0 latest
.venv/python.exe -m pip index versions plotly       # 7.1.0 latest
.venv/python.exe -m pip index versions tenacity      # 9.2.1 latest
.venv/python.exe -m pip index versions yfinance      # 1.7.0 latest, matches installed
```
All four installed cleanly into the project's actual `.venv` (not just the floors in the stale
`.planning/research/STACK.md`), and `pytest -q` (13 passed) + `ruff check .` (all checks passed)
were both re-run clean afterward.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| streamlit | PyPI | ~274 releases on record, multi-year project | Very high (industry-standard dashboard framework) | github.com/streamlit/streamlit | [OK] | Approved |
| plotly | PyPI | ~321 releases on record, multi-year project | Very high (industry-standard charting library) | github.com/plotly/plotly.py | [OK] | Approved |
| tenacity | PyPI | ~62 releases, maintained since 2016 | Very high (standard retry library) | github.com/jd/tenacity | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

`slopcheck` was installed and run in this session (`slopcheck install streamlit plotly tenacity`)
and returned `[OK]` for all three against the real PyPI index. Package identities were not
discovered via an unverified web search in this session — `streamlit`, `plotly`, and `tenacity`
are already named in the project's own prior `.planning/research/STACK.md` and `CLAUDE.md`, and
are universally-known, multi-year-maintained libraries; combined with the slopcheck `[OK]`
verdict and direct `pip index`/local-install confirmation, these are tagged `[VERIFIED]` rather
than `[ASSUMED]`. `pandas`, `numpy`, `pyarrow`, `requests`, `yfinance` were not re-audited via
slopcheck (already in production use since Phase 0, no new install) but their currently-installed
versions were directly verified against `pip index versions` this session.

## Architecture Patterns

### System Architecture Diagram

```
 OFFLINE (GitHub Actions, weekday evenings UTC, has network, no secrets needed this phase)
 ┌────────────────────────────────────────────────────────────────────┐
 │ jobs/refresh_prices.py                                              │
 │   1. core.data.fetch_yfinance(ticker, start="1993-01-29")  [retry]  │
 │   2. validate(new_df, existing_snapshot)  -- gap/shrink/rewrite gate│
 │        pass --> continue        fail --> exit non-zero, no write   │
 │   3. core.storage.write_prices(new_df) + write_meta(...)            │
 └───────────────────────────┬──────────────────────────────────────-─┘
                              │ git commit (GITHUB_TOKEN) + push
                              ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │ data/prices.parquet, data/meta.json   (committed, the only contract)│
 └───────────────────────────┬──────────────────────────────────────-─┘
                              │ triggers Streamlit Cloud redeploy
                              ▼
 ONLINE (Streamlit Community Cloud, ephemeral FS, zero secrets, zero network)
 ┌────────────────────────────────────────────────────────────────────┐
 │ app/Home.py  (st.navigation registers Overview + Strategy Lab)      │
 │      │                                                              │
 │      ▼                                                              │
 │ @st.cache_data wrappers  →  core/storage.py (pure reads)            │
 │      │                                                              │
 │      ▼                                                              │
 │ sidebar inputs (date range, basis, cost, rule) ──┐                  │
 │                                                   ▼                  │
 │ core/indicators.py, core/signals.py, core/backtest.py, core/grid.py │
 │ core/metrics.py (+Sortino/Calmar), Strategy protocol                │
 │                                                   │                  │
 │                                                   ▼                  │
 │ app/components/charts.py  →  Plotly figures  →  st.plotly_chart(    │
 │                                                     theme="streamlit")│
 └────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
app/
├── Home.py                       # st.navigation + st.Page registration, sidebar entrypoint
├── components/
│   ├── sidebar.py                 # shared date range / price basis / cost widgets
│   └── charts.py                  # Plotly figure builders (price, equity, heatmap, scatter)
├── pages/
│   ├── 1_overview.py
│   └── 2_strategy_lab.py
core/
├── storage.py                    # NEW — read_prices/read_meta, no Streamlit import
├── grid.py                        # EXTEND — heatmap_pairs() for independent short/long kind+range
├── metrics.py                     # EXTEND — sortino(), calmar()
├── backtest.py                    # EXTEND — is_oos_summary() split helper
├── signals.py                     # EXTEND — Strategy Protocol
├── config.py                      # EXTEND — 1993 start, grid ranges, default window/split, tolerances
jobs/
└── refresh_prices.py              # NEW — fetch, validate, write, exit non-zero on failure
.github/workflows/
├── ci.yml                         # ADD paths-ignore: data/**
└── nightly.yml                    # NEW
.streamlit/
└── config.toml                    # per UI-SPEC, authoritative values already specified there
```

### Pattern 1: Build-then-serve, no exceptions

**What:** All network/impure work happens only in `jobs/refresh_prices.py`; the app only reads
finished, committed artifacts and recomputes cheaply.
**When to use:** Always, for every new page or component in this phase — this is the entire
point of DATA-05 and the existing `core/` purity rule.
**Example:**
```python
# core/storage.py — no streamlit import, testable standalone
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from core.data import read_prices  # reuse Phase 0's reader

def load_prices(path: Path) -> pd.DataFrame:
    return read_prices(path)

def load_meta(path: Path) -> dict:
    return json.loads(path.read_text())

# app/Home.py or app/components/sidebar.py — the only place that adds caching
import streamlit as st
from core.config import SETTINGS
from core.storage import load_prices, load_meta

@st.cache_data  # no ttl — redeploy-on-commit clears the whole process (CLAUDE.md override)
def get_prices() -> "pd.DataFrame":
    return load_prices(SETTINGS.prices_path)

@st.cache_data
def get_meta() -> dict:
    return load_meta(SETTINGS.meta_path)
```

### Pattern 2: `Strategy` Protocol wrapping existing signal functions (LAB-10)

**What:** A small Protocol in `core/signals.py` that every rule (current and future) satisfies,
returning a target exposure series per `core/backtest.py`'s documented conventions.
**When to use:** The Strategy Lab page must construct the active rule's target series through
this interface, never by calling `ma_crossover`/`trend_filter` directly from `app/`.
**Example:**
```python
# core/signals.py — addition
from typing import Protocol
import pandas as pd

class Strategy(Protocol):
    name: str
    def target(self, prices: pd.DataFrame) -> pd.Series: ...

class MACrossoverStrategy:
    """Wraps ma_crossover, optionally AND-ed with a 200D trend filter."""
    def __init__(self, short: MASpec, long: MASpec, trend_filter_period: int | None = None):
        self.short, self.long, self.trend_filter_period = short, long, trend_filter_period
        self.name = f"{short.label}__{long.label}"
        if trend_filter_period:
            self.name += f"__trend{trend_filter_period}"

    def target(self, prices: pd.DataFrame) -> pd.Series:
        base = ma_crossover(prices["close"], self.short, self.long)
        if self.trend_filter_period:
            return combine_all(base, trend_filter(prices["close"], self.trend_filter_period))
        return base
```
A new rule type (e.g. a future V2 momentum rule) implements the same `target(prices)` signature
and plugs into the Strategy Lab page with zero page changes — satisfying LAB-10 literally.

### Pattern 3: Denser, independent-kind heatmap grid (D-05, D-06, D-07)

**What:** `core/grid.py::default_pairs()` only supports one `kinds` tuple applied to *both* legs
via `itertools.product`. The heatmap needs the *selected rule's* short kind and long kind held
fixed while periods vary independently over different ranges (short 5–60 step 5, long 100–250
step 10) — `default_pairs()` cannot express "short kind != long kind, different step/range per
leg" in one call.
**When to use:** Building the LAB-05 heatmap and the LAB-01 picker's bounded-range validation.
**Example:**
```python
# core/grid.py — new helper, sits next to default_pairs()
def heatmap_pairs(short_kind: str, long_kind: str,
                  short_range: range, long_range: range) -> list[tuple[MASpec, MASpec]]:
    shorts = [MASpec(short_kind, p) for p in short_range]
    longs = [MASpec(long_kind, p) for p in long_range]
    return list(product(shorts, longs))

# usage, matching D-06's grid shape
pairs = heatmap_pairs(selected_short.kind, selected_long.kind,
                      range(5, 61, 5), range(100, 251, 10))
grid = run_ma_grid(prices, pairs, cost_bps=cost_bps, start=window_start, end=window_end)
```
`run_ma_grid` itself needs no change — it already accepts an arbitrary `pairs` list.

### Pattern 4: IS/OOS split as a thin wrapper, not a new backtest path (D-12)

**What:** In-sample/out-of-sample is just two calls to the existing `run_backtest`/`summarise`
with different `start`/`end`, per the exact window rule in D-12 (OOS always runs to the latest
data regardless of the sidebar end date).
**Example:**
```python
# core/backtest.py — new helper
def is_oos_summary(prices: pd.DataFrame, target: pd.Series, split: str,
                   start: str, cost_bps: float = 0.0) -> tuple[dict, dict]:
    is_res = run_backtest(prices, target, cost_bps=cost_bps, start=start, end=split)
    oos_res = run_backtest(prices, target, cost_bps=cost_bps, start=split)  # end=None -> latest
    return summarise(is_res), summarise(oos_res)
```

### Pattern 5: Nightly validation gate (DATA-03, D-13)

**What:** Before overwriting `data/prices.parquet`, diff the newly fetched frame against the
currently-committed one over the overlapping date range. Any historical value outside a tight
tolerance (other than a single common `adj_close` rescale factor) fails the job.
**Example:**
```python
# core/config.py additions
@dataclass(frozen=True)
class Settings:
    # ... existing fields ...
    history_start: str = "1993-01-29"
    rewrite_tolerance_pct: float = 0.0001          # 0.01%
    adj_close_rescale_tolerance_pct: float = 0.0001

# jobs/refresh_prices.py (sketch)
def validate_snapshot(new: pd.DataFrame, old: pd.DataFrame, cfg) -> None:
    overlap = old.index.intersection(new.index)
    if len(new) < len(old):
        raise ValueError("row count shrank")
    for col in ("open", "high", "low", "close"):
        diff = (new.loc[overlap, col] / old.loc[overlap, col] - 1).abs()
        if (diff > cfg.rewrite_tolerance_pct).any():
            raise ValueError(f"{col} rewritten beyond tolerance")
    factor = (new.loc[overlap, "adj_close"] / old.loc[overlap, "adj_close"]).dropna()
    if factor.std() / factor.mean() > cfg.adj_close_rescale_tolerance_pct:
        raise ValueError("adj_close restated by more than a single common factor")
    expected_trading_days = pd.bdate_range(old.index[-1], new.index[-1])  # refine: US holidays
    gap = expected_trading_days.difference(new.index)
    if len(gap) > 0:
        raise ValueError(f"non-holiday gap(s) detected: {gap}")
```
Use `pandas_market_calendars` or a hand-maintained NYSE holiday list for the gap check if
`pd.bdate_range` false-positives on holidays — flagged in Open Questions, not yet verified this
session which approach the existing codebase prefers.

### Anti-Patterns to Avoid
- **Computing the 24-rule grid or the ~192-cell heatmap inside an uncached code path on every
  widget interaction.** Cache on `(start, end, cost_bps, basis, trend_filter, short_kind,
  long_kind)` with `st.cache_data`, per D-09.
- **Reaching for `st.markdown(..., unsafe_allow_html=True)` for anything the UI-SPEC's theme
  tokens or native widgets can already express** — explicitly ruled out in the UI-SPEC's
  Streamlit-Specific Contract §6.
- **Importing `jobs/` or `requests`/`yfinance` from any file under `app/`** — breaks DATA-05
  and the ephemeral-filesystem/no-secrets assumption outright.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry/backoff around `fetch_yfinance` and the nightly job's network step | A hand-rolled `for attempt in range(n): try/except/sleep` loop | `tenacity.retry(stop=stop_after_attempt(n), wait=wait_exponential(...))` | Battle-tested, handles jitter/backoff correctly, trivially testable by mocking the wrapped function; already verified installable in this session |
| Theming Plotly charts to match Streamlit's palette | Per-chart `fig.update_layout(colorway=[...])` hand-tuned to match `.streamlit/config.toml` | `st.plotly_chart(fig, theme="streamlit")` (never `theme=None`) | One config source of truth (`chartCategoricalColors`/`chartDivergingColors`), confirmed still supported in the current Streamlit config schema this session |
| Multipage navigation / URL routing | A hand-rolled sidebar radio + conditional page render | `st.navigation` + `st.Page` | Native, current, gives explicit titles/icons/URLs and sidebar grouping for free — confirmed current via live doc fetch this session |
| Sortino/Calmar ratio math | A pulled-in metrics library (`empyrical`, `quantstats`) just for two formulas | Hand-written functions in `core/metrics.py`, matching the existing `sharpe()`/`summarise()` style, each with a unit test | The formulas are ~10 lines each and the project explicitly keeps `core/` dependency-light; a "full-metrics expander" library is already named as out-of-scope for v1 (V2-05) |
| CI-loop prevention on the nightly data commit | A custom "detect if this is a bot commit" check in `ci.yml` | `paths-ignore: data/**` + pushing with the default `GITHUB_TOKEN` (not a PAT) | Both are first-class, officially documented GitHub Actions mechanisms, confirmed current this session — no custom logic needed |

**Key insight:** Nothing in this phase's "don't hand-roll" list is domain-specific finance logic
(that part — the backtest engine — is correctly already hand-rolled and tested in Phase 0). Every
item here is generic platform/retry/UI plumbing where a maintained library or a documented
platform feature is strictly safer than a bespoke equivalent.

## Common Pitfalls

### Pitfall 1: Assuming the stale `.planning/research/*.md` version pins are still accurate
**What goes wrong:** Those docs recommend `streamlit>=1.49`, `plotly>=5.24`, pin `yfinance` to
the `0.2.40`-era API. The actual PyPI-latest and actually-installed versions in this repo's
`.venv` are `streamlit 1.65.0`, `plotly 7.1.0`, `yfinance 1.7.0`, `pandas 3.0.6` — one to two
majors ahead in most cases.
**Why it happens:** Research docs were written once; the ecosystem moved since.
**How to avoid:** Pin `pyproject.toml` to floors that match what's *actually verified working*
this session (see Standard Stack), not the floors copied from the older research docs. Re-run
`pytest -q` and `ruff check .` after any dependency bump — both passed clean against the current
versions in this session.
**Warning signs:** A `pip install -e ".[dev]"` that silently resolves to much older versions than
what's on PyPI today, or a planner copying version numbers straight from `STACK.md` without
re-checking.

### Pitfall 2: Treating the LAB-05 heatmap as needing `on_select` click interaction
**What goes wrong:** `.planning/STATE.md`'s "Blockers/Concerns" flags "verify
`st.plotly_chart(on_select="rerun")` actually fires on the Strategy Lab heatmap" as a risk, citing
genuine, still-open Streamlit GitHub issues (#8760, #8933) about heatmap/imshow selection not
firing reliably.
**Why it happens:** The concern was written generically before CONTEXT.md's D-06/D-07 were
decided. Re-reading CONTEXT.md: the heatmap's selected cell is driven by the **sidebar picker**,
not by clicking the heatmap itself ("the selected rule's cell highlighted" — a static annotation,
not an interactive callback).
**How to avoid:** Do not build any `on_select="rerun"` handling for the Strategy Lab heatmap in
Phase 1 — render it as a plain `go.Heatmap` with a highlight annotation (e.g. a rectangle shape
or marker overlaid at the selected cell's coordinates) driven by `st.session_state`/sidebar
values, not by chart click events. This resolves the STATE.md concern **for this phase**; it
still applies to Phase 4's Event Explorer (which does need click-to-select on scatter markers,
not a heatmap, and scatter selection is confirmed to work).
**Warning signs:** Any task description that says "wire up heatmap click-to-select" for Phase 1
— that's scope creep against CONTEXT.md's explicit decision.

### Pitfall 3: `chartDivergingColors` expects a 10-color array; the UI-SPEC's `.streamlit/config.toml` only lists 3
**What goes wrong:** Current Streamlit docs (re-fetched this session) describe
`chartDivergingColors` as "an array of **ten** colors to use for diverging chart data." The
UI-SPEC's authoritative config block specifies only three: `["#C0152F", "#FFFFFF", "#1A7F37"]`.
**Why it happens:** The UI-SPEC was written assuming a simple red-white-green 3-stop scale (a
reasonable design intent), but Streamlit's theme engine may expect a denser array to interpolate
a smooth diverging colorscale for `theme="streamlit"`-themed Plotly heatmaps.
**How to avoid:** Verify rendering with exactly the UI-SPEC's 3-color array on a real heatmap
during implementation; if Streamlit does not smoothly interpolate 3 colors into 10 slots, either
(a) expand the array to 10 stops that still read as red→white→green (keep white dead-center), or
(b) bypass the theme token for this one chart and set the diverging colorscale directly in Plotly
(`colorscale=[[0, "#C0152F"], [0.5, "#FFFFFF"], [1, "#1A7F37"]]`) while leaving `theme="streamlit"`
on the call for every other chart element. Flag back to the UI checker if (b) is needed, since
the UI-SPEC says "never per-chart Plotly templates" — this would be a justified, documented
exception, not silent drift.
**Warning signs:** The heatmap's center (0% excess return) doesn't render as visually white/
neutral, or renders with banding instead of a smooth gradient.

### Pitfall 4: Running the nightly job's gap-check against `pd.bdate_range` naively flags US market holidays as gaps
**What goes wrong:** `pd.bdate_range` (business days) does not know about NYSE holidays
(Thanksgiving, Christmas, July 4th, etc.), so a validator that expects every weekday to have a
row will false-positive on every market holiday.
**Why it happens:** `bdate_range` is the obvious first reach for "every weekday," but SPY has no
trading data on US market holidays — those are expected, legitimate gaps.
**How to avoid:** Either vendor a small NYSE holiday list (few hundred dates since 1993, cheap to
hardcode or generate once) or use `pandas_market_calendars`'s NYSE calendar if adding that
dependency is acceptable — not yet verified against this project's dependency-minimalism
preference, flagged in Open Questions. At minimum, the validator must distinguish "missing a
known holiday" (expected, not a failure) from "missing an ordinary trading day" (DATA-03
failure).
**Warning signs:** The nightly job fails every time it runs near a US market holiday.

### Pitfall 5: Heatmap/rolling-start/IS-OOS panels silently re-introduce presentation-layer data-snooping even though the engine is correct
**What goes wrong (from `.planning/research/PITFALLS.md`, still applicable, re-confirmed this
session as not yet mitigated by any CONTEXT.md decision):** A visitor can read the heatmap's
"best cell" as a recommendation, defeating the entire honesty premise of the project
(`docs/PHASE0_FINDINGS.md`: 0/24 beat B&H).
**How to avoid:** Every Strategy Lab chart needs a one-line caveat caption (already partially
addressed by D-02's live-recount headline and the UI-SPEC's copy contract, but extend the same
discipline to the heatmap and scatter captions specifically — "best cell shown for reference, not
a recommendation").
**Warning signs:** Any Strategy Lab copy that reads like "this rule performed best" without a
caveat.

### Pitfall 6: `st.cache_data` with no `ttl` relies entirely on redeploy to bust the cache — confirm this actually happens on every nightly commit
**What goes wrong:** CLAUDE.md's override ("no ttl... each nightly data commit redeploys the app
and clears the cache") is correct per official Streamlit docs on *auto-redeploy-on-push for an
already-awake app*, but a long-lived, already-running session's cache is only cleared by a
container restart — confirmed this is Streamlit Cloud's actual redeploy mechanism (full process
restart), not an in-place cache invalidation. If Streamlit Cloud ever changes to a hot-reload
model instead of full restart, this assumption would silently break.
**How to avoid:** No code change needed now (the current behavior supports the no-ttl decision),
but document the reasoning in a code comment next to the cache decorators (as `ARCHITECTURE.md`
already recommends) so a future contributor doesn't "fix" perceived staleness by adding a TTL
that would mask a genuinely failed redeploy instead of catching it.
**Warning signs:** A visitor reports seeing yesterday's data right after a known nightly commit —
investigate redeploy logs, don't just add a TTL.

## Code Examples

### `.github/workflows/nightly.yml` skeleton (D-14, D-15, D-16)
```yaml
# Source: GitHub Actions official docs on GITHUB_TOKEN + paths-ignore, re-verified 2026-10-07
name: nightly
on:
  schedule:
    - cron: "30 21 * * 1-5"   # weekdays ~21:30 UTC
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: python -m jobs.refresh_prices   # exits non-zero on validation failure
      - name: Commit data if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/prices.parquet data/meta.json
          git diff --cached --quiet || git commit -m "data: nightly price refresh"
          git push
          # Uses the default GITHUB_TOKEN (checkout's default) -> this push will NOT
          # trigger ci.yml's `push` event per GitHub's own docs. paths-ignore below is
          # defense in depth in case a PAT is ever substituted.
```
```yaml
# .github/workflows/ci.yml — add this one line
on:
  push:
    paths-ignore: ["data/**"]
  pull_request:
```

### `core/metrics.py` additions (Sortino, Calmar)
```python
# Standard formulas — [ASSUMED], not tied to a specific library's exact implementation;
# matches the existing sharpe()/summarise() style and annualisation convention (√252).
def downside_deviation(equity: pd.Series, target: float = 0.0) -> float:
    r = equity.pct_change().dropna()
    downside = r[r < target]
    return float(((downside ** 2).mean()) ** 0.5 * math.sqrt(TRADING_DAYS)) if len(downside) else 0.0

def sortino(equity: pd.Series, rf_annual: float = 0.0) -> float:
    r = equity.pct_change().dropna() - rf_annual / TRADING_DAYS
    dd = downside_deviation(equity)
    return float(r.mean() * TRADING_DAYS / dd) if dd > 0 else float("nan")

def calmar(equity: pd.Series) -> float:
    mdd = max_drawdown(equity)
    return float(cagr(equity) / abs(mdd)) if mdd < 0 else float("nan")
```

### Overview KPI strip pattern (OVER-04)
```python
# app/pages/1_overview.py — per UI-SPEC §Streamlit-Specific Contract item 4
cols = st.columns(4, gap="medium")
kpis = [("YTD return", ytd_return, "normal"), ("Distance from ATH", dist_ath, "normal"),
        ("Current drawdown", cur_dd, "inverse"), ("20D realised vol", vol20, "off")]
for col, (label, value, delta_color) in zip(cols, kpis):
    with col:
        with st.container(border=True):
            st.metric(label, f"{value:.1%}" if delta_color != "off" else f"{value:.1%}")
```

## State of the Art

| Old Approach (stale docs / training assumption) | Current Approach (verified this session) | When Changed | Impact |
|--------------------------------------------------|---------------------------------------------|---------------|--------|
| `yfinance>=0.2.40`, `auto_adjust` default flip discourse framed around 0.2.x | `yfinance` is at **1.7.0**; `download()` still exposes `auto_adjust` and `multi_level_index` exactly as `core/data.py` already uses them | 1.x line released since the stale research was written | No code change needed in `core/data.py`; just update the `pyproject.toml` floor and re-verify after any future bump |
| `streamlit>=1.49,<2` | `streamlit` is at **1.65.0**, still pre-2.0, `st.navigation`/`st.Page`/`st.cache_data`/config.toml theme keys all confirmed unchanged in current docs | Ongoing 1.5x→1.6x minor releases | None — raise the floor, no API migration needed |
| `plotly>=5.24` | `plotly` is at **7.1.0** — two majors ahead | 6.0 (Mapbox deprecation, `titlefont`→`title.font`, `heatmapgl`/`pointcloud`/`transforms` removed), 7.0 (Mapbox traces fully removed) | None of the removed features are used by this app (candlestick, vrect, Scattergl, Heatmap all unaffected) — verified by direct import test this session |
| "Heatmap click-to-select is a Phase 1 risk" (STATE.md) | Not applicable to Phase 1 — CONTEXT.md's D-06/D-07 drive the highlighted cell from the sidebar, not a chart click | Resolved by CONTEXT.md decisions, not by a Streamlit fix | Removes a flagged blocker from this phase's scope entirely |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Sortino/Calmar formulas as written (downside deviation vs 0%, `√252` annualisation, Calmar = CAGR / \|maxDD\|) are the standard, uncontroversial definitions for this context | Code Examples | Low — these are the textbook definitions; a different risk-free/target convention would only shift the Sortino denominator slightly, easily corrected by a test asserting the chosen convention |
| A2 | `pd.bdate_range`-based gap detection needs a real NYSE holiday list (not yet selected: hand-vendored list vs. `pandas_market_calendars` dependency) | Common Pitfalls #4, Open Questions | Medium — a wrong choice either adds an unreviewed dependency or ships a nightly job that false-fails on every holiday; must be resolved before DATA-03 is implemented |
| A3 | Streamlit Community Cloud's deploy pipeline accepts `pyproject.toml` directly (pip-installs it) without a generated `requirements.txt` | Standard Stack, Phase Requirements (OPS-01) | Medium — if wrong, first deploy fails until a `requirements.txt` is generated/committed; easy fallback, not a blocker to decide now, but should be tested on the very first real deploy |
| A4 | `chartDivergingColors`'s current "ten colors" documentation requirement will actually render acceptably with the UI-SPEC's 3-color array (Streamlit may interpolate gracefully) | Common Pitfalls #3 | Low-Medium — cosmetic only; worst case is a non-smooth diverging scale on one chart, fixed by either expanding the array or setting the Plotly colorscale directly for that one chart |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **NYSE holiday calendar source for the DATA-03 gap check**
   - What we know: `pd.bdate_range` alone will false-positive on every US market holiday;
     `pandas_market_calendars` would solve this cleanly but is not currently a project dependency.
   - What's unclear: Whether the project prefers a hand-vendored static holiday list (zero new
     dependency, needs occasional manual updates for new years) or adding
     `pandas_market_calendars` (correct forever, one more dependency to audit).
   - Recommendation: Hand-vendor a static list for 1993–2030 (a few hundred known dates, cheap to
     generate once from any authoritative NYSE holiday source) unless the planner decides the
     dependency is worth it — flag for the planner to decide explicitly, not left implicit.

2. **Streamlit Community Cloud's exact dependency-file detection (`pyproject.toml` vs `requirements.txt`)**
   - What we know: Community Cloud's docs describe installing from a repo's dependency files but
     the previous research pass couldn't find an explicit enumeration of supported formats.
   - What's unclear: Whether `pip install -e .` against `pyproject.toml` alone is sufficient on
     first real deploy, or whether a generated `requirements.txt` is needed as a fallback.
   - Recommendation: Treat `pyproject.toml`-only as the default; capture the "Manage app →
     Dependencies" log on the very first real deploy as the actual confirmation, and prepare (but
     don't pre-emptively commit) a `requirements.txt` fallback.

3. **`st.form`/"Update grid" debounce fallback (D-09)**
   - What we know: ~192 heatmap backtests + 24 headline/scatter backtests per sidebar change,
     cached by primitive inputs, is expected to be fast on pure pandas vector ops over ~8,500
     rows — not independently benchmarked in this research session (no Streamlit runtime was
     exercised).
   - What's unclear: Actual wall-clock time on Streamlit Community Cloud's shared, resource-
     limited container (PITFALLS.md flags ~1–2.7GB memory ceilings as a known constraint).
   - Recommendation: Implement without the `st.form` fallback first (per D-09's explicit
     instruction), but have the plan include a quick manual timing check during implementation
     before declaring LAB-05 done — add the fallback only if that check shows it's needed.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 (`.venv`) | Everything | ✓ | 3.12.15 | — |
| streamlit | app/ | ✓ (installed this session) | 1.65.0 | — |
| plotly | app/ | ✓ (installed this session) | 7.1.0 | — |
| tenacity | jobs/refresh_prices.py | ✓ (installed this session) | 9.2.1 | — |
| pandas, numpy, pyarrow, requests, yfinance | core/ | ✓ (already installed) | 3.0.6 / 2.5.3 / 25.0.1 / 2.34.2 / 1.7.0 | — |
| Internet access (yfinance live fetch) | jobs/refresh_prices.py, local dev re-fetch | Not tested this session (no live fetch attempted — scope was package/API verification only) | — | `data/prices.parquet` already has a committed Phase 0 snapshot; Overview/Strategy Lab dev can proceed against it without a live fetch |
| GitHub Actions runner (ubuntu-latest) | nightly.yml, ci.yml | ✓ (standard GitHub-hosted runner, no special access needed) | — | — |

**Missing dependencies with no fallback:** none identified.
**Missing dependencies with fallback:** Internet access for a live yfinance fetch — the existing
committed `data/prices.parquet` snapshot (2010-01-04 to 2026-10-07, 4,216 rows per
`docs/PHASE0_FINDINGS.md`) is sufficient to build and test the Overview/Strategy Lab pages without
a live fetch; only the 1993-backfill and the nightly job itself need real network access, and
those run in GitHub Actions (confirmed has network) or require a deliberate local run.

## Validation Architecture

> Included per explicit instruction for this research pass, even though
> `.planning/config.json`'s `workflow.nyquist_validation` is `false` — the orchestrator's task
> brief for this phase requested it explicitly.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (already configured) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| Quick run command | `.venv/python.exe -m pytest -q` (currently 13 tests, 0.3–0.4s) |
| Full suite command | `.venv/python.exe -m pytest -q` (no slow/integration split exists yet — same command until `app/` tests are added, see Wave 0 Gaps) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Job fetches 1993-01-29 → latest | unit (mocked fetch) | `pytest tests/test_refresh_prices.py -x` | ❌ Wave 0 |
| DATA-02 | `auto_adjust=False`, flat columns, retries, non-zero exit on final failure | unit | `pytest tests/test_data.py::test_fetch_yfinance_pins_auto_adjust -x` | ❌ Wave 0 (extend existing `core/data.py` coverage, currently no dedicated test file found in `tests/`) |
| DATA-03 | Gap/shrink/rewrite validation gate | unit, synthetic fixtures | `pytest tests/test_validate_snapshot.py -x` | ❌ Wave 0 |
| DATA-04 | `meta.json` schema fields present | unit | `pytest tests/test_storage.py::test_meta_schema -x` | ❌ Wave 0 |
| DATA-05 | No network import in `app/` | static check (import-only smoke test) | `pytest tests/test_app_purity.py -x` | ❌ Wave 0 |
| OVER-01..06 | Overview computations (KPIs, drawdown regimes, table) | unit | `pytest tests/test_regimes.py tests/test_kpis.py -x` | ❌ Wave 0 |
| LAB-01..10 | Strategy Lab engine extensions (`Strategy`, `heatmap_pairs`, `is_oos_summary`, Sortino/Calmar) | unit | `pytest tests/test_grid.py tests/test_metrics.py tests/test_signals.py -x` | Partial — `tests/test_grid.py`, `tests/test_signals.py` exist for Phase 0 scope; new cases needed |
| LAB-09 | Default view reproduces "0 of 24" | regression | `pytest tests/test_grid.py::test_default_window_zero_of_24 -x` | ❌ Wave 0 — this is the single most important new test (mirrors `docs/PHASE0_FINDINGS.md`'s headline) |
| OPS-05 | CI-loop guard config present | config lint (no pytest — a workflow YAML check) | manual/CI review of `ci.yml`'s `paths-ignore` | N/A |

### Sampling Rate
- **Per task commit:** `.venv/python.exe -m pytest -q` (full suite — currently sub-second,
  stays cheap through this phase since everything is pure pandas, no network/LLM calls)
- **Per wave merge:** Same command, plus `ruff check .`
- **Phase gate:** Full suite green, plus a manual re-run of
  `python -m scripts.rerun_notebook_grid` to confirm the Strategy Lab's default view still prints
  "0 of 24" against the live 1993-backfilled snapshot (not just the 2010-starting one used in
  Phase 0's findings).

### Wave 0 Gaps
- [ ] `tests/test_refresh_prices.py` — DATA-01, DATA-02 (mock `fetch_yfinance`, assert retry
  behavior and non-zero exit)
- [ ] `tests/test_validate_snapshot.py` — DATA-03 (synthetic gap/shrink/rewrite fixtures)
- [ ] `tests/test_storage.py` — DATA-04, DATA-05 (meta schema, override-free read path, no
  Streamlit import)
- [ ] `tests/test_app_purity.py` — DATA-05 (static assertion that no file under `app/` imports
  `requests`, `yfinance`, or `jobs`)
- [ ] `tests/test_regimes.py`, `tests/test_kpis.py` — OVER-01..06
- [ ] `tests/test_metrics.py` — Sortino/Calmar (LAB-04), extending the existing bare `core/metrics.py`
  (no dedicated test file currently exists for it — verified via `ls tests/`)
- [ ] Extend `tests/test_grid.py` — `heatmap_pairs()`, `is_oos_summary()`, and the "0 of 24 at
  default settings" regression test
- [ ] Extend `tests/test_signals.py` — `Strategy` Protocol conformance for `MACrossoverStrategy`

## Security Domain

### Applicable ASVS Categories (Level 1)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V1 Architecture | Yes | `core/` purity rule (no Streamlit/network imports outside `data.py`/`jobs/`) is itself an ASVS-aligned trust-boundary control — enforce via the new `tests/test_app_purity.py` |
| V2 Authentication | No | Public, read-only app; no accounts, no login (REQUIREMENTS.md "Out of Scope: user accounts") |
| V3 Session Management | No | No server-side session state beyond Streamlit's own ephemeral widget state; nothing sensitive stored |
| V4 Access Control | No | No privileged actions in the app; `jobs/review_events.py` (Phase 3) is explicitly local-only, not reachable from the deployed app |
| V5 Input Validation | Yes | Sidebar widgets (date range, cost bps, MA periods) must be bounded (D-05's 5–60/50–250 ranges, short<long enforcement) to prevent a visitor from crafting an input that causes an unbounded/slow computation or an unhandled exception (e.g., a date range shorter than the slowest MA's warm-up — already a known bug class per `docs/SPEC.md`'s notebook audit #3/#8) |
| V6 Cryptography | No | No secrets, no crypto operations in this phase (ANTHROPIC_API_KEY doesn't exist yet — Phase 3) |
| V14 Configuration | Yes | GitHub Actions secret hygiene: `ci.yml` must never run with secrets exposed to fork `pull_request` triggers (not an issue this phase — no secrets are used yet, but `nightly.yml` should stay on `schedule`/`workflow_dispatch` only, never `pull_request_target`, establishing the safe pattern before Phase 3 adds a real API key) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Visitor selects a degenerate date range / MA period combo that triggers an unhandled exception or very slow recompute (e.g., start date leaves fewer bars than the slowest MA's period) | Denial of Service (resource exhaustion on a shared Streamlit Cloud container) | Bound every sidebar numeric/date input at the widget level (D-05's ranges); catch the "not enough history" case explicitly and show the UI-SPEC's defined `st.warning()` copy instead of letting an unhandled exception crash the session — this is literally the bug class Phase 0's audit #8/`core/grid.py`'s off-by-one fix already addressed once; don't reintroduce it in the UI layer |
| A future contributor adds a workflow trigger (`pull_request_target`, or a fork-sourced `pull_request` with `secrets.ANTHROPIC_API_KEY` in scope) before Phase 3 | Information Disclosure (secret exfiltration via a malicious fork PR) | Not yet a live risk (no API key exists this phase), but `nightly.yml` must be authored now on `schedule`/`workflow_dispatch` only, establishing the safe pattern `.planning/research/PITFALLS.md`'s Security Mistakes table already flags for Phase 3 |
| Tampering with the committed `data/prices.parquet` outside the validated job path (e.g., a manual bad commit bypassing `validate_snapshot`) | Tampering | DATA-03's validation gate only runs inside `jobs/refresh_prices.py` — it cannot stop a manual `git commit` that bypasses the job entirely. Out of scope to fully prevent (no branch-protection requirement given in CONTEXT.md), but worth noting as a residual risk, not a false sense of security from "the job validates everything" |

## Sources

### Primary (HIGH confidence)
- [docs.streamlit.io — st.navigation](https://docs.streamlit.io/develop/api-reference/navigation/st.navigation) — re-fetched 2026-10-07, confirms current `st.navigation`/`st.Page` syntax, dict-based sectioning, `pages/`-lockout behavior
- [docs.streamlit.io — Caching overview](https://docs.streamlit.io/develop/concepts/architecture/caching) — re-fetched 2026-10-07, confirms `ttl` semantics and cache-key hashing on function arguments
- [docs.streamlit.io — config.toml theme keys](https://docs.streamlit.io/develop/api-reference/configuration/config.toml) — re-fetched 2026-10-07, confirms `chartCategoricalColors`/`chartSequentialColors`/`chartDivergingColors` still supported; `chartDivergingColors` documented as expecting a 10-color array (see Pitfall 3)
- [docs.github.com — Triggering a workflow](https://docs.github.com/en/actions/using-workflows/triggering-a-workflow) — re-fetched 2026-10-07, confirms `GITHUB_TOKEN`-authored push events don't trigger further workflow runs, and `paths-ignore` skips a workflow only when *all* changed paths match
- [plotly.com — v6 migration guide](https://plotly.com/python/v6-migration/) and [v7 migration guide](https://plotly.com/python/v7-migration/) — confirms the only breaking changes in the 5.24→7.1 jump (Mapbox traces, `heatmapgl`, `pointcloud`, legacy `transforms`) don't touch this app's usage
- Local `.venv` verification this session: `pip index versions` for streamlit/plotly/tenacity/yfinance; `pip install` of streamlit/plotly/tenacity into the actual project `.venv`; `python -c "import ..."` smoke tests for Candlestick/vrect/Scattergl; `pytest -q` (13 passed) and `ruff check .` (clean) re-run after installs; `help(yf.download)` signature inspection; `slopcheck install streamlit plotly tenacity` (all `[OK]`)
- `core/data.py`, `core/backtest.py`, `core/metrics.py`, `core/grid.py`, `core/signals.py`, `core/indicators.py`, `core/config.py`, `tests/*.py` (this repo, read directly) — primary source for existing conventions this phase extends

### Secondary (MEDIUM confidence)
- [GitHub streamlit/streamlit #8760](https://github.com/streamlit/streamlit/issues/8760), [#8933](https://github.com/streamlit/streamlit/issues/8933) — WebSearch-surfaced, cross-referenced against this project's own prior `.planning/research/PITFALLS.md` citation of the same issues; confirms the heatmap `on_select` gap is still a live, open concern in the Streamlit repo (irrelevant to Phase 1 per Pitfall 2's resolution, relevant to Phase 4)
- [GitHub stefanzweifel/git-auto-commit-action](https://github.com/stefanzweifel/git-auto-commit-action) — WebSearch-surfaced, confirms v7.2.0 as of June 2026, actively maintained; not independently verified via a registry-equivalent tool (GitHub Actions aren't on a package registry slopcheck covers)

### Tertiary (LOW confidence)
- Sortino/Calmar exact formula conventions (Code Examples) — standard textbook definitions, not verified against a specific named authoritative source in this session; flagged in Assumptions Log (A1)
- `pandas_market_calendars` vs. hand-vendored NYSE holiday list tradeoff (Open Questions #1) — not independently resolved this session, left as an explicit planner decision

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version claim in this doc was independently re-verified against
  `pip index versions` and/or a local install+import+test in this session, not just copied from
  prior research docs.
- Architecture: HIGH — directly extends the already-built, already-tested `core/` package's own
  conventions; the new patterns (Strategy protocol, heatmap_pairs, is_oos_summary,
  validate_snapshot) are small, consistent extensions of existing shapes, not novel designs.
- Pitfalls: MEDIUM-HIGH — most are re-confirmed against current official docs or this session's
  own tool runs; the Sortino/Calmar formula convention and the NYSE-holiday-list decision remain
  genuinely open (see Assumptions Log / Open Questions), not just unverified claims.

**Research date:** 2026-10-07
**Valid until:** 30 days for the Streamlit/Plotly/tenacity/yfinance version pins (fast-moving
PyPI ecosystem); the architecture/pattern guidance is stable for the life of Phase 1 regardless
of minor version drift.
