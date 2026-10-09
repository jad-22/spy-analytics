---
phase: 03-news-enrichment-backfill-review
plan: 01
subsystem: data
tags: [pydantic, news-enrichment, llm-schema, protocol-interface, atomic-json-writes]

# Dependency graph
requires:
  - phase: 02-event-detection-macro-calendar
    provides: data/episodes.parquet (142 closed episodes with scheduled_releases/unscheduled_releases/catalyst tags)
provides:
  - core/news/ pure package (schema, NewsProvider Protocol, NullProvider, cost math)
  - jobs/enrich_events.py incremental enrichment job (NullProvider wired, PROVIDERS registry open for "claude")
  - core/storage.py JSON helpers (write_json_atomic, load_events, write_events, load_spend_ledger, write_spend_ledger)
  - core/config.py News enrichment Settings block (model IDs, verified prices, budget, hard caps)
affects: [03-02-claude-search-provider, 03-03-backfill-workflow, 03-04-review-tool, phase-04-event-explorer]

# Tech tracking
tech-stack:
  added: ["anthropic>=1.12,<2", "pydantic>=2.9,<3", "python-dateutil>=2.9"]
  patterns:
    - "pydantic model_validator(mode=\"after\") recomputes a code-enforced status, never trusting the caller's claimed value (apply_status_rules)"
    - "NewsProvider as a @runtime_checkable Protocol with one explain() method, matching core/signals.py::Strategy's existing convention"
    - "atomic JSON writes (tmp sibling + os.replace) generalized from core/storage.py's parquet pattern to write_json_atomic"
    - "job main() upserts into a dict-by-id and calls the single _write_events call site after every episode, so a mid-run failure never loses finished work"

key-files:
  created:
    - core/news/__init__.py
    - core/news/schema.py
    - core/news/base.py
    - core/news/null.py
    - core/news/cost.py
    - jobs/enrich_events.py
    - tests/test_enrich_events.py
    - tests/test_news_schema.py
    - tests/test_news_cost.py
  modified:
    - pyproject.toml
    - core/config.py
    - core/storage.py
    - tests/test_app_purity.py

key-decisions:
  - "apply_status_rules checks zero-sources before the reviewed override, so a human review can never mark an episode explained without a cited source"
  - "EnrichmentRecord.cost_usd is hardcoded to 0.0 in jobs/enrich_events.py for the null provider; 03-02's real provider must call core/news/cost.cost_usd(usage, model, SETTINGS) instead of a literal"
  - "select_pending requires --force AND the id to be in --episode-ids before re-enriching an already-current record -- force alone does nothing"

patterns-established:
  - "Pattern: EnrichmentRecord nested-model round-trip via model_dump(mode=\"json\") -> model_validate, used both for the storage write path and the idempotency test"
  - "Pattern: core/news/*.py module docstrings state what they must NOT import (no network, no anthropic SDK, no jobs/scripts), enforced by tests/test_app_purity.py's AST guard"

requirements-completed: [NEWS-01, NEWS-02, NEWS-04, NEWS-05, NEWS-06, NEWS-07]

# Metrics
duration: 15min
completed: 2026-10-09
---

# Phase 3 Plan 1: Offline NullProvider Enrichment Slice Summary

**Incremental, idempotent `jobs/enrich_events.py` turns closed episodes into pydantic-validated `data/events.json` records via a deterministic `NullProvider`, with code-enforced status rules and verified Haiku/Sonnet 5.5 pricing centralized in `core/config.py`.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-10-09T14:44:24+01:00
- **Completed:** 2026-10-09T14:59:32+01:00
- **Tasks:** 3
- **Files modified:** 13 (9 created, 4 modified)

## Accomplishments

- `jobs/enrich_events.py` reads `data/episodes.parquet`, filters to pending closed episodes (NEWS-06: incremental, idempotent, null-provider records never count as current), and writes schema-validated `EnrichmentRecord` rows to `data/events.json` with an atomic write after every episode.
- `core/news/schema.py` implements the full NEWS-02/04/05 pydantic contract (`Episode`, `Source`, `DroppedSource`, `Usage`, `EventExplanation`, `Enrichment`, `EnrichmentRecord`) with `apply_status_rules` as a single, monotonic, code-enforced status function that a human `reviewed=True` can override only when at least one source exists.
- `core/news/base.py`'s `NewsProvider` Protocol and `core/news/null.py`'s deterministic `NullProvider` let the whole offline slice run and test with zero network calls; `jobs/enrich_events.py`'s `PROVIDERS` registry is ready for 03-02 to add `"claude"`.
- `core/config.py` centralizes every NEWS-07 threshold (verified `claude-haiku-5-5`/`claude-sonnet-5-5` model IDs and prices per D-01, `$25` budget, per-run/per-request hard caps) -- confirmed by grep that no model ID string exists anywhere in `core/news/` or `jobs/enrich_events.py`.
- `core/news/cost.py` provides the verified cost math (`price_for`, `cost_usd`, `ledger_total_usd`, `estimate_backfill_usd`) that 03-02's real provider will call per episode instead of the current `cost_usd=0.0` placeholder.
- `--dry-run` against the real committed `data/episodes.parquet` reports `142 pending`, confirming NEWS-08's full backfill scope is ready to enrich.

## Task Commits

Each task was committed atomically (Tasks 2 and 3 are `tdd="true"`, so each has a `test` RED commit followed by a `feat` GREEN commit):

