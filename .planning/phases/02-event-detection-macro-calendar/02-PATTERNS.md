# Phase 2: Event Detection & Macro Calendar - Pattern Map

**Mapped:** 2026-10-08
**Files analyzed:** 8 (2 core modules, 1 core extension, 1 core extension, 2 jobs, 2 test files)
**Analogs found:** 8 / 8 (all role-match or better; no true "exact" analogs exist since this is greenfield detection logic, per RESEARCH.md's own "State of the Art" section)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|---------------|
| `core/events.py` (new) | service (pure detector/transform) | transform (batch, deterministic) | `core/regimes.py` | role-match (same peak/trough-scan + dataclass style; different grain) |
| `core/calendar.py` (new) | service (pure tagging logic) | transform (batch, event-driven match) | `core/validate.py` | role-match (pure gate function, raises/returns on structural checks against a calendar) |
| `core/data.py` (extended: `fetch_fred_release_dates`, `fetch_fomc_dates`) | service (network fetch) | request-response (external API/HTML) | `core/data.py::fetch_yfinance` (same file, existing function) | exact (literally the pattern to extend in-place) |
| `core/storage.py` (extended: `load_episodes`, `load_macro_calendar`) | service (pure read layer) | file-I/O | `core/storage.py::load_prices`/`load_meta` (same file) | exact |
| `jobs/detect_events.py` (new) | job (I/O orchestrator) | batch (read parquet → compute → write parquet) | `jobs/refresh_prices.py` | exact (same "job owns I/O, calls pure core, writes artifact, fail-loud" shape) |
| `jobs/build_macro_calendar.py` (new) | job (I/O orchestrator) | batch (network fetch → parse → write parquet) | `jobs/refresh_prices.py` | role-match (same job shape, but source is FRED/Fed HTTP instead of yfinance) |
| `tests/test_events.py` (new) | test | transform (hand-checkable fixtures) | `tests/test_regimes.py` | exact (same fixture style: tiny hand-checkable `pd.Series`/`pd.bdate_range`) |
| `tests/test_build_macro_calendar.py` (new) | test | request-response (mocked network) | `tests/test_refresh_prices.py` | exact (same `monkeypatch` fetch pattern, tmp_path for writes) |

## Pattern Assignments

### `core/events.py` (service, transform)

**Analog:** `core/regimes.py` (peak/trough scan style) + `core/indicators.py` (frozen dataclass + `from_label`/parsing style) + `core/signals.py` (pure-function-per-rule style)

**Module docstring/purity convention** (from `core/regimes.py` lines 1-4, and enforced by `tests/test_app_purity.py::test_core_has_no_streamlit_import`):
```python
"""Drawdown regimes and Overview KPIs. Pure; computed on whatever price basis the caller passes.

Thresholds and windows are passed in by callers from SETTINGS; no literals in function bodies.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
```
Apply the same convention to `core/events.py`: no Streamlit import, no network import, every threshold (`2.5`, `0.015`, `0.05`, `0.08`, `30`, `3`/merge window, `60`-day σ window) passed in from `core.config.SETTINGS` — never a bare literal inside a function body (RESEARCH.md's own "Known Threat Patterns" table flags this explicitly for DET-06).

**Core peak/trough-scan pattern to reuse/adapt** (`core/regimes.py` lines 41-90, `drawdown_table`):
```python
def drawdown_table(close: pd.Series, top_n: int) -> pd.DataFrame:
    drawdown = drawdown_series(close)
    episodes: list[dict] = []
    peak_price = float(close.iloc[0])
    peak_date = close.index[0]
    in_episode = False
    episode_start_idx: int | None = None

    for i, (date, price) in enumerate(close.items()):
        if price >= peak_price:
            if in_episode:
                episode_slice = drawdown.iloc[episode_start_idx : i + 1]
                episodes.append({
                    "peak": peak_date, "trough": episode_slice.idxmin(),
                    "recovery": date, "depth": float(episode_slice.min()),
                    "days_underwater": i - episode_start_idx,
                })
                in_episode = False
            peak_price, peak_date = float(price), date
        elif not in_episode:
            in_episode = True
            episode_start_idx = i - 1
    ...
```
RESEARCH.md's own Code Examples section (DET-03) explicitly notes this structural similarity and suggests factoring shared peak/trough-scan logic — but flags it `[ASSUMED]`/planner's call since `drawdown_table` wants *all* drawdowns unfiltered, while DET-03 wants only ≥5% ones as episodes. Recommend: write `core/events.py::drawdown_episodes` as its own causal single-pass scan following this same style (no look-ahead, `float()`-cast prices, dict-of-fields-per-episode-then-`pd.DataFrame`), rather than importing from `core/regimes.py` directly — keep the two call sites decoupled per RESEARCH.md's own caution, but match the *style* exactly.

**Dataclass + label-parsing pattern** (`core/indicators.py` lines 22-37, `MASpec`):
```python
@dataclass(frozen=True)
class MASpec:
    kind: Literal["sma", "ema"]
    period: int

    @property
    def label(self) -> str:
        return f"{self.kind}{self.period}"

    @classmethod
    def from_label(cls, label: str) -> MASpec:
        for kind in ("sma", "ema"):
            if label.startswith(kind) and label[len(kind):].isdigit():
                return cls(kind, int(label[len(kind):]))
        raise ValueError(f"Invalid MA label: {label!r}. Expected e.g. 'sma50' or 'ema200'.")
```
Use this exact shape for the deterministic `episode_id` construction (RESEARCH.md Pattern 2: `f"{anchor_date:%Y-%m-%d}_{trigger}"`) and for the `trigger` precedence rule (RESEARCH.md Pattern 2/Pitfall 4: `drawdown > rally > shock > gap`) — a small frozen dataclass or a pure function with an explicit, test-covered precedence tuple in `core.config.SETTINGS`, not inline literals.

**Interval-merge / clustering pattern** (RESEARCH.md Pattern 1, verified against real data — no existing codebase analog since this is genuinely new, but the shape mirrors `core/regimes.py::regime_spans`'s contiguous-run merge at lines 20-38):
```python
def regime_spans(drawdown: pd.Series, threshold: float) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    mask = drawdown <= threshold
    spans: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    start = None
    prev_date = None
    for date, flag in mask.items():
        if flag:
            if start is None:
                start = date
            prev_date = date
        elif start is not None:
            spans.append((start, prev_date))
            start = None
    if start is not None:
        spans.append((start, prev_date))
    return spans
```
This is the closest in-repo precedent for "scan a boolean/interval series and merge contiguous/near runs" — `core/events.py`'s sort-and-sweep merge (RESEARCH.md's `intervals.sort(...)` snippet) is the same family of algorithm, generalized from single-point contiguity to a `MERGE_DAYS`-tolerant interval merge. Use trading-day integer positions (`close.index.get_indexer(...)` or build a `date -> position` dict), never `pd.Timedelta`, matching `core/market_calendar.py`'s rationale for trading-day-aware distance.

**Error handling:** no try/except inside `core/events.py` — pure functions should raise naturally (e.g. `ValueError` on empty/malformed input) and let the caller (`jobs/detect_events.py`) handle it, matching `core/regimes.py`/`core/signals.py`'s convention of zero try/except blocks in pure modules.

---

### `core/calendar.py` (service, transform)

**Analog:** `core/validate.py` (pure gate function pattern)

**Module docstring + no-network convention** (`core/validate.py` lines 1-6):
```python
"""Pre-write validation gate for the nightly price refresh (DATA-03, D-13).

No Streamlit import, no network call. Every failure mode raises ValueError with a
descriptive message so jobs/refresh_prices.py can print it and exit non-zero,
leaving the last committed snapshot untouched.
"""
from __future__ import annotations

import pandas as pd

from core.config import Settings
from core.market_calendar import nyse_sessions
```
Apply the same shape to `core/calendar.py`: pure, no network, takes a `Settings`/config object rather than bare literals, imports only other pure `core/` modules (here it would import nothing from `core.data` — only `core.storage`'s loaded `macro_calendar_df` passed in as a parameter).

**Window-membership / tagging pattern to adapt** — `core/validate.py`'s gap-check (lines 41-44) is the closest existing "is X inside a computed window" pattern:
```python
missing = nyse_sessions(new.index[0], new.index[-1]).difference(new.index)
if len(missing):
    first_ten = [str(d.date()) for d in missing[:10]]
    raise ValueError(f"missing session(s): {first_ten}")
```
For `tag_episode(episode, macro_calendar_df) -> scheduled release(s) in [search_from, search_to]`, use the same "boolean mask over a DatetimeIndex, then filter" idiom:
```python
in_window = macro_calendar_df["date"].between(episode.search_from, episode.search_to)
matches = macro_calendar_df.loc[in_window]
```
**Function signature should return, not raise**, for the no-match case ("surprise" tagging is a valid, expected output per RESEARCH.md Pitfall 2 — a `None`/empty-list result, not an error).

---

### `core/data.py` (extended)

**Analog:** same file, existing `fetch_yfinance` (lines 31-46)

**Exact pattern to copy for `fetch_fred_release_dates`/`fetch_fomc_dates`:**
```python
def fetch_yfinance(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    """Daily OHLCV plus dividend/split-adjusted close from Yahoo Finance."""
    import yfinance as yf

    raw = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if raw is None or raw.empty:
        raise ValueError(f"yfinance returned no rows for {ticker}")
    ...
```
Note the **local import inside the function body** (`import yfinance as yf`), not at module top — this keeps `core/data.py` importable without the network library installed in unrelated test contexts, and lets `tests/test_app_purity.py`'s AST-based forbidden-module scan key off call sites cleanly. Follow the same local-import style for `requests` inside `fetch_fred_release_dates`/`fetch_fomc_dates`, and the same fail-loud convention (`raise ValueError(...)` on empty/unexpected response — RESEARCH.md's own skeleton in Architecture Patterns Pattern 3 already follows this: `resp.raise_for_status()` plus explicit `ValueError` on missing data, not a silent empty list).

**Purity-boundary implication:** `core.data` is already in `tests/test_app_purity.py::FORBIDDEN_MODULES` (line 15) — any new network function added here automatically inherits the existing app-forbidden guard; no test changes needed there, but `core/calendar.py` and `core/events.py` must NOT import `core.data` (only `jobs/*.py` may).

---

### `core/storage.py` (extended: `load_episodes`, `load_macro_calendar`)

**Analog:** same file, existing `load_prices`/`load_meta` (lines 19-26)

**Exact pattern to copy:**
```python
def load_prices(path: Path) -> pd.DataFrame:
    """Read the committed price snapshot. Lets FileNotFoundError propagate."""
    return read_prices(path)


def load_meta(path: Path) -> dict:
    """Read the committed refresh metadata. Lets FileNotFoundError propagate."""
    return json.loads(Path(path).read_text())
```
`load_episodes(path)`/`load_macro_calendar(path)` should follow the identical one-liner shape: thin wrapper, explicit "lets FileNotFoundError propagate" docstring contract (this is load-bearing — `app/components/store.py::require_data()` catches `FileNotFoundError` by name at the call site, so the new loaders must raise the same way, not swallow it).

---

### `jobs/detect_events.py` (job, batch)

**Analog:** `jobs/refresh_prices.py` (full file, 102 lines)

**Imports pattern** (lines 1-23):
```python
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from core.config import SETTINGS
from core.data import fetch_yfinance, write_prices
from core.storage import build_meta, load_prices, write_meta
from core.validate import drop_incomplete_session, validate_snapshot
```
For `jobs/detect_events.py`: `from core.config import SETTINGS`, `from core.storage import load_prices, write_meta` (or a new `write_episodes` in `core/data.py`/`core/storage.py`, mirroring `write_prices`), `from core.events import detect` (or similarly named top-level entry point), `from core.calendar import tag_episode`. **No network import** — this job reads `data/prices.parquet` only (RESEARCH.md Architecture Patterns explicitly: "No network call here").

**Core orchestration pattern — job owns I/O, calls pure core, writes artifact** (lines 63-97, `main`):
```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices-path", default=str(SETTINGS.prices_path))
    parser.add_argument("--meta-path", default=str(SETTINGS.meta_path))
    args = parser.parse_args(argv)
    ...
    try:
        df = fetch_with_retry(...)
    except Exception as exc:  # noqa: BLE001 - final-retry exhaustion, keep last snapshot
        print(f"price refresh failed: {exc}; keeping last snapshot", file=sys.stderr)
        return 1

    ...
    _write_snapshot(df, prices_path, Path(args.meta_path))
    print(f"wrote {len(df)} rows ... to {args.prices_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
`jobs/detect_events.py::main` should follow this exact `argparse` + "fail loud, print to stderr, return 1, never touch `data/` on failure" shape, reading `data/prices.parquet` via `core.storage.load_prices`, calling `core.events.detect(...)`/`core.calendar.tag_episode(...)`, writing `data/episodes.parquet`, and bumping `detector_version` in `meta.json` (RESEARCH.md Architecture Patterns: "writes data/episodes.parquet (+ bumps detector_version in meta.json)").

**Single-write-call-site pattern** (lines 48-60, `_write_snapshot`):
```python
def _write_snapshot(df: pd.DataFrame, prices_path: Path, meta_path: Path) -> None:
    """Single call site for the write path. Callers must validate before calling this."""
    write_prices(df, prices_path)
    write_meta(build_meta(df, ticker=SETTINGS.ticker, refreshed_at=datetime.now(UTC), ...), meta_path)
```
Mirror this for episodes: a single `_write_episodes(df, episodes_path, meta_path)` helper, validate-before-write.

---

### `jobs/build_macro_calendar.py` (job, batch)

**Analog:** `jobs/refresh_prices.py` (retry/backoff + idempotent-rebuild shape)

**Retry pattern** (lines 26-45, `fetch_with_retry`):
```python
def fetch_with_retry(
    ticker: str, start: str, attempts: int, wait_min_s: float, wait_max_s: float
) -> pd.DataFrame:
    """Fetch SPY prices, retrying transient failures with exponential backoff."""

    def _log_retry(retry_state) -> None:
        exc = retry_state.outcome.exception()
        print(f"price fetch attempt {retry_state.attempt_number} failed: {exc}", file=sys.stderr)

    retryer = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=wait_min_s, max=wait_max_s),
        reraise=True,
        before_sleep=_log_retry,
    )
    # Calls the module-level name so tests can monkeypatch jobs.refresh_prices.fetch_yfinance.
    return retryer(fetch_yfinance, ticker, start=start)
