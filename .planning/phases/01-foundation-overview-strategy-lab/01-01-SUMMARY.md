---
phase: 01-foundation-overview-strategy-lab
plan: 01
subsystem: data/ui
tags: [streamlit, plotly, tenacity, yfinance, parquet, app-test]

# Dependency graph
requires: []
provides:
  - "core/storage.py: pure read/write contract (load_prices, load_meta, price_basis, build_meta, write_meta)"
  - "app/components/store.py: the one cached storage module (DATA-05), no ttl"
  - "app/components/sidebar.py: price_basis_input, date_range_input"
  - "app/components/theme.py: semantic Plotly trace colours"
  - "app/Home.py + app/views/overview.py: st.navigation entrypoint and Overview skeleton"
  - "jobs/refresh_prices.py: retrying nightly price refresh, _write_snapshot() single call site"
  - "data/prices.parquet + data/meta.json: 1993-01-29+ committed snapshot"
affects: [01-02, 01-03, 01-04, 01-05, 01-06]

# Tech tracking
tech-stack:
  added: [streamlit>=1.65, plotly>=7.1, tenacity>=9.2, "yfinance>=1.7 (floor raised)"]
  patterns:
    - "core/ stays pure (no Streamlit); app/ reads data only through app/components/store.py"
    - "Settings dataclass in core/config.py holds every Phase 1 threshold/default"
    - "st.cache_data with no ttl on primitive-keyed private readers, public wrappers read module-level SETTINGS at call time so tests can monkeypatch it"
    - "jobs/refresh_prices.py: fetch -> _write_snapshot() single call site (Plan 02 inserts the D-13 validation gate there)"

key-files:
  created:
    - core/storage.py
    - app/Home.py
    - app/components/store.py
    - app/components/sidebar.py
    - app/components/theme.py
    - app/views/overview.py
    - jobs/refresh_prices.py
    - .streamlit/config.toml
    - tests/test_storage.py
    - tests/test_app_purity.py
    - tests/test_app_overview.py
    - tests/test_refresh_prices.py
    - data/meta.json
  modified:
    - core/config.py
    - core/data.py
    - pyproject.toml
    - requirements.txt
    - scripts/rerun_notebook_grid.py
    - data/prices.parquet

key-decisions:
  - "st.Page path resolution used the literal string 'views/overview.py' relative to app/Home.py, exactly as planned — no deviation needed"
  - "jobs/refresh_prices.py uses tenacity.Retrying(...)(fetch_yfinance, ticker, start=start) (callable-Retrying pattern) with a before_sleep logger, rather than the @retry decorator, so tests can monkeypatch the module-level fetch_yfinance name"

requirements-completed: [DATA-01, DATA-02, DATA-04, DATA-05, OVER-01, OVER-06]

# Metrics
duration: 14min
completed: 2026-10-08
---

# Phase 1 Plan 01: Walking Skeleton Summary

**End-to-end Streamlit skeleton (st.navigation entrypoint, cached core.storage read layer, retrying yfinance refresh job) backfilled to the real 1993-01-29 SPY snapshot — 8,480 rows, zero network calls at render time.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-10-08T00:34:29+01:00
- **Completed:** 2026-10-08T00:47:33+01:00
- **Tasks:** 4
- **Files modified:** 22 (13 created, 9 modified)

## Accomplishments

- A visitor running `./.venv/python.exe -m streamlit run app/Home.py` sees the Overview
  page draw a SPY close-price line from the committed 1993-01-29+ snapshot, with a
  working price-basis toggle and date-range sidebar control.
- `core/storage.py` (no Streamlit import) and `app/components/store.py` (the one
  `@st.cache_data` module, no `ttl`, per CLAUDE.md) together form the DATA-05 read path,
  enforced at runtime by `tests/test_app_overview.py::test_overview_makes_no_network_calls`
  and statically by `tests/test_app_purity.py`'s `ast`-based import/call guard.
- `jobs/refresh_prices.py` backfilled the real 1993-01-29 → 2026-10-07 snapshot (8,480
  rows) via live yfinance, with `tenacity`-based retry/backoff and a verified non-zero
  exit (leaving the prior snapshot untouched) on final failure.
- The Stooq fallback is fully removed from `core/data.py` (D-17) — `fetch_stooq`,
  `load_prices`, and the now-unused `requests`/`io` imports are gone.
