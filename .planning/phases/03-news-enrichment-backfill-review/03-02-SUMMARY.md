---
phase: 03-news-enrichment-backfill-review
plan: 02
subsystem: data
tags: [anthropic-sdk, web-search, structured-outputs, source-cross-validation, spend-ledger]

# Dependency graph
requires:
  - phase: 03-news-enrichment-backfill-review/03-01
    provides: core/news/schema.py (Episode, Source, DroppedSource, Usage, EventExplanation, Enrichment, EnrichmentRecord, apply_status_rules, to_record, is_current_record), core/news/cost.py (price_for, cost_usd, ledger_total_usd), core/storage.py (load_events/write_events, load_spend_ledger/write_spend_ledger), jobs/enrich_events.py's PROVIDERS registry and main() skeleton
provides:
  - core/news/sources.py (parse_page_age, extract_search_results, publisher_from_url, filter_sources_in_window, sanitize_raw_response) -- pure, tested NEWS-03/NEWS-05 cross-validation
  - core/news/prompt.py (SYSTEM_PROMPT, ClaimedSource, ModelAnswer, build_user_prompt, answer_json_schema, prompt_fingerprint, PROMPT_FINGERPRINTS)
  - jobs/claude_provider.py::ClaudeSearchProvider -- the real, network-calling NewsProvider
  - jobs/enrich_events.py --provider claude: env-only key handling, model preflight, spend ledger, budget guard, --escalate-needs-review
affects: [03-03-backfill-workflow, 03-04-review-tool, 03-05-pre-backfill-spike, 03-06-full-backfill, phase-04-event-explorer]

# Tech tracking
tech-stack:
  added: []  # anthropic/pydantic/python-dateutil were already installed and pinned by 03-01
  patterns:
    - "Source cross-validation: a claimed source is kept only if its URL was actually returned by extract_search_results AND its page_age parses inside the episode's search window -- the model's own self-reported fields are never read (core/news/sources.py::filter_sources_in_window)"
    - "parse_page_age rejects any string without a 4-digit year (1900-2099) before ever calling dateutil's fuzzy parser, so relative phrases like '3 days ago' can never resolve against 'now' and be mistaken for an absolute date"
    - "publisher_from_url is a hand-rolled string-split hostname parser (no urllib) because core/ purity forbids importing urllib"
    - "tenacity Retrying(...) used as a callable (not @retry decorator) with retry_if_exception_type restricted to the three documented-retryable anthropic exception types; every other exception (including validation/auth errors) fails on the first attempt"
    - "pause_turn continuation: usage and max_uses accumulate/decrement across re-calls; the assistant's own prior content is replayed back as a message turn; stop_reasons other than end_turn/pause_turn (or pause_turn beyond the continuation cap, or 0 search budget on a needed continuation) raise ValueError naming only the episode_id"
    - "Spend ledger: one run_id-keyed entry, rewritten in place after every episode attempt (success or failure) via core/storage.write_spend_ledger, so a crash never loses accounting; the budget guard checks ledger_total_usd(prior entries) + run-so-far + a per-episode reserve against SETTINGS.news_budget_usd before every call, not just once at startup"

key-files:
  created:
    - core/news/sources.py
    - core/news/prompt.py
    - jobs/claude_provider.py
    - tests/test_news_sources.py
    - tests/test_news_prompt.py
    - tests/test_claude_provider.py
    - tests/fixtures/news/claude_response_explained.json
    - tests/fixtures/news/claude_response_pause_turn.json
  modified:
    - jobs/enrich_events.py
    - tests/test_enrich_events.py

key-decisions:
  - "jobs/enrich_events.py's make_client(api_key) -> anthropic.Anthropic requires `import anthropic` in that module too, alongside jobs/claude_provider.py -- see Deviations for why this reconciles two conflicting statements inside 03-02-PLAN.md itself"
  - "answer_json_schema() strips only the pydantic-only 'default' key recursively and sets additionalProperties:false + full required list on every object (root and nested $defs), per the plan's explicit 'title is fine, remove default' instruction"
  - "The budget guard re-checks ledger_total_usd(prior entries) + run-so-far + reserve before every episode in the loop, not just once before the run, so a multi-episode run that would cross the budget mid-run stops immediately after the last affordable episode and keeps everything already written"
  - "select_needs_review matches on (status == needs_review AND model != escalation_model), independent of prompt_version, so a needs_review record is never re-escalated twice even across a prompt-version bump"

