---
phase: 01-foundation-overview-strategy-lab
verified: 2026-10-08T12:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Open https://spy-market-analytics.streamlit.app/ and view the Overview page default state"
    expected: "Last ~5 years shown as a line chart with SMA 50/200 overlays and -10/-20% drawdown bands; the 4-metric KPI strip is readable; the largest-drawdowns table shows 'Not recovered' for any unrecovered episode; Candlestick and Price-only switches render without errors"
    why_human: "Visual layout, readability and color rendering in a real browser cannot be confirmed by grep/pytest, even though the underlying data/props are unit- and AppTest-verified"
  - test: "Open Strategy Lab and confirm the default view"
    expected: "Page leads with '0 of 24 rules beat buy-and-hold in this window' above any chart, with the fixed anchor caption beneath it"
    why_human: "Visual ordering/emphasis on the rendered page; text presence is grep-verified but visual prominence is not"
  - test: "Inspect the short x long heatmap at defaults (EMA short 10, SMA long 200)"
    expected: "Heatmap is white at 0 with a smooth red-green diverging scale, and the selected rule's cell is visibly marked"
    why_human: "Color rendering and marker visibility are a rendering concern; zmid=0 and colorscale endpoints are unit-tested but the visual result is not"
  - test: "Toggle trading cost, trend filter and date range on Strategy Lab"
    expected: "The page recomputes and feels responsive (consistent with the measured D-09 'REACTIVE OK' decision, ~1.5s worst case)"
    why_human: "Perceived responsiveness in a live, possibly cold/sleeping Community Cloud container cannot be measured by a static check"
deferred: []
---

# Phase 1: Foundation, Overview & Strategy Lab Verification Report

