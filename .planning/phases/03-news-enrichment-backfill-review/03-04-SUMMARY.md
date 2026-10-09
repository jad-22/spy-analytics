---
phase: 03-news-enrichment-backfill-review
plan: 04
subsystem: infra
tags: [reporting, github-actions, workflow_dispatch, budget, leak-scan, ci]

# Dependency graph
requires:
  - phase: 03-news-enrichment-backfill-review
    plan: 02
    provides: core/news/cost.py (price_for, cost_usd, ledger_total_usd, estimate_backfill_usd), jobs/enrich_events.py --provider claude CLI, core/storage.py spend-ledger helpers
  - phase: 03-news-enrichment-backfill-review
    plan: 03
    provides: core/news/overrides.py (Override, apply_overrides), core/storage.py (load_event_overrides, load_effective_events)
provides:
  - "scripts/report_news_budget.py: render_budget + main writing docs/PHASE3_BUDGET.md from core/config.py's D-01 verified prices and the real 142 closed episodes"
  - "docs/PHASE3_BUDGET.md: script-generated verified pricing, per-episode estimate, worst-case-at-caps, 20% escalation scenario, actual ledger spend"
  - ".github/workflows/backfill.yml: workflow_dispatch-only paid backfill/spike/escalation job holding ANTHROPIC_API_KEY as a secret"
  - "scripts/report_phase3.py: render_enrichment_report + render_episode_table + main writing docs/PHASE3_ENRICHMENT.md (coverage, status tallies, leak scan)"
  - "tests/test_events_data.py: offline integrity checks on a committed data/events.json, skipped cleanly until it exists"
  - "CLAUDE.md/docs/SPEC.md/docs/ROADMAP.md corrected to the D-03 (jobs/claude_provider.py) and D-05 (scripts/review_events.py) paths"
affects: [03-05-pre-backfill-spike, 03-06-full-backfill, 03-07-review]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Report scripts (report_news_budget.py, report_phase3.py) are pure render_*(...) -> str functions plus a thin main(argv) -> int wrapper, matching scripts/report_phase2.py's established shape -- every number traces to core.config.SETTINGS or core.storage reads, never a literal"
    - "Leak scan over json.dumps(records/overrides/ledger) text (not just a structural field check): scans for sk-ant-, x-api-key, encrypted_content, cited_text case-insensitively plus the live ANTHROPIC_API_KEY env value if set, without ever printing that value -- used by both scripts/report_phase3.py's rendered 'PASS'/'FAIL' line and tests/test_events_data.py's committed-file scan"
    - "workflow_dispatch inputs reach the shell only via an env: mapping on the step that uses them, never interpolated into a run: script line directly -- enforced by tests/test_backfill_workflow.py's regex check that every ${{ inputs. reference sits on an env-mapping line"
    - "if: ${{ !cancelled() }} on the commit step (not the default implicit success()) so a failed enrich step still commits every already-written record and spend-ledger entry, while the job's own conclusion still reports failed"

key-files:
  created:
    - scripts/report_news_budget.py
    - scripts/report_phase3.py
    - docs/PHASE3_BUDGET.md
    - .github/workflows/backfill.yml
    - tests/test_report_phase3.py
    - tests/test_backfill_workflow.py
    - tests/test_events_data.py
  modified:
    - CLAUDE.md
    - docs/SPEC.md
    - docs/ROADMAP.md

key-decisions:
  - "render_enrichment_report filters records to is_current_record(record, settings.news_prompt_version) before computing every tally (status counts, per-model, dropped-source/stop-reason, search usage) -- a stale-prompt-version or null-provider record counts as 'missing' (needing re-enrichment) rather than polluting the current-state summary, consistent with NEWS-06's existing 'current record' definition in jobs/enrich_events.py::select_pending"
  - "The leak scan is a report-layer safety net over the *serialized* text of records/overrides/ledger (via json.dumps), not just a per-field check -- it would catch a leak even if a future field were added without updating a structural scanner, matching the plan's literal 'any input file text contains' wording"
  - "Escalation-scenario fraction (20% of episodes) is a local module constant in scripts/report_news_budget.py, not a core/config.py Settings field, since it governs only this one illustrative report line, not any runtime behaviour"
  - "docs/PHASE3_ENRICHMENT.md is not generated/committed in this plan -- main() is proven against both a hand-built fixture and the real repo's --stdout path (0 current records, exit 0), but the real report with real content is 03-06's job once the backfill has run"

patterns-established:
  - "Pattern: a workflow_dispatch job's dispatch inputs are declared under on.workflow_dispatch.inputs and consumed only inside one step's env: block; the step's run: script reads them as ordinary shell variables ($VAR) and builds an args array, never string-interpolating ${{ inputs.* }} into the script body itself"

requirements-completed: [NEWS-07, NEWS-08, OPS-03]

# Metrics
duration: 25min
completed: 2026-10-09
---

# Phase 3 Plan 4: Budget Report, Backfill Workflow, Enrichment Report & Integrity Tests Summary

