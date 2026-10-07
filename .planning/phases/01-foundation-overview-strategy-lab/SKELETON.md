# Walking Skeleton — SPY Market Lens

**Phase:** 1
**Generated:** 2026-10-07

## Capability Proven End-to-End

A visitor runs `streamlit run app/Home.py` and sees the Overview page draw a SPY price line
from 1993-01-29 to the latest trading day. The chart reads the committed `data/prices.parquet`,
which `jobs/refresh_prices.py` wrote along with `data/meta.json`, through the one cached storage
module. The page makes no network calls.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Framework | Streamlit 1.65 multipage via `st.navigation` + `st.Page`, entrypoint `app/Home.py`, page scripts in `app/views/` (not `app/pages/`) | `st.navigation` is the current recommended API and gives explicit titles and URLs. Using `views/` instead of `pages/` avoids Streamlit's legacy `pages/` auto-discovery next to the entrypoint, so the two navigation models never mix. |
| Import root | `app/Home.py` prepends the repo root to `sys.path`, so every module imports as `core.*` / `app.components.*`. Tests rely on `pythonpath = ["."]` in `pyproject.toml`. | `streamlit run app/Home.py` only puts `app/` on the path. This keeps one import style for the app, tests and Streamlit Cloud, whatever the install path. |
| Data layer | Committed files in `data/`: `prices.parquet` (OHLCV + adj_close, 1993-01-29 onward) and `meta.json` (schema_version, ticker, source, last_refresh, first/last trading day, row_counts, detector_version). No database. | Streamlit Community Cloud has an ephemeral filesystem. Git is the store, and a nightly commit redeploys the app. |
| Read path | `core/storage.py` (pure, no Streamlit) wrapped by `app/components/store.py` (`@st.cache_data`, no `ttl`, keyed on the file path string). Views read data only through `app.components.store`. | DATA-05: one cached storage module. `core/` stays testable without Streamlit. A redeploy clears the cache, so a TTL adds nothing (CLAUDE.md). |
| Write path | `jobs/refresh_prices.py` (yfinance, `auto_adjust=False`, tenacity retries) → validation gate (`core/validate.py`, NYSE sessions from `core/market_calendar.py`) → `write_prices` + `write_meta`. A failure exits non-zero and leaves the old snapshot untouched. | DATA-01..04. yfinance is the only source (no Stooq, D-17). |
| Scheduling | `.github/workflows/nightly.yml`, cron `30 21 * * 1-5` + `workflow_dispatch`. It pushes with the default `GITHUB_TOKEN`, and `ci.yml` has `paths-ignore: ["data/**"]`. | D-14, D-15, OPS-05: no CI loop. |
| Auth | None. Public, read-only app with no accounts and no secrets in Streamlit Cloud. | REQUIREMENTS out of scope: user accounts. API keys (Phase 3) live only in GitHub Actions secrets. |
| Deployment target | Streamlit Community Cloud from a public GitHub repo, main file `app/Home.py`, Python 3.12. Dependencies come from `requirements.txt` (one line `.`), which installs the project from `pyproject.toml`. | OPS-01. `pyproject.toml` stays the single source of truth. Locally, run `./.venv/python.exe -m streamlit run app/Home.py`. |
| Theme | `.streamlit/config.toml` per UI-SPEC. Every chart uses `st.plotly_chart(fig, theme="streamlit")`. Semantic trace colours are in `app/components/theme.py`. | One palette source. No CSS injection. |
| Directory layout | `core/` pure analytics, `jobs/` offline writers, `app/Home.py` + `app/views/*.py` + `app/components/*.py`, `data/` committed outputs, `tests/` pytest (including Streamlit `AppTest` end-to-end tests). | Matches CLAUDE.md purity rules. `app/` never imports `jobs/`, `core.data`, `requests` or `yfinance`, and `tests/test_app_purity.py` enforces this. |
| Config | All thresholds and defaults are fields on `core.config.Settings`. | CLAUDE.md rule. |

## Stack Touched in Phase 1

- [ ] Project scaffold: `pyproject.toml` deps (streamlit, plotly, tenacity), ruff, pytest + `streamlit.testing.v1.AppTest`
- [ ] Routing: `st.navigation` with Overview (Plan 01) and Strategy Lab (Plan 04)
- [ ] Data: real read (`data/prices.parquet`, `data/meta.json` via `app/components/store.py`) and real write (`jobs/refresh_prices.py` 1993 backfill)
- [ ] UI: sidebar date range + price basis wired to the cached read and the Plotly chart
- [ ] Deployment: local `streamlit run app/Home.py` (Plan 01), then Streamlit Community Cloud (Plan 06 checkpoint)

## Out of Scope (Deferred to Later Slices)

- Event detection, macro calendar, `episodes.parquet` (Phase 2). `meta.json.detector_version` is `0` until then.
- News enrichment, `events.json`, the review tool, the Anthropic API key (Phase 3)
- Event Explorer, Event Study and Methodology pages, failure-notification issues, the 60-day keepalive (Phase 4, OPS-04)
- Heatmap click-to-select (the sidebar picker drives the selected cell). Heatmap small multiples. A rolling-start horizon picker.
- Stooq or any second price source

## Subsequent Slice Plan

- Phase 2: the detector writes `data/episodes.parquet` and `data/macro_calendar.parquet` through `core/storage.py` and bumps `meta.json.detector_version`
- Phase 3: enrichment writes `data/events.json`, and overrides are read through the same storage module
- Phase 4: Event Explorer, Event Study and Methodology views are registered in `app/Home.py`'s `st.navigation`, and `nightly.yml` gains detect and enrich steps