**Phase Goal:** A public URL shows SPY price context and an honest MA backtest, with every page
reading only committed `data/` files and no runtime network calls.
**Verified:** 2026-10-08
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria 1-5)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Visitor sees the Overview page: price chart (line/candle), SMA/EMA overlays, shaded drawdown regimes, KPI strip (YTD return, distance from ATH, current drawdown, 20D vol), largest-drawdowns table, total-return/price-only toggle | VERIFIED | `app/views/overview.py`, `core/regimes.py`, `app/components/price_charts.py` all present; `tests/test_app_overview.py` (10 tests, all pass) exercises `test_kpi_strip_has_four_metrics`, `test_candlestick_switch`, `test_drawdown_table_rendered`, `test_all_regimes_and_mas`, `test_ma_overlay_no_warmup_gap`, `test_price_basis_toggle` — ran directly, all 10 pass |
| 2 | Visitor configures a Strategy Lab rule and sees equity curve vs B&H with trades marked, metrics table, short×long heatmap with overfitting caption, rolling-start chart, IS/OOS split, CAGR-vs-MDD scatter | VERIFIED | `app/views/strategy_lab.py`, `core/grid.py` (`heatmap_grid`, `rolling_start_strategy`, `is_oos_split`), `app/components/lab_charts.py` (`heatmap_figure`, `scatter_figure`, `rolling_figure`) all present; `tests/test_app_strategy_lab.py` (13 tests, all pass) directly verifies heatmap contract (zmid=0, colorscale endpoints, "Selected rule" trace), 25-point scatter, rolling figure, split-date change, equity+metrics render |
| 3 | Strategy Lab default view states "0 of 24 rules beat buy-and-hold" matching Phase 0 findings | VERIFIED | `grep -c "rules beat buy-and-hold in this window" app/views/strategy_lab.py` == 1; `tests/test_phase0_regression.py` (7 tests, all pass) asserts `count_beating(grid) == 0` on 6 parametrised real-snapshot windows plus exact totals `total_return≈2.150`, `bh_total_return≈3.152` against `docs/PHASE0_FINDINGS.md`; `test_default_headline` AppTest confirms the live-rendered string |
| 4 | Nightly GitHub Actions job refreshes `data/prices.parquet`/`meta.json` (validated, retries, no silent gap/shrink), commits without triggering CI loop, every page reads through one cached module with zero network calls | VERIFIED | `core/validate.py::validate_snapshot` enforces row-count/last-date/OHLC-rewrite/adj_close-factor/missing-session checks (volume explicitly exempted per documented D-13 decision, commit `99b5953`, test `test_volume_revision_passes`); `.github/workflows/nightly.yml` scheduled `30 21 * * 1-5` + `workflow_dispatch`, default `GITHUB_TOKEN` only; `.github/workflows/ci.yml` has `paths-ignore: ["data/**"]`. Live proof: `gh run list --workflow nightly.yml` shows run `37763263924` concluded `success`, committed `f56c43a` "data: nightly price refresh"; `gh run list --workflow ci.yml` (20 most recent headSha values) contains **zero** entries matching `f56c43a` — confirmed directly against GitHub, not just SUMMARY claims. `tests/test_app_purity.py` (ast-based) + a live run confirm zero `requests/yfinance/urllib/httpx/socket/anthropic/jobs/core.data` imports in `app/` |
| 5 | New strategy rule types plug in through a `Strategy` interface without changing the Strategy Lab page | VERIFIED | `core/signals.py` has `@runtime_checkable class Strategy(Protocol)`; `grep -c "ma_crossover(\|trend_filter(\|combine_all(\|MASpec("  app/views/strategy_lab.py` returns 0 (confirmed directly) — the page only calls `strategy.name/.label/.target()`; `tests/test_signals.py::test_custom_strategy_plugs_in` exercises a test-local `AlwaysLong` class through `evaluate_strategy`/`run_strategy_grid` with no page changes needed |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `core/storage.py` | Pure read/write (load_prices, load_meta, price_basis, build_meta, write_meta) | VERIFIED | Exists, no streamlit import (`grep -rl streamlit core/` empty) |
| `app/components/store.py` | The one cached storage module, no ttl | VERIFIED | Present; `require_data()`/`render_freshness()` used by both views |
| `app/Home.py` | st.navigation entrypoint | VERIFIED | Registers `views/overview.py` and `views/strategy_lab.py` |
| `app/views/overview.py` | Full Overview page | VERIFIED | All OVER-01..06 controls present and AppTest-passing |
| `app/views/strategy_lab.py` | Full Strategy Lab page | VERIFIED | All LAB-01..10 sections present and AppTest-passing |
| `jobs/refresh_prices.py` | Retrying refresh with D-13 gate wired before write | VERIFIED | `validate_snapshot(` precedes `_write_snapshot(df` in source; exit-1-on-failure behavior proven on live GitHub run |
| `core/validate.py` | D-13 gate, 5 ValueError branches | VERIFIED | Read directly; volume exempted per documented decision, OHLC/adj_close/gap checks intact |
| `core/market_calendar.py` | NYSE session calendar | VERIFIED | `nyse_sessions`/`nyse_holidays` present, tested against real 33-year snapshot |
| `.github/workflows/nightly.yml` | Scheduled + dispatchable refresh/commit | VERIFIED | Read directly; matches D-14/D-15/D-16 exactly |
| `.github/workflows/ci.yml` | `paths-ignore: data/**` loop guard | VERIFIED | Read directly |
| `core/regimes.py` | drawdown_series, regime_spans, drawdown_table, overview_kpis | VERIFIED | Present, no streamlit import, 13+ unit tests pass |
| `core/signals.py` | Strategy Protocol + MACrossoverStrategy | VERIFIED | `class Strategy(Protocol)` + `@runtime_checkable` present |
| `core/grid.py` | run_strategy_grid, heatmap_grid, rolling_start_strategy, is_oos_split, count_beating | VERIFIED | All functions present and exercised by tests |
| `scripts/profile_lab_grid.py` | D-09 timing measurement | VERIFIED | Present; last recorded run: 1.498s worst-case sum vs. 2.0s threshold ("REACTIVE OK") |
| `data/prices.parquet` + `data/meta.json` | Committed 1993+ snapshot | VERIFIED | 8,480 rows, 1993-01-29 to 2026-10-07 (current as of the latest successful nightly run) |
| `README.md` | Live URL, run instructions, no Stooq | VERIFIED | Contains `spy-market-analytics.streamlit.app`; `grep -ci stooq README.md` == 0 |
| `docs/ROADMAP.md` | Phase 1 reflected as done | VERIFIED | Phase 1 row "Done", open questions resolved |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `app/views/overview.py` | `app/components/store.py` | `require_data`/`get_prices` | WIRED | Confirmed by purity test + direct read |
| `app/views/strategy_lab.py` | `app/components/lab_compute.py` | `headline_grid`/`heatmap_for`/`rolling_for`/`is_oos_for` | WIRED | All cached wrapper functions present and called |
| `app/components/lab_compute.py` | `core/grid.py` | `run_strategy_grid`/`heatmap_grid`/`rolling_start_strategy`/`is_oos_split` | WIRED | Confirmed by direct read |
| `jobs/refresh_prices.py` | `core/validate.py` | `validate_snapshot` before `_write_snapshot` | WIRED | Confirmed by direct read + live GitHub run behavior (rejected run made no write; fixed run committed) |
| `.github/workflows/nightly.yml` | `jobs/refresh_prices.py` | `python -m jobs.refresh_prices` | WIRED | Confirmed live: run `37763263924` executed it and committed `f56c43a` |
| Streamlit Community Cloud | `app/Home.py` on `main` | Deploy config | WIRED | `curl` to the live URL returns HTTP 303 (documented Community Cloud wake-redirect, not an error) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite green | `./.venv/python.exe -m pytest -q` | 124 passed | PASS |
| Lint clean | `./.venv/python.exe -m ruff check .` | All checks passed | PASS |
| App purity (no network/job imports) | ast-based scan of `app/**/*.py` | 0 matches | PASS |
| `core/` has no Streamlit import | `grep -rl streamlit core/` | empty | PASS |
| LAB-10 page purity | `grep -c "ma_crossover(\|trend_filter(\|combine_all(\|MASpec(" app/views/strategy_lab.py` | 0 | PASS |
| Live URL reachable | `curl -s -o /dev/null -w "%{http_code}" https://spy-market-analytics.streamlit.app/` | 303 (documented wake redirect) | PASS |
| Nightly workflow succeeds live | `gh run list --workflow nightly.yml` | latest run `37763263924` = success, committed `f56c43a` | PASS |
| CI not triggered by data commit | `gh run list --workflow ci.yml` (20 runs) headSha scan for `f56c43a` | 0 matches | PASS |
| `rolling_start_strategy` on real committed snapshot + live settings | direct Python invocation (`horizon_years=SETTINGS.rolling_horizon_years`) | 28 rows returned, no crash | PASS (confirms CR-01 from code review is not reachable today) |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention is used in this repository. None found via `find scripts -path '*/tests/probe-*.sh'`. Step 7c: SKIPPED (no probe scripts exist; this project uses pytest/AppTest and live `gh run`/`curl` checks instead).