**Script-generated budget and enrichment reports against D-01's verified Claude pricing, a workflow_dispatch-only GitHub Actions job that holds the Anthropic API key as a secret and commits every paid result even after a failure, and offline integrity tests ready for the real backfill's committed data.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-10-09 (first RED commit, `55f95d3`)
- **Completed:** 2026-10-09 (final GREEN commit, `b9de22b`)
- **Tasks:** 3 (Tasks 1 and 3 `tdd="true"`, each with a `test` RED commit followed by a `feat` GREEN commit; Task 2 is a single `feat` commit)
- **Files modified:** 10 (7 created, 3 modified) -- matches the plan's `files_modified` list exactly

## Accomplishments

- `scripts/report_news_budget.py::render_budget` renders `docs/PHASE3_BUDGET.md` purely from `core/config.py`'s D-01 verified model IDs/prices and the committed spend ledger: a pricing table with both model IDs' input/output prices and the web-search price, the verification date and both source URLs, the Haiku per-episode estimate (via `core/news/cost.py::estimate_backfill_usd`), a worst-case-at-hard-caps figure shown as two separate line items (search cost at the cap, reserve headroom), a 20%-escalation scenario costed on `claude-sonnet-5-5`, the budget cap, and either "No paid runs recorded yet" or a per-run ledger table with totals and remaining budget. Re-running it against the real 142 closed episodes produces a byte-identical `docs/PHASE3_BUDGET.md`.
- `CLAUDE.md`'s stale "the model IDs ... are unverified" correction note is replaced with the 2026-10-09 D-01 verification (exact prices) and a pointer at the generated budget report; `scripts.review_events` is added to the Commands block.
- `.github/workflows/backfill.yml` is `workflow_dispatch`-only (no `schedule:`), with `episode_ids`/`max_episodes`/`escalate_needs_review` inputs reaching the shell only through the "Enrich episodes" step's `env:` mapping (never interpolated into the script body), `ANTHROPIC_API_KEY` read only from `secrets.ANTHROPIC_API_KEY` in that same step, and a "Commit enrichment data" step gated on `!cancelled()` (not the default implicit `success()`) so every already-written `data/events.json` record and `data/enrichment_spend.json` ledger entry survive a failed/interrupted run, while the job's own conclusion still correctly reports `failed`.
- `scripts/report_phase3.py::render_enrichment_report` reports closed-episode coverage (missing ids listed), raw vs. override-effective status counts, reviewed/rejected counts, unresolved `needs_review` ids, records-per-model/dropped-source-reason/stop-reason tallies, total and max-per-episode web search usage, ledger spend vs. budget, and a `PASS`/`FAIL` leak scan over the serialized text of records/overrides/ledger (plus the live `ANTHROPIC_API_KEY` env value if set, never echoed). `render_episode_table` renders a one-row-per-episode spike table (status, confidence, kept-source count, dropped reasons, searches, cost, headline; "missing" for an absent id). `--stdout` against the real repo (no `events.json` yet) reports 0 current records and exits 0.
- `tests/test_events_data.py` is modelled on `tests/test_macro_calendar_data.py`'s `skipif`-until-committed pattern: validates every record through `EnrichmentRecord.model_validate`, rejects `provider == "null"`, checks `prompt_version`/`model` against the known tables, checks the search window and every source's `published` date against the matching episode, checks `scheduled == (catalyst == "scheduled")`, requires `explained` to have >= 1 source, scans the raw committed-file text for leaked patterns, and checks the spend ledger stays within budget. Collects and skips (9 tests) cleanly today, since `data/events.json` doesn't exist yet.
- `docs/SPEC.md` and `docs/ROADMAP.md` are corrected to the D-03 (`jobs/claude_provider.py`) and D-05 (`scripts/review_events.py`) paths the earlier plans actually built, with `enrichment_spend.json` added to the Data model table and Phase 3's roadmap items converted to the checkbox style used elsewhere, items 1-4 ticked.

## Task Commits

1. **Task 1 RED: budget report tests** - `55f95d3` (test)
2. **Task 1 GREEN: scripts/report_news_budget.py + docs/PHASE3_BUDGET.md + CLAUDE.md** - `df4eb26` (feat)
3. **Task 2: .github/workflows/backfill.yml + tests/test_backfill_workflow.py** - `f9180f4` (feat)
4. **Task 3 RED: enrichment report + events-data integrity tests** - `91b7626` (test)
5. **Task 3 GREEN: scripts/report_phase3.py + docs/SPEC.md + docs/ROADMAP.md** - `b9de22b` (feat)

**Plan metadata:** this SUMMARY commit (SUMMARY/STATE/ROADMAP.md under `.planning/` are owned by the orchestrator in worktree mode)

## Files Created/Modified

