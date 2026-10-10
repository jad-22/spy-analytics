# Handover: Phase 3 enrichment, resume at 03-05 "adjust" (2026-10-11)

This was written for a Claude Code cloud session picking up from a local session. Delete
this file and the pointer to it in CLAUDE.md once 03-05 is closed.

## Where things stand

- Phase 3 plans 03-01 to 03-04 are done and merged on `main`. The suite passes
  (391 passed, 9 skipped).
- 03-05 Task 1 is done: the `ANTHROPIC_API_KEY` repo secret is set.
- 03-05 Task 2 is done, but the spike failed. Run 38090673107 hit HTTP 400
  (`BadRequestError`) on all 5 calls it attempted. **$0 spent**, nothing committed. See
  `.planning/phases/03-news-enrichment-backfill-review/03-05-SUMMARY.md`.
- 03-05 Task 3 is decided: Jason chose **adjust** and handed over to this cloud session.
- Still to do after 03-05: 03-06 (full backfill, a checkpoint that needs Jason's go)
  and 03-07 (manual review pass). The phase gates come after those: code review,
  regression, verification and phase completion.

## The adjust steps (in order, stop and report at each gate)

1. **Ask Jason** to confirm that web search is enabled for the org (Console > Settings). This
   costs nothing and is the likeliest cause.
2. **Surface the API's own error.**
   - Location: `jobs/claude_provider.py:103` currently re-raises only `type(exc).__name__`.
   - For `anthropic.APIStatusError`, also include:
     - `exc.status_code`;
     - the error `type`, from `exc.body["error"]["type"]`;
     - its `message`, truncated to about 300 chars.
   - Never include `str(exc)`, the request, headers or the env.
   - Before printing, redact anything matching `sk-ant-`, and the live key value if one is set.
   - Add tests in `tests/test_claude_provider.py`:
     - a fake `BadRequestError` body is surfaced;
     - a body containing `sk-ant-xxx` is redacted.
   - Run `ruff check .` and `pytest -q`, then commit and push.
3. **Run a 1-episode diagnostic** (worst case about $0.05):
   `gh workflow run backfill.yml -f episode_ids=2008-10-13_drawdown -f max_episodes=1 -f escalate_needs_review=false`.
   Read only the `episode ...` / `budget` log lines. Never print the step's env section.
4. **Fix the cause.**
   - If the API rejects `output_config.format` together with the web_search tool:
     1. drop `output_config`;
     2. keep the JSON instruction in the prompt;
     3. rely on the existing `ModelAnswer.model_validate_json`.
     A prompt change means bumping `news_prompt_version` and adding a `PROMPT_FINGERPRINTS` entry.
   - Otherwise, fix what the error names.
5. **Re-run the 9-episode spike** (ids in 03-05-SUMMARY.md, about $0.14). Then:
   1. `git pull --rebase`.
   2. Run `python -m scripts.report_phase3 --stdout --episode-ids <csv>`.
   3. Run `pytest tests/test_events_data.py -q`.
   4. Run `python -m scripts.report_news_budget`, then commit `docs/PHASE3_BUDGET.md`.
   5. Append the results to 03-05-SUMMARY.md: per-episode status, confidence, sources,
      dropped reasons, searches and cost; the stop_reason tally; cost vs estimate; and
      whether the 7 DET-07 episodes were explained as expected.
6. **Stop.** Present go/abort for the full backfill (03-06) to Jason and spend nothing more
   until he answers.

## Environment notes (cloud is Linux, not the local Windows conda env)

- Setup: `pip install -e ".[dev]"`, then `python -m ruff check .` and `python -m pytest -q`.
- The GSD tooling (`/gsd-*` skills, `gsd-sdk`) is installed only on Jason's machine. Work
  from the plan files in `.planning/phases/03-news-enrichment-backfill-review/` directly.
- If `gh workflow run` isn't authorised here, ask Jason to dispatch from the Actions tab
  with the inputs above.
- The nightly job pushes data commits to `main`, so always `git pull --rebase` before pushing.

## Hard rules (from CLAUDE.md and the plans)

- The API key exists only in GitHub Actions secrets. Never put it on a command line, in a
  file, in chat, or in Streamlit Cloud.
- `git grep -n "sk-ant-"` may match only the leak-scan pattern strings.
- `core/` stays pure (no network calls, no anthropic import), and the app stays read-only.
- Every spend needs Jason's authorisation. The $25 cap is enforced by the job's ledger guard.
