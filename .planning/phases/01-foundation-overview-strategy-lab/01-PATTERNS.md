# Phase 1: Foundation, Overview & Strategy Lab - Pattern Map

**Mapped:** 2026-10-07
**Files analyzed:** 24 (new + modified)
**Analogs found:** 15 exact/in-repo / 24 total (9 have no in-repo analog — new UI/CI layer; RESEARCH.md Code Examples are the fallback pattern source for those)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `core/storage.py` (new) | utility (I/O) | file-I/O | `core/data.py` (`read_prices`/`write_prices`) | exact — same module family, same author intent, just Streamlit-caller-agnostic |
| `core/config.py` (extend) | config | CRUD (read config) | `core/config.py` itself (existing `Settings`) | exact — additive fields on an existing dataclass |
| `core/grid.py` (extend: `heatmap_pairs`) | utility/service | transform/batch | `core/grid.py` itself (`default_pairs`, `run_ma_grid`) | exact — same file, same shape |
| `core/metrics.py` (extend: `sortino`, `calmar`, `downside_deviation`) | utility | transform | `core/metrics.py` itself (`sharpe`, `cagr`, `max_drawdown`) | exact — same file, same style |
| `core/backtest.py` (extend: `is_oos_summary`) | service | transform | `core/grid.py::run_ma_grid` (two-call wrapper over `run_backtest`+`summarise`) | exact — same composition pattern, different file |
| `core/signals.py` (extend: `Strategy` Protocol, `MACrossoverStrategy`) | service/model | transform | `core/signals.py` itself (`ma_crossover`, `trend_filter`, `combine_all`) | exact — same file, same target-exposure contract |
| `core/validate.py` or `core/data.py` addition (`validate_snapshot`, DATA-03) | utility | batch/validation | `core/backtest.py::run_backtest` (pure function, raises `ValueError` on invalid input) | role-match — no validation-gate precedent exists; error-raising convention borrowed from `run_backtest` |
| `jobs/refresh_prices.py` (new) | service (job) | file-I/O + event-driven (scheduled) | `scripts/rerun_notebook_grid.py` | role-match — closest existing "argparse + `core.data` fetch/write + `__main__` guard" script in the repo |
| `.github/workflows/nightly.yml` (new) | config | event-driven (scheduled) | `.github/workflows/ci.yml` | exact — same YAML skeleton (`runs-on`, `actions/checkout`, `actions/setup-python`, `pip install -e ".[dev]"`) |
| `.github/workflows/ci.yml` (modify: `paths-ignore`) | config | event-driven | `.github/workflows/ci.yml` itself | exact — one-line addition to existing file |
| `app/Home.py` (new) | controller/router | request-response | none in repo | no analog — first Streamlit entrypoint; use RESEARCH.md Pattern 1 + UI-SPEC §Streamlit-Specific Contract item 1 |
| `app/components/sidebar.py` (new) | component | request-response | none in repo | no analog — first Streamlit widget module; use RESEARCH.md Pattern 1 (`@st.cache_data` wrapper shape) |
| `app/components/charts.py` (new) | component | transform | none in repo | no analog — first Plotly figure-builder module; use RESEARCH.md Code Examples + UI-SPEC color/theme tokens |
| `app/pages/1_overview.py` (new) | component/page | request-response | none in repo | no analog — use RESEARCH.md "Overview KPI strip pattern" + UI-SPEC §4/§5 |
| `app/pages/2_strategy_lab.py` (new) | component/page | request-response | none in repo | no analog — use RESEARCH.md Patterns 2-4 + D-01..D-12 |
| `.streamlit/config.toml` (new) | config | — | none in repo | no analog — values are fully specified verbatim in UI-SPEC §`.streamlit/config.toml` |
| `pyproject.toml` (modify: add streamlit/plotly/tenacity) | config | — | `pyproject.toml` itself | exact — additive dependency entries |
| `data/meta.json` (new, written by job) | model (data file) | file-I/O | `data/prices.parquet` (written by `core/data.py::write_prices`) | role-match — same "job writes, app reads" contract, JSON instead of parquet |
| `tests/test_refresh_prices.py` (new) | test | file-I/O | `tests/test_backtest.py` (fixture-driven, hand-checked assertions) | role-match |
| `tests/test_validate_snapshot.py` (new) | test | batch | `tests/test_backtest.py` + `tests/test_indicators.py` (synthetic-fixture style) | role-match |
| `tests/test_storage.py` (new) | test | file-I/O | `tests/test_grid.py` (small, single-assertion-focused) | role-match |
| `tests/test_app_purity.py` (new) | test | static check | none in repo | no analog — new static-import-check pattern, sketch below |
| `tests/test_metrics.py` (new, Sortino/Calmar) | test | transform | `tests/test_backtest.py::test_max_drawdown_known_series` (hand-computed numeric assertion) | exact |
| `tests/test_grid.py` (extend: `heatmap_pairs`, `is_oos_summary`, "0 of 24" regression) | test | transform | `tests/test_grid.py` itself | exact |
| `tests/test_signals.py` (extend: `Strategy` Protocol conformance) | test | transform | `tests/test_signals.py` itself | exact |