```
Reuse `tenacity` the same way for `fetch_fred_release_dates`/`fetch_fomc_dates` network calls inside `jobs/build_macro_calendar.py` — same "calls the module-level name so tests can monkeypatch" comment convention is load-bearing for testability (see `tests/test_refresh_prices.py::test_fetch_with_retry_retries_then_succeeds` which monkeypatches `refresh_prices.fetch_yfinance`, not `core.data.fetch_yfinance`, specifically because of this re-export pattern).

**Idempotent/rerunnable requirement (D-03 in CONTEXT.md):** `jobs/refresh_prices.py` itself is not idempotent in the relevant sense (it always re-fetches from `history_start`), but its **validation-before-write gate** (`core/validate.py::validate_snapshot`, called at line 87) is the right template for "re-running rebuilds or extends to the current date with stable rows" — `jobs/build_macro_calendar.py` should load any existing `data/macro_calendar.parquet` via the new `core.storage.load_macro_calendar`, fetch forward from the last committed date (or full re-fetch and dedupe by `date`+`release`), and write only if the result is a superset of existing rows — same "old vs new" comparison shape as `validate_snapshot`'s `old`/`new` parameters (lines 19-20).

**No-API-key-available fallback note:** RESEARCH.md's Environment Availability table confirms no FRED API key is present locally (`✗ (none found in local env or gh secret list)`). The job must support the ALFRED HTML-scrape fallback path (RESEARCH.md Alternatives Considered / Pitfall 3) if a key isn't supplied via env var — follow `core/data.py`'s existing "raise ValueError on empty/malformed result" convention for whichever path is used, don't silently produce an empty calendar.

---

### `tests/test_events.py` (test)

**Analog:** `tests/test_regimes.py` (full file) + `tests/conftest.py` (fixtures)

**Hand-checkable fixture pattern** (`tests/test_regimes.py` lines 15-19, plus `tests/conftest.py` lines 6-25):
```python
@pytest.fixture
def dd_prices():
    """Five days, hand-checkable: two drawdown episodes, one recovered."""
    idx = pd.bdate_range("2024-01-01", periods=5, name="date")
    return pd.Series([100.0, 120.0, 90.0, 130.0, 104.0], index=idx, name="close")