### Requirements Coverage

All 23 Phase 1 requirement IDs declared across the six plans' frontmatter (`DATA-01..05`,
`OVER-01..06`, `LAB-01..10`, `OPS-01`, `OPS-05`) are accounted for, with no gaps and no
orphans against `.planning/REQUIREMENTS.md`'s traceability table (all marked "Complete").

| Requirement | Source Plan | Status | Evidence |
|---|---|---|---|
| DATA-01 | 01-01 | SATISFIED | `data/meta.json` first_trading_day "1993-01-29"; `SETTINGS.history_start` |
| DATA-02 | 01-01 | SATISFIED | `auto_adjust=False` pinned (`grep -c` ==1 in plan acceptance); retry via tenacity |
| DATA-03 | 01-02 | SATISFIED | `core/validate.py::validate_snapshot`, proven live on GitHub (rejected then accepted runs) |
| DATA-04 | 01-01 | SATISFIED | `data/meta.json` has all required keys (verified by direct read) |
| DATA-05 | 01-01 | SATISFIED | ast purity test + runtime socket-patch test, both passing |
| OVER-01..06 | 01-01, 01-03 | SATISFIED | All controls present, AppTest-passing (10/10) |
| LAB-01..04, 09, 10 | 01-04 | SATISFIED | AppTest-passing (regression + lab tests), LAB-10 purity grep confirmed |
| LAB-05..08 | 01-05 | SATISFIED | Heatmap/scatter/rolling/IS-OOS all present and tested |
| OPS-01 | 01-06 | SATISFIED | Public repo + live Streamlit Cloud URL confirmed reachable |
| OPS-05 | 01-02, 01-06 | SATISFIED | Live-proven: nightly data commit `f56c43a` triggered zero `ci.yml` runs |