patterns-established:
  - "FakeClient/FakeMessages/FakeResponse (recording .create(**kwargs) calls, returning objects exposing only .model_dump()) is the test double for anthropic.Anthropic throughout tests/test_claude_provider.py and tests/test_enrich_events.py -- no real SDK types needed in tests"
  - "httpx2 (not httpx) is this environment's installed httpx distribution; anthropic's retryable exception classes (RateLimitError, APIConnectionError, InternalServerError) are constructed in tests via httpx2.Request/Response, imported as `import httpx2 as httpx`"

requirements-completed: [NEWS-01, NEWS-03, NEWS-04, NEWS-05, NEWS-07, OPS-03]

# Metrics
duration: 20min
completed: 2026-10-09
---

# Phase 3 Plan 2: ClaudeSearchProvider -- Web Search + Structured Output Summary

**`--provider claude` now calls Claude with server-side web search and structured output in one request, cross-validates every cited source against the tool's own search results (never the model's claimed dates), logs verified spend to a per-run ledger with a pre-call budget guard, and is proven entirely offline against two hand-built response fixtures.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-10-09T15:08 (first RED commit)
- **Completed:** 2026-10-09T15:23 (final GREEN commit)
- **Tasks:** 3 (all `tdd="true"`, each with a `test` RED commit followed by a `feat` GREEN commit)
- **Files modified:** 10 (8 created, 2 modified) -- matches the plan's `files_modified` list exactly

## Accomplishments

- `core/news/sources.py` implements NEWS-03's cross-validation as four pure, independently tested functions: `parse_page_age` (rejects year-less/relative strings like "3 days ago" before ever reaching dateutil's fuzzy parser), `extract_search_results` (maps url -> {title, page_age} from `web_search_tool_result` blocks only, ignoring error-shaped content), `publisher_from_url` (hand-rolled hostname parsing -- no `urllib`, which core/ purity forbids), and `filter_sources_in_window` (keeps a claimed source only if its URL was actually searched and its page_age falls inside the episode's window; every drop reason -- `not_in_search_results`, `no_page_age`, `unparseable_page_age`, `outside_window` -- is recorded).
- `core/news/sources.py::sanitize_raw_response` recursively strips `encrypted_content`/`encrypted_index`/`cited_text` at any depth without mutating its input (NEWS-05, the copyright "no stored article text" rule).
- `core/news/prompt.py` defines the exact `SYSTEM_PROMPT` (instructs JSON-only output, cite-only-searched-URLs, `unexplained` on no in-window source, untrusted-web-content/prompt-injection guard per T-03-06), `ModelAnswer` (no `scheduled` field -- that's always derived from `episode.catalyst`, never the model), `build_user_prompt` (dates, direction, signed move_pct, trigger, scheduled/unscheduled releases, catalyst), a strict `answer_json_schema()` (every object gets `additionalProperties: false` and a full `required` list), and a SHA-256 `prompt_fingerprint()` hard-pinned in `PROMPT_FINGERPRINTS["v1"]` so an unversioned prompt edit fails a test.
- `jobs/claude_provider.py::ClaudeSearchProvider` is the repo's primary `import anthropic` call site: it composes the `web_search` server tool with `output_config.format` in one request, sums usage and decrements `max_uses` across up to `SETTINGS.news_max_continuations` `pause_turn` re-calls, cross-validates every claimed source via `core/news/sources.py` before building the `EventExplanation`, retries only the three documented-retryable anthropic exception types via a `tenacity.Retrying` callable, and re-raises every other failure as a `ValueError` naming only the `episode_id` and exception type (never the original message, which could embed request/key details).
- `jobs/enrich_events.py --provider claude` is fully wired: `make_client(api_key)` (module-level, monkeypatchable), an env-only `ANTHROPIC_API_KEY` check that names the repo-secret workflow, a free `client.models.retrieve(model)` preflight before any spend, a spend ledger (`data/enrichment_spend.json`-shaped, one `run_id`-keyed entry rewritten after every episode attempt) using `core/news/cost.cost_usd` against `SETTINGS`' verified prices (replacing 03-01's `cost_usd=0.0` placeholder), a pre-episode budget guard (`ledger_total_usd(prior) + run-so-far + reserve > SETTINGS.news_budget_usd` stops the run and keeps already-written records), and `--escalate-needs-review` (re-sends only `needs_review` records not already on the escalation model, via a `ClaudeSearchProvider` built with `SETTINGS.news_escalation_model`).
- Two hand-built, clearly-marked-synthetic response fixtures (`claude_response_explained.json`, `claude_response_pause_turn.json`) exercise every documented response shape (server_tool_use, web_search_tool_result with an in-window source, an outside-window source, and a text block citing a never-searched URL; a `pause_turn` continuation) with zero network calls anywhere in the test suite.

## Task Commits

Each task was committed atomically; all three are `tdd="true"`, so each has a `test` RED commit followed by a `feat` GREEN commit:

1. **Task 1: core/news/sources.py + prompt.py** -- `f9459de` (test, RED) / `1048bd7` (feat, GREEN)
2. **Task 2: ClaudeSearchProvider** -- `14a5cb7` (test, RED, includes the two fixtures) / `fe96c34` (feat, GREEN)
3. **Task 3: --provider claude wiring in jobs/enrich_events.py** -- `8f09011` (test, RED) / `da91e02` (feat, GREEN)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP are owned by the orchestrator in worktree mode)