1. **Task 1: Write the failing end-to-end job test** - `1a0739f` (test) -- RED for `jobs.enrich_events`
2. **Task 2: Thinnest slice (config, schema, Protocol, NullProvider, storage, job)** - `53bef7d` (feat) -- GREEN, makes Task 1's test pass
3. **Task 3 RED: cost/status-rule/purity tests** - `c2e730c` (test) -- RED for `core.news.cost`
4. **Task 3 GREEN: implement core/news/cost.py** - `f509022` (feat)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP are owned by the orchestrator in worktree mode)

## Files Created/Modified

- `pyproject.toml` - adds `anthropic`, `pydantic`, `python-dateutil` to `[project].dependencies`
- `core/config.py` - News enrichment (NEWS-01..08, REV-01..02, OPS-03) Settings block: verified model IDs/prices, paths, budget, hard caps, prompt version, web search tool type
- `core/news/__init__.py` - package docstring (D-02 purity statement)
- `core/news/schema.py` - `Episode`, `Source`, `DroppedSource`, `Usage`, `EventExplanation`, `Enrichment`, `EnrichmentRecord`, `apply_status_rules`, `to_record`, `is_current_record`
- `core/news/base.py` - `NewsProvider` `@runtime_checkable` Protocol
- `core/news/null.py` - deterministic `NullProvider`
- `core/news/cost.py` - `price_for`, `cost_usd`, `ledger_total_usd`, `estimate_backfill_usd`
- `core/storage.py` - `write_json_atomic`, `load_events`, `write_events`, `load_spend_ledger`, `write_spend_ledger`
- `jobs/enrich_events.py` - `select_pending`, `_write_events`, `main`, `PROVIDERS` registry
- `tests/test_enrich_events.py` - 7 end-to-end tests (happy path, open-episode skip, idempotent re-run, null-not-current, committed-path refusal, id/cap filters, dry-run)
- `tests/test_news_schema.py` - 9-case `apply_status_rules` table, URL scheme validation, `EnrichmentRecord` JSON round-trip, `is_current_record` cases
- `tests/test_news_cost.py` - verified pricing, cost math, ledger total, backfill estimate
- `tests/test_app_purity.py` - adds `test_core_news_has_no_network_or_sdk_imports` (D-02 AST guard)

## Decisions Made

- `apply_status_rules`' check order places "zero sources -> unexplained" before the "reviewed -> unchanged" override, so a human can never mark an episode "explained" without at least one cited source (matches the plan's must-have truth and the nine-case parametrized test, including the explicit `("explained", 0, 0.9, reviewed=True) -> "unexplained"` case).
- `jobs/enrich_events.py` passes `cost_usd=0.0` into `to_record(...)` for every record today, since `NullProvider` never spends anything; this is a deliberate placeholder documented as a Known Stub below, not an oversight -- 03-02's real provider is expected to call `core/news/cost.cost_usd(enrichment.usage, enrichment.model, SETTINGS)` instead.
- `select_pending`'s `force` flag only re-enriches an episode if it is *also* named in `--episode-ids` -- `--force` alone is a no-op, matching the plan's "unless force and id in episode_ids" wording and keeping accidental re-spend impossible.

## Deviations from Plan

None - plan executed exactly as written. Two minor ruff-driven import-order fixes were applied to test files during Task 2/3 verification (not a deviation from the plan's intent, just `ruff --fix` on `I001`), and one `PIE810` lint fix (merged two `str.startswith()` calls into one `startswith((...))` call in `core/news/schema.py::Source._validate_scheme`) -- both are mechanical lint cleanups with no behavior change, folded into the task commits that introduced the lines.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. `ANTHROPIC_API_KEY` is referenced only as a config field name (`SETTINGS.anthropic_api_key_env`) for 03-02 to read later; nothing in this plan calls the Anthropic API.

## Known Stubs

- **`jobs/enrich_events.py` `cost_usd=0.0`** (line inside `main()`'s per-episode loop): every `EnrichmentRecord` written by this plan has `cost_usd: 0.0`, correct for the `NullProvider` (which spends nothing) but a placeholder for the real provider. Resolved by 03-02, which must pass `cost_usd(enrichment.usage, enrichment.model, SETTINGS)` (already implemented in `core/news/cost.py`) instead of the literal `0.0`.
- **`core/news/null.py`'s `raw_response=None`**: intentional, not a gap -- the null provider makes no API call, so there is no raw response to store. Real providers (03-02) must populate this per NEWS-05.

## Next Phase Readiness

- The `NewsProvider` Protocol, `EnrichmentRecord` schema, `core/storage.py` JSON helpers, and `jobs/enrich_events.py`'s `PROVIDERS` registry are all stable contracts; 03-02 only needs to add a `ClaudeSearchProvider` implementing `explain(episode) -> Enrichment` and register it as `PROVIDERS["claude"]` -- no change to `jobs/enrich_events.py`'s control flow should be required.
- `core/news/cost.py` is ready for 03-02 to wire real per-episode spend tracking and for a future `scripts/report_phase2.py`-style cost report.
- `data/episodes.parquet`'s real 142 episodes are confirmed reachable (`142 pending` via `--dry-run`), so NEWS-08's full-history backfill scope is unblocked once 03-02's real provider lands.
- No blockers.

---
*Phase: 03-news-enrichment-backfill-review*
*Completed: 2026-10-09*

## Self-Check: PASSED

All 10 created files confirmed present on disk; all 4 task commit hashes
(`1a0739f`, `53bef7d`, `c2e730c`, `f509022`) confirmed present in `git log --oneline --all`.