## Pattern Assignments

### `core/storage.py` (utility, file-I/O)

**Analog:** `core/data.py`

**Imports pattern** (`core/data.py` lines 1-12):
```python
"""Price loading and storage.

Network calls live here and are only used by jobs/scripts, never by the Streamlit app.
The app reads the committed parquet snapshot through `read_prices`.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests
```
Copy the module-docstring convention (state the purity boundary in the first lines) and the
`from __future__ import annotations` + stdlib-then-third-party import ordering. `core/storage.py`
must NOT import `requests`/`yfinance` — only `pandas`, `pathlib.Path`, `json`, and
`core.data.read_prices`.

**Core read/write pattern** (`core/data.py` lines 89-101, `write_prices`/`read_prices`):
```python
def write_prices(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["source"] = df.attrs.get("source", "unknown")
    out.to_parquet(path)


def read_prices(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    source = df["source"].iloc[-1] if "source" in df.columns else "unknown"
    df = df.drop(columns=["source"], errors="ignore")
    df.attrs["source"] = source
    return df
```
`core/storage.py::load_prices`/`load_meta` should be thin wrappers in this exact style — reuse
`read_prices` directly (per CONTEXT.md's "Reusable Assets"), add a `load_meta(path) -> dict` doing
`json.loads(path.read_text())`, mirroring the "one function, one file format" granularity above.

**Error handling pattern:** None present in `read_prices`/`write_prices` — they let `pd.read_parquet`/
`FileNotFoundError` propagate uncaught. Follow the same "let it raise" convention in `core/storage.py`;
the UI-SPEC's "No market data yet" empty state (line 113-114) is handled at the `app/` call site
(`try/except FileNotFoundError`), not inside `core/storage.py`.

---

### `core/config.py` (config, additive)

**Analog:** `core/config.py` itself

**Current shape** (lines 11-22):
```python
@dataclass(frozen=True)
class Settings:
    ticker: str = "SPY"
    start: str = "2010-01-01"
    short_periods: tuple[int, ...] = (10, 20, 50)
    long_periods: tuple[int, ...] = (100, 200)
    ma_kinds: tuple[str, ...] = ("sma", "ema")
    cost_bps: float = 0.0  # one-way cost per unit of turnover, in basis points
    prices_path: Path = field(default=DATA_DIR / "prices.parquet")


SETTINGS = Settings()
```
Add fields in the same style (inline comment explaining units/semantics where not obvious):
`history_start: str = "1993-01-29"`, `meta_path: Path = field(default=DATA_DIR / "meta.json")`,
`rewrite_tolerance_pct: float = 0.0001`, `adj_close_rescale_tolerance_pct: float = 0.0001`,
`heatmap_short_range`/`heatmap_long_range` (as `tuple[int, int, int]` start/stop/step, matching
the existing `tuple[int, ...]` idiom), `default_window` (start/end strings per D-01),
`default_split: str = "2022-12-16"` (D-12). Per CLAUDE.md: "Thresholds and defaults go in
`core/config.py`, not inside functions" — every numeric literal introduced by D-01 through D-13
belongs here, not hardcoded in `app/` or `jobs/`.

---

### `core/grid.py::heatmap_pairs` (service, transform)

**Analog:** `core/grid.py::default_pairs` (same file, lines 14-19)

```python
def default_pairs(short_periods=(10, 20, 50), long_periods=(100, 200),
                  kinds=("sma", "ema")) -> list[tuple[MASpec, MASpec]]:
    """Same 24 combinations as the 2022 notebook."""
    shorts = [MASpec(k, p) for k in kinds for p in short_periods]
    longs = [MASpec(k, p) for k in kinds for p in long_periods]
    return list(product(shorts, longs))
```
Copy this exact shape for `heatmap_pairs(short_kind, long_kind, short_range, long_range)` (per
RESEARCH.md Pattern 3) — same `itertools.product` composition, same `list[tuple[MASpec, MASpec]]`
return type so it drops straight into the existing `run_ma_grid(prices, pairs, cost_bps=...)`
with zero changes to `run_ma_grid` itself (lines 22-38).

---

### `core/metrics.py::sortino`, `::calmar` (utility, transform)

**Analog:** `core/metrics.py::sharpe`, `::max_drawdown`, `::cagr` (same file, lines 17-31)

```python
def max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1).min())


def sharpe(equity: pd.Series, rf_annual: float = 0.0) -> float:
    r = equity.pct_change().dropna() - rf_annual / TRADING_DAYS
    sd = r.std()
    return float(r.mean() / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else float("nan")
```
Copy this exact style: one-line pure function, `float(...)` cast on return, `TRADING_DAYS = 252`
constant already defined at module level (line 10) — reuse it, don't redefine. Guard
divide-by-zero with the same `if sd > 0 else float("nan")` idiom (`sortino` guards on `dd > 0`,
`calmar` guards on `mdd < 0`, per RESEARCH.md's Code Examples). Add both to the `summarise()` dict
(lines 34-48) alongside `sharpe`, following the existing `"sharpe": sharpe(s)` entry pattern —
add `"sortino": sortino(s)` and `"calmar": calmar(s)`.

**Error handling:** No try/except anywhere in `core/metrics.py` — all guards are inline
conditional expressions returning `float("nan")`. Match this; do not introduce exceptions here.

---

### `core/backtest.py::is_oos_summary` (service, transform)

**Analog:** `core/grid.py::run_ma_grid` (two-call composition over `run_backtest` + `summarise`, lines 22-38)

```python
def run_ma_grid(prices, pairs, cost_bps=0.0, start=None, end=None):
    targets = {...}
    ...
    for name, target in targets.items():
        res = run_backtest(prices, target, cost_bps=cost_bps, start=common_start, end=end)
        rows[name] = summarise(res)
    return pd.DataFrame(rows).T.sort_values("excess_total_return", ascending=False)
```
`is_oos_summary` is the same "call `run_backtest` + `summarise` twice with different
`start`/`end`" shape, just returning a `tuple[dict, dict]` instead of a `DataFrame`. Per D-12,
the OOS call must omit `end` entirely (`run_backtest(prices, target, cost_bps=cost_bps, start=split)`)
so it naturally runs to `prices.index[-1]` — `run_backtest`'s own `.loc[start:end]` (line 45) already
treats `end=None` as "to the end", so no new slicing logic is needed.

---

### `core/signals.py::Strategy`, `::MACrossoverStrategy` (model/service, transform)

**Analog:** `core/signals.py` itself (`ma_crossover`, `trend_filter`, `combine_all`, lines 19-34)

```python
def ma_crossover(close: pd.Series, short: MASpec, long: MASpec) -> pd.Series:
    return crossover_target(short.compute(close), long.compute(close)).rename(
        f"{short.label}__{long.label}"
    )


def trend_filter(close: pd.Series, period: int = 200) -> pd.Series:
    """In the market only while the close is above its `period`-day SMA."""
    return crossover_target(close, sma(close, period)).rename(f"close__sma{period}")
```
`MACrossoverStrategy.target(prices)` must call these two functions exactly as written (never
reimplement crossover math), composing via the existing `combine_all` (lines 30-34) when a trend
filter is active — this is RESEARCH.md Pattern 2, already matching the file's own composition
style (`crossover_target` → `ma_crossover`/`trend_filter` → `combine_all`). Naming convention to
copy: `f"{short.label}__{long.label}"` (double-underscore join), extended with
`f"__trend{trend_filter_period}"` when present, per RESEARCH.md's example.

**Contract note:** Every function in this file returns a target exposure series (1.0/0.0/NaN) per
the module docstring (lines 1-6) — `MACrossoverStrategy.target()` must return the same shape,
satisfying `core/backtest.py::run_backtest`'s `target` parameter contract unchanged.

---

### `core/validate.py` or `core/data.py::validate_snapshot` (utility, batch validation — DATA-03)

**Analog:** `core/backtest.py::run_backtest` (pure function, raises on invalid input, lines 38-47)

```python
df = pd.DataFrame({"r": interval_ret, "exp": exposure}).loc[start:end].dropna()
if df.empty:
    raise ValueError("No overlapping data between prices and target in the window")
```
No existing validation-gate precedent exists in the codebase; the closest convention is
`run_backtest`'s "raise `ValueError` with a descriptive message, no custom exception classes" — follow
that exact idiom for every D-13 failure branch (row-count shrink, OHLC rewrite beyond tolerance,
non-common-factor `adj_close` restatement, non-holiday gap). RESEARCH.md's Pattern 5 sketch
(lines 405-421 of 01-RESEARCH.md) is the concrete starting point:
```python
def validate_snapshot(new: pd.DataFrame, old: pd.DataFrame, cfg) -> None:
    overlap = old.index.intersection(new.index)
    if len(new) < len(old):
        raise ValueError("row count shrank")
    for col in ("open", "high", "low", "close"):
        diff = (new.loc[overlap, col] / old.loc[overlap, col] - 1).abs()
        if (diff > cfg.rewrite_tolerance_pct).any():
            raise ValueError(f"{col} rewritten beyond tolerance")
    ...
```
Place it in `core/data.py` (next to `fetch_yfinance`/`load_prices`, since it only concerns price
data) rather than a new file, unless the planner prefers a dedicated `core/validate.py` for
test-file-naming symmetry with `tests/test_validate_snapshot.py` — either is consistent with
`core/`'s existing flat, one-concern-per-file layout; no strong precedent forces one over the
other. Resolve the NYSE-holiday-gap check (RESEARCH.md Open Question 1) with a hand-vendored
static list in `core/config.py` or alongside `validate_snapshot`, not a new dependency, per the
project's "Don't Hand-Roll" table's own bias toward minimal dependencies for small, bounded logic.

---

### `jobs/refresh_prices.py` (service/job, file-I/O + scheduled)

**Analog:** `scripts/rerun_notebook_grid.py`

**Imports + structure pattern** (lines 1-20):
```python
"""Re-run the 2022 notebook's 24-rule MA grid with the corrected engine.
...
"""
from __future__ import annotations

import argparse

import pandas as pd

from core.config import SETTINGS
from core.data import load_prices, to_total_return, write_prices
from core.grid import default_pairs, rolling_start, run_ma_grid
from core.indicators import MASpec
```
Copy the module-docstring-with-usage-examples convention, `argparse.ArgumentParser()` for any
CLI flags (even though `jobs/refresh_prices.py` is cron-invoked with no flags per D-16's scope,
keep the `if __name__ == "__main__": main()` guard for local manual runs), and the
`from core.config import SETTINGS` / `from core.data import ...` import style.

**Core fetch+write pattern** (lines 32-37):
```python
raw = load_prices(SETTINGS.ticker, start=SETTINGS.start)
print(f"Loaded {len(raw)} rows from {raw.attrs['source']} "
      f"({raw.index[0].date()} to {raw.index[-1].date()})")
if args.save:
    write_prices(raw, SETTINGS.prices_path)
```
`jobs/refresh_prices.py` replaces `load_prices` (which tries yfinance-then-stooq, D-17 removes
the stooq fallback) with a direct `tenacity`-wrapped `fetch_yfinance(ticker, start=cfg.history_start)`
call, then `validate_snapshot(new, core.storage.load_prices(cfg.prices_path))` before calling
`write_prices` + a new `write_meta(...)`. On validation failure or final-retry exhaustion, `exit(1)`
(no existing precedent for non-zero exit in this repo — this is new, required by DATA-02/D-13; use
`raise SystemExit(1)` after logging the error, since `scripts/rerun_notebook_grid.py` has no
error path to copy from).

**Error handling (new, no repo precedent — use RESEARCH.md "Don't Hand-Roll"):**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_with_retry(ticker: str, start: str) -> pd.DataFrame:
    return fetch_yfinance(ticker, start=start)
```

---

### `.github/workflows/nightly.yml` (config, scheduled)

**Analog:** `.github/workflows/ci.yml` (entire file, 19 lines)

```yaml
name: ci

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -q
```
Copy the `runs-on: ubuntu-latest` + `actions/checkout@v4` + `actions/setup-python@v5` (with
`python-version: "3.12"`, `cache: pip`) + `pip install -e ".[dev]"` skeleton verbatim. Diverge
only in `on:` (→ `schedule`/`workflow_dispatch` per D-14, never `push`/`pull_request`), add
`permissions: contents: write`, replace the test/lint steps with
`python -m jobs.refresh_prices`, and add the commit+push step (RESEARCH.md's Code Examples
section has the full skeleton, reproduced there with the exact D-15 `GITHUB_TOKEN` reasoning).

**Modify `ci.yml` itself** (D-15): add `paths-ignore: ["data/**"]` under the existing `push:` key,
in the same two-space YAML indentation already used for `on:` / `jobs:` / `steps:`.

---

### `app/Home.py`, `app/components/*.py`, `app/pages/*.py` (no in-repo analog)

No Streamlit code exists anywhere in this repo yet — these are genuinely new files with no
same-stack analog to copy structurally. Use **RESEARCH.md's Pattern 1, 2 and the "Overview KPI
strip pattern" Code Example verbatim** (01-RESEARCH.md lines 283-317, 604-614) as the pattern
source, combined with **UI-SPEC's §Streamlit-Specific Contract items 1-6** (copy/caching/chart/
layout rules) as the binding contract. Key excerpt to carry forward (RESEARCH.md lines 304-316):
```python
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
`core/storage.py` must be called ONLY from inside `app/`-level `@st.cache_data`-wrapped functions
— never call it uncached per page render, and never call `core.data`/`jobs` from any file under
`app/` (enforced by the new `tests/test_app_purity.py`, see below).

---

### Test files

**Analog for `tests/test_metrics.py`, `tests/test_refresh_prices.py`, `tests/test_validate_snapshot.py`:**
`tests/test_backtest.py` (lines 1-47) — fixture-driven (`tiny_prices`/`random_prices` from
`tests/conftest.py`), one assertion-dense test per behavior, hand-computed expected values with
`pytest.approx`:
```python
def test_max_drawdown_known_series():
    eq = pd.Series([1.0, 1.2, 0.9, 1.3, 1.04], index=pd.bdate_range("2024-01-01", periods=5))
    assert max_drawdown(eq) == pytest.approx(0.9 / 1.2 - 1)
```
Copy this exact style for `sortino`/`calmar` tests: construct a short hand-computable series,
assert against a manually derived expected value with `pytest.approx`. For
`test_validate_snapshot.py`, build synthetic `old`/`new` DataFrame fixtures (reuse the
`tiny_prices`-style construction from `conftest.py`) and assert `validate_snapshot` raises
`ValueError` (or returns cleanly) for each D-13 branch — one test per failure mode, matching
`tests/test_backtest.py`'s one-behavior-per-test granularity.

**Analog for `tests/test_grid.py` extension ("0 of 24" regression):**
`tests/test_grid.py` itself (lines 1-11):
```python
def test_grid_rules_share_one_window(random_prices):
    """Every rule must be measured over the same interval, so buy-and-hold is identical."""
    grid = run_ma_grid(random_prices, default_pairs())
    assert len(grid) == 24
    bh = grid["bh_total_return"].astype(float)
    assert bh.max() == pytest.approx(bh.min())
```
The new `test_default_window_zero_of_24` test should load the real committed
`data/prices.parquet` (not a synthetic fixture — this is a regression test against
`docs/PHASE0_FINDINGS.md`'s actual reported numbers) and assert
`(grid["excess_total_return"] > 0).sum() == 0` on the D-01 window, mirroring
`scripts/rerun_notebook_grid.py`'s own `beats = int((grid["excess_total_return"] > 0).sum())`
line (line 45).

**`tests/test_app_purity.py` (no analog — new static-check pattern):**
No existing test does a static import check. Sketch (no library needed — stdlib `ast` or a
simple substring scan over file text):
```python
import pathlib

FORBIDDEN = ("import requests", "import yfinance", "from jobs", "import jobs")

def test_app_has_no_network_or_job_imports():
    for path in pathlib.Path("app").rglob("*.py"):
        text = path.read_text()
        for bad in FORBIDDEN:
            assert bad not in text, f"{path} imports forbidden module via '{bad}'"
```

## Shared Patterns

### Purity boundary (core/ vs app/ vs jobs/)
**Source:** `core/data.py` module docstring (lines 1-5): *"Network calls live here and are only
used by jobs/scripts, never by the Streamlit app."*
**Apply to:** Every new file under `core/`, `app/`, `jobs/`. `core/` never imports `streamlit`;
`app/` never imports `requests`, `yfinance`, or `jobs`; only `jobs/refresh_prices.py` and
`core/data.py` touch the network.

### Pure-function, raise-ValueError error handling
**Source:** `core/backtest.py` lines 45-47, `core/data.py` lines 34-35, 56-57 — every `core/`
function that encounters invalid input raises a plain `ValueError` with a descriptive message; no
custom exception hierarchy, no try/except swallowing inside `core/`.
**Apply to:** `core/validate.py`/`validate_snapshot`, `core/signals.py::MACrossoverStrategy`,
`core/backtest.py::is_oos_summary` — never introduce a new exception type for this phase.

### `float(...)`-cast pure metric functions, NaN-guarded
**Source:** `core/metrics.py` lines 13-31 (`total_return`, `cagr`, `max_drawdown`, `sharpe`) —
one-line body, explicit `float(...)` cast, inline conditional guarding divide-by-zero with
`float("nan")`.
**Apply to:** `sortino`, `calmar`, `downside_deviation` additions to `core/metrics.py`.

### Config-not-hardcoded thresholds
**Source:** `core/config.py`'s `Settings` dataclass + CLAUDE.md's rule *"Thresholds and defaults
go in `core/config.py`, not inside functions."*
**Apply to:** D-13's tolerance values, D-01/D-12's default window/split dates, D-06's heatmap
grid ranges, D-05's picker bounds — all as `Settings` fields, never literals inside
`app/pages/*.py` or `jobs/refresh_prices.py`.

### GitHub Actions workflow skeleton
**Source:** `.github/workflows/ci.yml` (full file) — `runs-on: ubuntu-latest`,
`actions/checkout@v4`, `actions/setup-python@v5` with `python-version: "3.12"` and `cache: pip`,
`pip install -e ".[dev]"`.
**Apply to:** `.github/workflows/nightly.yml`'s setup steps (diverges only in the trigger and the
job-execution/commit steps).

### Fixture-driven, one-behavior-per-test pytest style
**Source:** `tests/conftest.py` (`tiny_prices`, `random_prices` fixtures) + `tests/test_backtest.py`
(hand-computed `pytest.approx` assertions, one test function per distinct behavior, a one-line
docstring explaining the scenario when the arithmetic isn't self-evident).
**Apply to:** All new/extended test files this phase.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `app/Home.py` | controller/router | request-response | No Streamlit code exists anywhere in the repo yet; use RESEARCH.md Pattern 1 + UI-SPEC §Streamlit-Specific Contract item 1 (`st.navigation`/`st.Page` skeleton) |
| `app/components/sidebar.py` | component | request-response | Same — first `st.sidebar` widget module; use UI-SPEC's Sidebar control labels table + RESEARCH.md's `@st.cache_data` wrapper shape |
| `app/components/charts.py` | component | transform | First Plotly figure-builder module; use RESEARCH.md Code Examples + UI-SPEC Color section (hex values, `theme="streamlit"` rule) |
| `app/pages/1_overview.py` | page | request-response | Use RESEARCH.md "Overview KPI strip pattern" (lines 604-614) + UI-SPEC §4/§5 |
| `app/pages/2_strategy_lab.py` | page | request-response | Use RESEARCH.md Patterns 2-4 + CONTEXT.md D-01 through D-12 verbatim |
| `.streamlit/config.toml` | config | — | Fully specified verbatim in UI-SPEC's `.streamlit/config.toml` block — copy directly, no derivation needed |
| `data/meta.json` schema | model (data file) | file-I/O | New schema (DATA-04); no existing JSON file in `data/` to pattern-match — fields are specified by DATA-04 plus CONTEXT.md's "Claude's Discretion" note that the schema can extend beyond the required fields |
| `tests/test_app_purity.py` | test | static check | No existing static-import-check test in the repo; sketch provided above under "Pattern Assignments" |
| `core/validate.py` (if split from `core/data.py`) | utility | batch | No validation-gate precedent in the codebase; RESEARCH.md Pattern 5 is the concrete starting sketch |

## Metadata

**Analog search scope:** `core/`, `tests/`, `scripts/`, `.github/workflows/`, `pyproject.toml` (the entire pre-Phase-1 codebase — `app/` and `jobs/` do not exist yet)
**Files scanned:** `core/data.py`, `core/config.py`, `core/backtest.py`, `core/metrics.py`, `core/grid.py`, `core/signals.py`, `core/indicators.py`, `tests/conftest.py`, `tests/test_grid.py`, `tests/test_backtest.py`, `tests/test_signals.py`, `tests/test_indicators.py`, `scripts/rerun_notebook_grid.py`, `.github/workflows/ci.yml`, `pyproject.toml`
**Pattern extraction date:** 2026-10-07