## Files Created/Modified

- `core/news/sources.py` -- `parse_page_age`, `extract_search_results`, `publisher_from_url`, `filter_sources_in_window`, `sanitize_raw_response`
- `core/news/prompt.py` -- `SYSTEM_PROMPT`, `ClaimedSource`, `ModelAnswer`, `build_user_prompt`, `answer_json_schema`, `prompt_fingerprint`, `PROMPT_FINGERPRINTS`
- `jobs/claude_provider.py` -- `ClaudeSearchProvider` (web search + structured output, pause_turn continuation, leak-safe errors)
- `jobs/enrich_events.py` -- `make_client`, `select_needs_review`, `_write_ledger`, extended `main()` (preflight, ledger, budget guard, escalation, new `--ledger-path`/`--escalate-needs-review`/`--retry-wait-max` flags)
- `tests/test_news_sources.py` -- 20 tests: page_age parsing table, extraction, publisher parsing, window filtering (all four drop reasons + duplicate handling), sanitizer (recursion + non-mutation)
- `tests/test_news_prompt.py` -- 11 tests: system prompt content, user-prompt per-episode context (scheduled vs. surprise), schema strictness, fingerprint pin
- `tests/test_claude_provider.py` -- 12 tests: cross-validation end to end, status downgrades, pause_turn continuation + max_uses decrement, continuation/stop_reason failure paths, sentinel-key leak guard, retryable-error retry count, sanitized raw_response
- `tests/fixtures/news/claude_response_explained.json`, `tests/fixtures/news/claude_response_pause_turn.json` -- hand-built, `_comment`-marked synthetic Anthropic response bodies
- `tests/test_enrich_events.py` -- 9 new tests: missing-key, preflight failure, happy path (ledger required keys + per-episode stdout), budget guard (pre-existing-ledger block + mid-run stop), episode failure accounting, escalation selection + its `--provider null` rejection, null-provider-never-touches-ledger

## Decisions Made

- `answer_json_schema()` strips only the `"default"` key recursively (pydantic-only artifact that structured outputs rejects) and sets `additionalProperties: false` + a full `required` list on every object node (root `ModelAnswer` and the nested `ClaimedSource` under `$defs`) -- exactly the plan's "title is fine, remove default" instruction.
- The budget guard is re-evaluated **before every episode**, not once at startup, so a run that would cross the budget partway through stops immediately after the last affordable episode -- already-written records and the ledger entry for episodes completed so far are both kept untouched.
- `select_needs_review` matches purely on `(status == "needs_review" AND model != escalation_model)`, independent of `prompt_version` -- an already-escalated record is never re-sent even if the prompt version later bumps.
- `publisher_from_url` is a hand-rolled three-way string split (scheme, userinfo, port) rather than `urllib.parse`, since `urllib` is in `tests/test_app_purity.py`'s `FORBIDDEN_MODULES` set for `core/`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint] `publisher_from_url` used `startswith`/slice instead of `removeprefix`**
- **Found during:** Task 1 ruff check
- **Fix:** Replaced the conditional slice with `str.removeprefix("www.")` (ruff FURB188)
- **Files modified:** `core/news/sources.py`
- **Commit:** `1048bd7`

**2. [Rule 1 - Lint] A nested closure captured a loop variable (`tools`) for tenacity's retryer (B023)**
- **Found during:** Task 2 ruff check
- **Fix:** Passed `self.client.messages.create` and its kwargs (including `tools`) directly as `Retrying.__call__(fn, **kwargs)` arguments instead of wrapping them in a local closure, eliminating the late-binding hazard entirely (not just silencing the lint)
- **Files modified:** `jobs/claude_provider.py`
- **Commit:** `fe96c34`

**3. [Rule 1 - Lint] `SIM113` suggested `enumerate()` for the `attempted` counter**
- **Found during:** Task 3 ruff check
- **Fix:** Added a `# noqa: SIM113` with an inline reason -- `enumerate()` doesn't fit cleanly here because the budget-guard `break` must happen before the counter increments, and `attempted` is read again after the loop ends
- **Files modified:** `jobs/enrich_events.py`
- **Commit:** `da91e02`