- `data/meta.json` now exists with all DATA-04 fields (`schema_version`, `ticker`,
  `source`, `last_refresh`, `first_trading_day`, `last_trading_day`, `row_counts`,
  `detector_version`).
- Full suite: 31 tests pass (`pytest -q`); `ruff check .` is clean; a local
  `streamlit run app/Home.py --server.headless true` smoke-started, served HTTP 200,
  and was stopped cleanly.

## Task Commits

Each task was committed atomically:

1. **Task 1: Failing end-to-end tests for the skeleton** - `af05839` (test)
2. **Task 2: Core read layer — deps, Settings defaults, core/storage.py** - `25b7ea6` (feat)
3. **Task 3: App scaffold — cached store, sidebar, theme, entrypoint, Overview chart** - `66cab42` (feat)
4. **Task 4: Write slice — refresh job, Stooq removal, 1993 backfill** - `4562eb2` (feat, code) + `1cea2e5` (data)

_RED confirmed after Task 1 (ModuleNotFoundError on `core.storage`, before `core/storage.py`
existed). GREEN reached incrementally: `tests/test_storage.py` after Task 2;
`tests/test_app_purity.py` after Task 3; the three data-dependent `tests/test_app_overview.py`
tests after Task 4 wrote `data/meta.json` — matching the plan's own file-ownership split
(`data/meta.json` belongs to Task 4, not Task 3)._

## Files Created/Modified

- `core/storage.py` - pure read/write contract: `load_prices`, `load_meta`, `price_basis`, `build_meta`, `write_meta`, `BASES`
- `core/config.py` - every Phase 1 threshold/default added to `Settings` (history start, meta path, retry params, validation tolerances, Overview/Lab defaults, heatmap ranges)
- `core/data.py` - removed `fetch_stooq`/`load_prices`/`requests`/`io`; docstring updated for yfinance-only + last-good-snapshot behavior
- `app/Home.py` - `st.navigation` + `st.Page("views/overview.py", ...)` entrypoint
- `app/components/store.py` - the one cached storage module; `require_data()` empty state + `st.stop()`; `render_freshness()`
- `app/components/sidebar.py` - `price_basis_input`, `date_range_input` (bounded, falls back to defaults on partial selection)
- `app/components/theme.py` - semantic Plotly trace colours from UI-SPEC
- `app/views/overview.py` - price line chart skeleton, reads only through `app.components.store`
- `.streamlit/config.toml` - UI-SPEC theme tokens verbatim
- `jobs/refresh_prices.py` - `fetch_with_retry` (tenacity), `main()` (argparse, non-zero exit on failure, `_write_snapshot()` single call site), `if __name__ == "__main__": raise SystemExit(main())`
- `scripts/rerun_notebook_grid.py` - switched to `fetch_yfinance` (the removed `load_prices` fallback chain is gone)
- `pyproject.toml` / `requirements.txt` - streamlit/plotly/tenacity deps, raised yfinance floor, `packages.find` includes `jobs*`, requirements.txt is a single `.` line, `[tool.ruff.lint.per-file-ignores]` for `app/Home.py`'s capitalised module name
- `tests/test_storage.py`, `tests/test_app_purity.py`, `tests/test_app_overview.py`, `tests/test_refresh_prices.py` - new test suites (31 tests total across the full repo)
- `data/prices.parquet`, `data/meta.json` - real 1993-01-29 → 2026-10-07 backfill (8,480 rows)

## Decisions Made

- Used `tenacity.Retrying(...)` as a callable (`retryer(fetch_yfinance, ticker, start=start)`)
  with a `before_sleep` logger, instead of the `@retry` decorator, specifically so
  `fetch_with_retry` calls the bare module-level name `fetch_yfinance` — letting
  `tests/test_refresh_prices.py` monkeypatch `jobs.refresh_prices.fetch_yfinance` without
  needing `importlib.reload`.
- `app/components/store.py` functions read `SETTINGS` as a bare module-global at call time
  (not bound as a default argument), per the plan's own note — this is what lets
  `test_empty_state_when_data_missing` monkeypatch `store.SETTINGS` and have `require_data()`
  immediately observe the new paths.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `AppTest.from_file` resolves relative paths against the caller file's directory, not cwd**
- **Found during:** Task 3 (first GREEN attempt for `tests/test_app_overview.py`)
- **Issue:** The plan's literal example `AppTest.from_file("app/views/overview.py", ...)`
  raised `FileNotFoundError` because Streamlit 1.65's `AppTest.from_file` resolves relative
  paths against the directory of the file that calls it (`tests/`), not the pytest cwd —
  so it looked for `tests/app/views/overview.py`.