No orphaned requirements found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `core/grid.py` | 195-209 | `rolling_start_strategy` silently returns an empty frame (no `ValueError`) when no start date fits the horizon, unlike every sibling grid function | INFO (not BLOCKER) | Documented in `01-REVIEW.md` as CR-01. Reproduced directly during this verification: **not reachable** with the live committed snapshot and `SETTINGS.rolling_horizon_years=5` (confirmed: 28 rows returned without error). A genuine latent bug, but it does not currently break any success criterion. Recommend a follow-up fix before `rolling_horizon_years` is ever raised or a shorter data history is used. |
| `core/data.py` / `core/validate.py` | n/a | WR-02: NaN in `adj_close`/`high`/`low`/`volume` not validated, could silently corrupt total-return basis on a future bad data day | INFO | Not currently observed in the committed snapshot; no TBD/FIXME/XXX markers found in phase-modified files |
| `jobs/refresh_prices.py` | 70-71 | WR-03: `--retry-wait-max` CLI flag can produce a longer wait than requested for `0 < value < fetch_wait_min_s` | INFO | Low impact; nightly workflow never passes this flag |

No `TBD`, `FIXME`, or `XXX` debt markers found in any phase-modified file (checked via grep across the files listed in `01-REVIEW.md`'s `files_reviewed_list`).

### Human Verification Required

The following items were deferred to end-of-phase per the `<human-check>` blocks in
`01-03-PLAN.md`, `01-05-PLAN.md` and `01-06-PLAN.md` (Task 3). The user has already confirmed
the live app renders in general (per the orchestrator's established facts), but the specific
visual/perceptual checks below were not individually confirmed in any SUMMARY and cannot be
verified by static analysis:

#### 1. Overview default view

**Test:** Open the live URL's Overview page with no sidebar changes.
**Expected:** Last ~5 years shown as a line chart with SMA 50/200 overlays and −10/−20% drawdown
bands; the 4-metric KPI strip is readable; the drawdown table shows "Not recovered" for any
unrecovered episode; Candlestick and Price-only switches work without visual glitches.
**Why human:** Color/layout rendering in a real browser; data correctness is already unit- and
AppTest-verified.

#### 2. Strategy Lab headline prominence

**Test:** Open Strategy Lab with no sidebar changes.
**Expected:** "0 of 24 rules beat buy-and-hold in this window" appears above any chart, with the
fixed anchor caption beneath it.
**Why human:** Text presence and line ordering is grep/AppTest-verified; visual prominence on
the rendered page is not.

#### 3. Heatmap visual contract

**Test:** Inspect the short × long heatmap at defaults (EMA short 10 × SMA long 200).
**Expected:** White at 0, smooth red–green diverging scale, selected cell visibly marked.
**Why human:** `zmid=0` and colorscale endpoints are unit-tested, but the rendered visual result
in a browser is not.

#### 4. Interactive responsiveness

**Test:** Change trading cost, the trend filter, and the date range on Strategy Lab.
**Expected:** The page recomputes and feels responsive, consistent with the measured D-09
decision (~1.5s worst-case cold recompute, well under the 2.0s threshold).
**Why human:** Perceived responsiveness on a live (possibly cold-starting) Community Cloud
container cannot be measured by a static check.

### Gaps Summary

No blocking gaps were found. All 5 ROADMAP success criteria are verified against the actual
codebase (not just SUMMARY claims), with direct evidence: 124/124 tests passing, ruff clean,
live `gh run` queries confirming a successful nightly run and commit (`f56c43a`) with zero
triggered `ci.yml` runs, a reachable live URL, and direct greps confirming the Strategy
interface purity (LAB-10) and zero network imports in `app/` (DATA-05).

One pre-existing, non-blocking code-review finding (CR-01 in `core/grid.py`'s
`rolling_start_strategy`) was independently reproduced during this verification and confirmed
**not reachable** under the current committed snapshot and settings — it is a real latent bug
worth fixing but does not fail any Phase 1 success criterion today.

The only reason this report is not `status: passed` is the set of genuinely visual/perceptual
checks (color rendering, layout readability, interactive feel) that were deferred to
end-of-phase human verification per the plan's own `human_verify_mode = end-of-phase` design
and have not been individually confirmed in any SUMMARY, even though the user has already
confirmed the app generally renders and works.

---

*Verified: 2026-10-08*
*Verifier: Claude (gsd-verifier)*