```
and the shared `random_prices` property-style fixture (`tests/conftest.py` lines 15-25) for broader statistical assertions (e.g. shock-day z-score distribution sanity checks).

**Assertion style** (`tests/test_regimes.py` lines 51-64, `test_drawdown_table_rows`):
```python
def test_drawdown_table_rows(dd_prices):
    table = drawdown_table(dd_prices, top_n=10)
    assert len(table) == 2
    row1, row2 = table.iloc[0], table.iloc[1]
    assert row1["peak"] == dd_prices.index[1]
    assert row1["trough"] == dd_prices.index[2]
    ...
```
Use this exact per-field assertion style for DET-01..07's test cases, plus:
- **DET-07 (7 known episodes, asserted by test):** needs a fixture built from (or loading a slice of) the real `data/prices.parquet` — no existing test loads the real committed parquet directly in a pure-module test; closest precedent is `tests/test_refresh_prices.py`'s `_gapless_frame()` helper which builds frames from `core.market_calendar.nyse_sessions` rather than hand lists, for date-grid correctness. Consider a `tests/test_phase0_regression.py`-style approach (not read in full here, but named exactly for "regression against real historical data" — worth the planner checking that file directly, since DET-07's 7-named-episode assertion is structurally a regression test, same genre as whatever Phase 0 regression file already does).
- **DET-05 (replay-stability):** needs a test that runs detection on `prices[:N]` then `prices[:N+k]` and asserts already-closed episodes keep identical `episode_id`/`anchor_date` — no existing analog test does exactly this; closest in *spirit* is `tests/test_refresh_prices.py::test_main_exits_1_when_fetched_history_shrinks` (lines 174-204) for the "re-run with different data, assert stability/rejection" pattern, though that test asserts rejection, not stability of unaffected rows.

---

### `tests/test_build_macro_calendar.py` (test)

**Analog:** `tests/test_refresh_prices.py` (full file, `monkeypatch`-based network mocking)

**Monkeypatch-the-fetch-function pattern** (lines 45-60, `test_fetch_with_retry_retries_then_succeeds`):
```python
def test_fetch_with_retry_retries_then_succeeds(tiny_prices, monkeypatch):
    calls = {"n": 0}

    def fake_fetch(ticker, start, end=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return tiny_prices

    monkeypatch.setattr(refresh_prices, "fetch_yfinance", fake_fetch)
    result = refresh_prices.fetch_with_retry("SPY", "1993-01-29", attempts=4, wait_min_s=0, wait_max_s=0)

    pd.testing.assert_frame_equal(result, tiny_prices)
    assert calls["n"] == 3
```
Use the identical shape for `jobs.build_macro_calendar`'s fetch functions: `monkeypatch.setattr(build_macro_calendar, "fetch_fred_release_dates", fake_fetch)`, asserting retry counts and final success/failure.

**tmp_path write-and-verify pattern** (lines 90-114, `test_main_success_writes_prices_and_meta`):
```python
def test_main_success_writes_prices_and_meta(tmp_path, monkeypatch):
    ...
    prices_path = tmp_path / "prices.parquet"
    meta_path = tmp_path / "meta.json"
    exit_code = refresh_prices.main([
        "--prices-path", str(prices_path), "--meta-path", str(meta_path), "--retry-wait-max", "0",
    ])
    assert exit_code == 0
    meta = load_meta(meta_path)
    assert meta["row_counts"] == {"prices": 7}
```
Use for `build_macro_calendar.main`: `tmp_path`-based `--calendar-path`/`--meta-path` args, assert exit code and written parquet row count/columns. For offline-parseable fixtures (per RESEARCH.md's Don't Hand-Roll: "Write the parser against multiple real fixture years, not one"), store small captured HTML/JSON fixture snippets for 1993, 1994, 2015 FOMC pages (the three years RESEARCH.md directly verified have distinguishable Meeting/Conference-Call shapes) as test fixtures, mirroring how `tests/conftest.py` centralizes shared fixtures.

## Shared Patterns

### Purity boundary (core/ vs jobs/ vs app/)
**Source:** `tests/test_app_purity.py` (lines 13-16, `FORBIDDEN_MODULES`)
**Apply to:** `core/events.py`, `core/calendar.py` (must stay import-clean of `requests`/network/Streamlit); `core/data.py` extension (network calls are the one explicitly allowed exception); `jobs/*.py` (allowed to import `core.data` and network libs)
```python
FORBIDDEN_MODULES = {
    "requests", "yfinance", "urllib", "httpx", "socket", "anthropic", "jobs", "scripts",
    "core.data",
}
```
No test changes needed for Phase 2 — `core.data` is already forbidden to `app/`; `core/events.py`/`core/calendar.py` automatically pass `test_core_has_no_streamlit_import` as long as they don't import `streamlit`. Consider adding a Phase-2-specific purity assertion that `core/events.py` and `core/calendar.py` don't import `core.data` either (not currently enforced generically, only the app-boundary is) — flag for planner.

### Config-driven thresholds, no literals
**Source:** `core/config.py` (`Settings` dataclass, lines 11-65)
**Apply to:** `core/events.py` (DET-01..07 thresholds), `core/calendar.py` (merge/window constants shared with events)
```python
@dataclass(frozen=True)
class Settings:
    ...
    detector_version: int = 0  # 0 = no event detector has run (Phase 2 bumps this)
```
Add new fields here for shock z-threshold (2.5), gap threshold (0.015), drawdown threshold (0.05), rally threshold (0.08)/window (30 days), merge window (3 trading days), FRED `release_id`s (10, 50) — following the existing inline-comment-with-rationale style already used throughout `Settings`.

### Fail-loud, never silently write bad data
**Source:** `core/data.py::fetch_yfinance` (`raise ValueError(f"yfinance returned no rows for {ticker}")`), `core/validate.py` (every check raises `ValueError` with a descriptive message)
**Apply to:** `core/data.py`'s new fetch functions, `core/calendar.py`'s date-parsing validation (RESEARCH.md Security Domain V5: "raise loudly on a malformed scrape result ... rather than silently writing a bad row")

### Job main() shape: argparse + fail-loud + never touch data/ on failure
**Source:** `jobs/refresh_prices.py::main` (lines 63-97)
**Apply to:** `jobs/detect_events.py`, `jobs/build_macro_calendar.py`
```python
try:
    df = fetch_with_retry(...)
except Exception as exc:  # noqa: BLE001
    print(f"... failed: {exc}; keeping last snapshot", file=sys.stderr)
    return 1
...
if __name__ == "__main__":
    raise SystemExit(main())
```

### Storage loader contract: let FileNotFoundError propagate
**Source:** `core/storage.py::load_prices`/`load_meta` (lines 19-26)
**Apply to:** new `load_episodes`/`load_macro_calendar` — `app/components/store.py::require_data()` (lines 53-66) already catches `FileNotFoundError` by name; any new loader used by a future app page (Phase 4) must raise the same way.

## No Analog Found

None — every file in scope has at least a role-match analog in the existing codebase (expected, since RESEARCH.md's own "State of the Art" section notes this is bespoke statistical logic with no prior in-repo version, but the surrounding conventions — pure `core/`, job I/O shape, test fixture style — are all well-established and directly reusable).

## Metadata

**Analog search scope:** `core/` (all 9 modules), `jobs/` (1 existing job), `tests/` (16 files, 4 read in full), `app/components/store.py`, `docs/SPEC.md` (data model + repo tree), `.planning/phases/02-event-detection-macro-calendar/02-{CONTEXT,RESEARCH}.md`
**Files scanned:** 13 read in full (core/regimes.py, core/data.py, core/storage.py, core/config.py, core/validate.py, core/market_calendar.py, core/signals.py, core/indicators.py, jobs/refresh_prices.py, tests/test_regimes.py, tests/conftest.py, tests/test_refresh_prices.py, tests/test_app_purity.py, app/components/store.py) plus targeted greps of docs/SPEC.md
**Pattern extraction date:** 2026-10-08
