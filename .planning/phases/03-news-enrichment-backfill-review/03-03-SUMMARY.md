---
phase: 03-news-enrichment-backfill-review
plan: 03
subsystem: data
tags: [pydantic, news-enrichment, review-cli, read-time-merge, atomic-json-writes]

# Dependency graph
requires:
  - phase: 03-news-enrichment-backfill-review
    plan: 01
    provides: core/news/schema.py EventExplanation/apply_status_rules, core/storage.py JSON helpers (write_json_atomic, load_events, write_events)
provides:
  - "core/news/overrides.py: Override pydantic model, EDITABLE_FIELDS, apply_override, apply_overrides, upsert_override (pure, read-time merge)"
  - "core/storage.py: load_event_overrides, write_event_overrides, load_effective_events"
  - "scripts/review_events.py: local-only accept/edit/reject/skip/quit review CLI"
affects: [phase-04-event-explorer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Override re-validates its candidate fields through EventExplanation.model_validate so apply_status_rules decides the effective status -- a human accept/edit can never produce 'explained' without a cited source"
    - "apply_override/apply_overrides deep-copy before mutating, so the read-time merge is provably pure (tested via before/after deep-equality)"
    - "CLI prompt loop reads via input_fn() with no prompt argument (prompt text printed separately via print()), so a real input and a scripted iterator().__next__ are interchangeable"
    - "EOF from input_fn (StopIteration/EOFError) raises a local _Quit exception caught at the per-record loop boundary, so a session can always be ended cleanly with exit code 0"

key-files:
  created:
    - core/news/overrides.py
    - scripts/review_events.py
    - tests/test_overrides.py
    - tests/test_review_events.py
  modified:
    - core/storage.py

key-decisions:
  - "apply_override builds its candidate from only the EventExplanation-field subset of the record, re-validates through EventExplanation.model_validate, then merges the validated fields back into a deep copy of the full record -- so provenance fields (provider, model, usage, raw_response, etc.) are never touched by an override, only the explanation fields are"
  - "Override.fields is restricted to EDITABLE_FIELDS at the pydantic-model level (not just by apply_override), and is forced empty for accept/reject actions -- invalid keys or values fail fast as a ValidationError, either at Override construction (bad keys) or at apply_override's re-validation (bad Literal values, e.g. category='bogus')"
  - "scripts/review_events.py takes --events-path/--overrides-path/--episodes-path all defaulting to SETTINGS paths, joins episodes.parquet by episode_id purely for display (window/direction/move_pct/catalyst) -- no Episode pydantic model round-trip needed since the CLI only reads, never validates, episode rows"
  - "MAX_FIELD_ATTEMPTS = 3 is a module constant in scripts/review_events.py (a UI retry limit on malformed terminal input), deliberately kept out of core/config.py since it is not an analysis threshold"

patterns-established:
  - "Pattern: a human-review override model re-validates through the same schema class that produced the record, so code-enforced invariants (NEWS-03/04's 'explained requires a source') apply uniformly to automated and human-edited paths"
  - "Pattern: CLI main(argv, input_fn=input) -> int with scripted input_fn=iter(answers).__next__ in tests, matching the project's existing main(argv) -> int / tmp_path convention from jobs/refresh_prices.py and jobs/enrich_events.py"

requirements-completed: [REV-01, REV-02]

# Metrics
duration: 13min
completed: 2026-10-09
---

# Phase 3 Plan 3: Local Review CLI and Read-Time Override Merge Summary

**A local `python -m scripts.review_events` CLI lets Jason accept, edit or reject any enrichment record; every decision writes to `data/event_overrides.json` only, and `core.storage.load_effective_events` merges overrides over `events.json` at read time without ever rewriting the committed file.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-10-09T15:07:54+01:00
- **Completed:** 2026-10-09T15:16:55+01:00
- **Tasks:** 2
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments

- `core/news/overrides.py`'s `Override` pydantic model restricts manual edits to `EDITABLE_FIELDS` (`headline`, `summary`, `category`, `region`, `drivers`, `status`) and forces `fields` empty for `accept`/`reject`, so a malformed or out-of-scope override fails fast as a `ValidationError`.
- `apply_override`/`apply_overrides` are pure (tested via before/after deep-equality): they re-validate the candidate explanation fields through `EventExplanation.model_validate`, so `apply_status_rules` -- not the human -- has the final say on status; a `needs_review` record with zero sources can never become `explained` even via `accept`.
- `core/storage.py` gains `load_event_overrides`, `write_event_overrides` and `load_effective_events`, completing REV-02's read-time merge contract: a missing overrides file leaves events unchanged, and the merge never touches `events.json` on disk.
- `scripts/review_events.py` is a local-only, no-network CLI (`python -m scripts.review_events`) that steps through the effective queue (default: `needs_review`), displays each record (episode window/direction/move_pct/catalyst joined from `episodes.parquet`, status, confidence, headline, summary, category/region/drivers, kept sources, dropped-source count), and supports accept/edit/reject/skip/quit with an immediate write after every decision.
- Edit prompts each `EDITABLE_FIELDS` entry, re-prompting up to `MAX_FIELD_ATTEMPTS = 3` on an invalid Literal value (category/region/status) before leaving the field unchanged, and parses `drivers` as a comma-separated list.
- `--status`, `--episode-id` and `--include-reviewed` let Jason reach any record, including ones that already have an override.

## Task Commits

Each task was committed atomically (both `tdd="true"`, each with a `test` RED commit followed by a `feat` GREEN commit):

1. **Task 1 RED: Override model and read-time merge tests** - `e82a178` (test)
2. **Task 1 GREEN: core/news/overrides.py + core/storage.py readers** - `4237dca` (feat)
3. **Task 2 RED: review_events.py CLI tests** - `ac86e3e` (test)
4. **Task 2 GREEN: scripts/review_events.py** - `3eeccdd` (feat)

**Plan metadata:** commit pending (this SUMMARY is owned by the orchestrator in worktree mode)

## Files Created/Modified

- `core/news/overrides.py` - `EDITABLE_FIELDS`, `Override`, `apply_override`, `apply_overrides`, `upsert_override`
- `core/storage.py` - adds `load_event_overrides`, `write_event_overrides`, `load_effective_events`
- `scripts/review_events.py` - `main(argv, input_fn=input) -> int`, accept/edit/reject/skip/quit loop, `MAX_FIELD_ATTEMPTS`, `PROMPT`
- `tests/test_overrides.py` - 20 tests: Override validation, accept/edit/reject behavior, purity, upsert, storage readers
- `tests/test_review_events.py` - 15 tests: default queue, edit overlay + invalid-literal retry, reject, skip, quit, EOF, filters, drivers parsing, display fields, no forbidden imports, `--help` exit 0

## Decisions Made

- `apply_override` scopes its re-validation to the `EventExplanation`-field subset of the record (not the full `EnrichmentRecord`), then merges the validated result back into a full deep copy -- provenance fields (`provider`, `model`, `usage`, `cost_usd`, `raw_response`, etc.) are never touched by a human override.
- `Override.fields` validity (allowed keys, action-appropriate emptiness) is checked at the pydantic-model level; `Override.fields` *value* validity (Literal values like `category`) is deferred to `apply_override`'s re-validation through `EventExplanation`, since that is the single source of truth for valid field values (no duplicate Literal lists).
- `scripts/review_events.py` reads episode display context (window, direction, move_pct, catalyst) directly from `episodes.parquet` rows via a dict lookup, not through the `Episode` pydantic model, since the CLI never writes or validates episode data -- only displays it.
- The CLI's `_read(prompt, input_fn)` helper prints the prompt itself and calls `input_fn()` with no arguments, so `input` (default) and `iter(answers).__next__` (tests) are interchangeable without special-casing.

## Deviations from Plan

None - plan executed exactly as written. Both tasks' RED tests failed for the expected reason (missing module) and GREEN implementations made them pass on the first attempt; no auto-fixes were needed.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. The review tool is local-only and never reads `ANTHROPIC_API_KEY` or makes a network call.

## Known Stubs

None. This plan's artifacts (override model, storage readers, review CLI) are fully wired end to end and testable offline; no placeholder data flows to any UI (there is no UI in this phase).

## Next Phase Readiness

- `core.storage.load_effective_events` is the stable read API Phase 4's Event Explorer should call to get the override-merged view of `data/events.json` -- it never needs to read `event_overrides.json` directly.
- `scripts/review_events.py` works today against the `NullProvider`-enriched records from 03-01 (or whatever `03-02`'s real backfill eventually writes); no change to this plan's code is expected once the real Claude provider lands, since the review tool only depends on the `EnrichmentRecord`/`EventExplanation` schema and `core.storage`'s JSON helpers.
- No blockers.

---
*Phase: 03-news-enrichment-backfill-review*
*Completed: 2026-10-09*