- `scripts/report_news_budget.py` - `render_budget`, `main`, `HEADER`
- `scripts/report_phase3.py` - `render_enrichment_report`, `render_episode_table`, `main`, `HEADER`
- `docs/PHASE3_BUDGET.md` - generated report (142 closed episodes, verified pricing, estimates)
- `.github/workflows/backfill.yml` - manual-only paid backfill/spike/escalation job
- `tests/test_report_phase3.py` - 20 tests across both report scripts
- `tests/test_backfill_workflow.py` - 8 text-level workflow-shape guards
- `tests/test_events_data.py` - 9 offline integrity tests, `skipif` until `data/events.json` exists
- `CLAUDE.md` - corrected pricing-verification note, `scripts.review_events` command added
- `docs/SPEC.md` - `core/news`/`jobs`/`scripts` file layout, Curation paragraph, Data model table
- `docs/ROADMAP.md` - Phase 3 items converted to `[x]`/`[ ]` checkboxes

## Decisions Made

- `render_enrichment_report` filters to `is_current_record(record, settings.news_prompt_version)` before every tally, so a stale-prompt-version or null-provider placeholder record is treated as "missing" (needs re-enrichment), not as current-state noise -- reusing the exact "current record" definition `jobs/enrich_events.py::select_pending` already relies on for NEWS-06.
- The leak scan operates on `json.dumps(...)` of the records/overrides/ledger structures (not a hand-enumerated field walk), so it keeps working even if a future schema field were added without a matching scanner update -- directly implementing the plan's "any input file text contains" wording at the report layer, as a second line of defense behind `core/news/sources.py::sanitize_raw_response`'s write-time stripping.
- The 20%-escalation-scenario fraction is a local constant in `scripts/report_news_budget.py`, not a `core/config.py` `Settings` field, since it affects only this one illustrative report line, not any runtime budget-guard behaviour.
- Per the plan's explicit instruction, `docs/PHASE3_ENRICHMENT.md` itself is not generated/committed in this plan -- `main()` is proven both against a hand-built fixture (writes the file) and against the real repo via `--stdout` (0 current records, exit 0); 03-06's real backfill is what gives this report real content worth committing.

## Deviations from Plan

None - plan executed exactly as written. Every acceptance criterion's grep/pytest check passed on the first implementation attempt; no auto-fixes beyond the one ruff lint fix below were needed.

### Auto-fixed Issues

**1. [Rule 1 - Lint] `render_episode_table`'s implicit string concatenation inside a list literal (ISC004)**
- **Found during:** Task 3 ruff check
- **Issue:** A two-part f-string-adjacent header line (`"| episode_id | ... |" "searches | ... |"`) inside a list literal triggered ruff's "did you forget a comma?" guard.
- **Fix:** Wrapped the two concatenated string literals in parentheses, matching ruff's suggested fix exactly (no comma was intended; it's one continued string).
- **Files modified:** `scripts/report_phase3.py`
- **Committed in:** `b9de22b` (Task 3 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 lint)
**Impact on plan:** Purely stylistic; no behavior change.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. `ANTHROPIC_API_KEY` still only needs to exist as the repo's GitHub Actions secret (or a local dev shell var for a spike) before 03-05/03-06 actually dispatch `backfill.yml` or run `--provider claude` locally; this plan adds no new setup requirement.

## Known Stubs

None. Both report scripts are fully wired against real `core.storage`/`core.config` reads with no placeholder data path; `docs/PHASE3_ENRICHMENT.md` is intentionally not generated yet (see Decisions Made), which is documented, not a stub, and is resolved by 03-06's real backfill run.

## Threat Flags

None. Every new surface this plan introduces (`backfill.yml`'s dispatch inputs and secret handling, the report scripts' leak scan, the spend-vs-budget reporting) was already named and dispositioned `mitigate` in the plan's own `<threat_model>` (T-03-16 through T-03-20), and each mitigation is implemented and tested exactly as described there (T-03-21's "who can dispatch" is explicitly `accept`d by the plan, not mitigated, and nothing in this plan changes that).

## Next Phase Readiness

- `scripts/report_news_budget.py` and `scripts/report_phase3.py` are both ready to be re-run after 03-05's pre-backfill spike and 03-06's full backfill -- neither needs any code change once real `data/events.json`/`data/enrichment_spend.json` content exists; the reports will simply have real numbers to show instead of zeros/"No paid runs recorded yet".
- `.github/workflows/backfill.yml` is ready to dispatch once `ANTHROPIC_API_KEY` is provisioned as a repo secret -- no further workflow change expected for 03-05's spike or 03-06's full run (both are just different `episode_ids`/`max_episodes` dispatch inputs).
- `tests/test_events_data.py` will start actually asserting (rather than skipping) the moment 03-06 commits a real `data/events.json`, giving that plan an immediate offline integrity check with no further test-writing needed.
- No blockers.

---
*Phase: 03-news-enrichment-backfill-review*
*Completed: 2026-10-09*

## Self-Check: PASSED

All 10 created/modified files confirmed present on disk; all 5 task commit hashes
(`55f95d3`, `df4eb26`, `f9180f4`, `91b7626`, `b9de22b`) confirmed present in
`git log --oneline --all`.