**4. [Rule 1 - Doc accuracy] `jobs/claude_provider.py`'s docstring overclaimed "the repo's only `import anthropic`"**
- **Found during:** Task 3, once `jobs/enrich_events.py::make_client` needed `anthropic.Anthropic(...)` to construct the client
- **Issue:** The plan's Task 2 action text directed this exact docstring wording, but the plan's own Task 3 interface section separately specifies `make_client(api_key: str) -> anthropic.Anthropic` living in `jobs/enrich_events.py` -- which requires `import anthropic` there too. The plan's frontmatter `must_haves.truths` also states "the anthropic SDK is imported only in jobs/claude_provider.py," which is the stricter of the two internally-conflicting statements.
- **Resolution:** Kept `import anthropic` in both files (required for `make_client`'s type signature and constructor call) and corrected `jobs/claude_provider.py`'s docstring to say it is "the module that actually calls the Anthropic API," clarifying that `jobs/enrich_events.py`'s import is construction-only (never `messages.create`/`models.retrieve` itself). This matches the plan's own **acceptance criterion** for Task 2 (`grep -rln "import anthropic\|from anthropic" core app jobs scripts` is expected to list **both** `jobs/claude_provider.py` and `jobs/enrich_events.py`) and its Task 3 interface note, over the looser frontmatter paraphrase.
- **Files modified:** `jobs/claude_provider.py` (docstring only), `jobs/enrich_events.py`
- **Commit:** `da91e02`
- **Verified:** `grep -rlnE "^\s*(import|from) anthropic" core app` still returns nothing (the plan's actual `<verification>` gate, which only checks `core/` and `app/`, not `jobs/`).

No architectural (Rule 4) deviations. No auth gates encountered -- all tests use a `FakeClient`/`FakeClaudeClient`, never a real `anthropic.Anthropic` instance or network call.

## Issues Encountered

- This environment's installed httpx distribution is named `httpx2` (confirmed via `pip list`/`pip show httpx` returning "not found"), not the usual PyPI `httpx` package that `anthropic`'s SDK normally depends on by that name. Tests that need to construct real `anthropic.RateLimitError`/`APIConnectionError` instances (for the retry-count test) import it as `import httpx2 as httpx`. This is an environment detail, not a project dependency change -- `pyproject.toml` is untouched, and no application code imports `httpx`/`httpx2` directly (only the test file, to build fixture exceptions).

## User Setup Required

None. `ANTHROPIC_API_KEY` is still not provisioned anywhere (as 03-01 noted) -- every test in this plan uses a `FakeClient`/`FakeClaudeClient` monkeypatched in place of `jobs.enrich_events.make_client`, so no real key or network access was needed. The real key must be set (locally for a dev spike, or as a GitHub Actions secret for the recorded backfill, per D-04) before 03-05's pre-backfill spike or any real `--provider claude` run.

## Known Stubs

None. The 03-01 `cost_usd=0.0` stub is resolved for the `"claude"` path (now calls `core/news/cost.cost_usd(enrichment.usage, enrichment.model, settings)`); it remains `0.0` for the `"null"` provider, which is correct (the null provider spends nothing) and documented as intentional in 03-01's own summary.

## Threat Flags

None. Every piece of new network/auth/schema surface in this plan (the Claude API call itself, the spend ledger, the preflight model check, the budget guard) was already named and dispositioned `mitigate` in the plan's own `<threat_model>` (T-03-06 through T-03-11), and each mitigation is implemented and tested as described there -- no new, undocumented surface was introduced.

## Next Phase Readiness

- `jobs.enrich_events.main(["--provider", "claude", ...])` is ready for 03-05's small pre-backfill spike (5-10 real episodes against the real API) -- it only needs `ANTHROPIC_API_KEY` set in the environment; everything else (preflight, ledger, budget guard) is already wired and tested offline.
- `--escalate-needs-review` is ready for use once the full backfill (03-06) has produced `needs_review` records to escalate.
- `core/news/sources.py` and `core/news/prompt.py` are stable, pure contracts -- 03-03 (backfill workflow) and 03-04 (review tool) should not need to modify either file.
- No blockers.

---
*Phase: 03-news-enrichment-backfill-review*
*Completed: 2026-10-09*

## Self-Check: PASSED

All 10 created/modified files confirmed present on disk; all 6 task commit hashes
(`f9459de`, `1048bd7`, `14a5cb7`, `fe96c34`, `8f09011`, `da91e02`) confirmed present in
`git log --oneline`.