- **Fix:** Added `ROOT = Path(__file__).resolve().parents[1]` and built absolute
  `OVERVIEW_PATH`/`HOME_PATH` constants from it; every `AppTest.from_file(...)` call in the
  file now uses one of those.
- **Files modified:** `tests/test_app_overview.py`
- **Verification:** `pytest tests/test_app_overview.py -q`
- **Committed in:** `66cab42` (part of Task 3 commit)

**2. [Rule 1 - Bug] Blanket `socket.socket.connect` patch broke Windows' asyncio self-pipe**
- **Found during:** Task 4 (full-suite run after the real backfill)
- **Issue:** `test_overview_makes_no_network_calls` patched `socket.socket.connect`
  unconditionally. On Windows, `asyncio.new_event_loop()` (which `AppTest.run()` creates
  fresh every call) builds its self-pipe via a loopback `socket.socketpair()` fallback that
  internally calls `socket.connect()` to `127.0.0.1` — so the test failed on its own test
  infrastructure, not on anything the Overview page did.
- **Fix:** Scoped the guard to non-loopback hosts only (`127.0.0.1`, `::1`, `localhost` pass
  through to the original `connect`/`create_connection`; anything else still raises). A real
  external call (e.g. to Yahoo Finance) still fails the test.
- **Files modified:** `tests/test_app_overview.py`
- **Verification:** `pytest tests/test_app_overview.py::test_overview_makes_no_network_calls -q`
- **Committed in:** `4562eb2` (part of Task 4 commit)

**3. [Rule 1 - Bug] `FURB162`/`RUF100`/`N999` ruff findings on new files**
- **Found during:** Task 3 ruff pass
- **Issue:** `datetime.fromisoformat(s.replace("Z", "+00:00"))` was unnecessary (Python
  3.12's `fromisoformat` parses a trailing `Z` natively); `app/Home.py`'s `# noqa: E402`
  was unused (E402 isn't in this project's enabled rule set); `app/Home.py`'s capitalised
  module name tripped `N999`.
- **Fix:** Simplified the `fromisoformat` call in `app/components/store.py`; removed the
  stray `noqa`; added a `[tool.ruff.lint.per-file-ignores]` entry for `app/Home.py`'s `N999`
  (the capitalisation is Streamlit's own entrypoint convention, not a mistake).
- **Files modified:** `app/components/store.py`, `app/Home.py`, `pyproject.toml`
- **Verification:** `ruff check .`
- **Committed in:** `66cab42` (part of Task 3 commit)

---

**Total deviations:** 4 auto-fixed (all Rule 1 — bugs in tests/lint config, not in the
planned architecture).
**Impact on plan:** None of these changed the planned contracts, file list, or
architecture — all were test-infrastructure or lint-config corrections needed to make the
plan's own acceptance criteria actually pass on this Windows environment.

## Issues Encountered

None beyond the deviations above. The live yfinance backfill succeeded on the first
attempt (no retries needed) and required no fallback.

## User Setup Required

None - no external service configuration required. (The nightly GitHub Actions workflow,
GITHUB_TOKEN push config, and `ci.yml` `paths-ignore` from D-14/D-15 are out of scope for
this plan — they belong to a later plan in this phase per SKELETON.md's "Stack Touched in
Phase 1" checklist.)

## Next Phase Readiness

- `core/storage.py`, `app/components/store.py`, `app/components/sidebar.py`,
  `app/components/theme.py` and the `jobs/refresh_prices.py` `_write_snapshot()` call site
  are all in place for Plan 02 (Overview depth: KPI strip, MA overlays, drawdown regimes,
  largest-drawdowns table) and the later Strategy Lab plans to build on directly.
- `data/prices.parquet` + `data/meta.json` now reflect the full 1993+ history, so Plan 02's
  KPI/MA/drawdown work and the Strategy Lab's 1993→latest robustness views have real data
  to render against immediately.
- No blockers. The D-13 validation gate, `.github/workflows/nightly.yml`, and `ci.yml`'s
  `paths-ignore` are still open for whichever later plan in this phase owns OPS-05 per the
  roadmap.

---
*Phase: 01-foundation-overview-strategy-lab*
*Completed: 2026-10-08*

## Self-Check: PASSED

All 13 claimed files found on disk; all 6 claimed commit hashes found in git log.
