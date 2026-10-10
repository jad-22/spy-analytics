---
phase: 03-news-enrichment-backfill-review
plan: 05
subsystem: infra
tags: [spike, paid-run, github-actions, decision-checkpoint]
requires:
  - phase: 03-news-enrichment-backfill-review
    plan: 04
    provides: .github/workflows/backfill.yml, scripts/report_phase3.py, scripts/report_news_budget.py
provides:
  - "ANTHROPIC_API_KEY repo secret provisioned (Task 1, Jason, 2026-10-10)"
  - "Spike run 38090673107: all attempted calls rejected with HTTP 400 -- no records, $0 spend"
affects: [03-06-full-backfill]
key-files:
  created: []
  modified: []
status: decision-pending
---

# 03-05 Summary: pre-backfill spike

## Task 1: key provisioning (human-action) -- done

Jason set the `ANTHROPIC_API_KEY` repository secret ("key added, approved", 2026-10-10).
`gh secret list` shows it once. `git grep -n "sk-ant-"` matches only the leak-scan pattern
strings in plans, `scripts/report_phase3.py` and `tests/test_events_data.py`. It finds no key.

## Task 2: push + paid spike

- `main` was rebased onto the nightly price-refresh commit (b9c4b02), then pushed
  (b9c4b02..5805089). The full suite passed after the rebase: 391 passed, 9 skipped.
- Spike episode ids (7 KNOWN_EPISODES probes, plus 1993-05-19_shock and the episode containing 1997-10-27):
  `2000-04-14_drawdown,2008-10-13_drawdown,2015-08-24_drawdown,2018-02-05_drawdown,2018-12-26_drawdown,2020-03-16_drawdown,2022-11-10_drawdown,1993-05-19_shock,1997-10-27_drawdown`
- Run: https://github.com/jad-22/spy-analytics/actions/runs/38090673107. The conclusion was `failure`.
  - "Enrich episodes" failed.
  - "Commit enrichment data" ran and had nothing to commit.

Log lines (the env section is excluded):

```
episode 1993-05-19_shock failed: ValueError: Claude request failed for episode_id=1993-05-19_shock: BadRequestError
episode 1997-10-27_drawdown failed: ValueError: Claude request failed for episode_id=1997-10-27_drawdown: BadRequestError
episode 2000-04-14_drawdown failed: ValueError: Claude request failed for episode_id=2000-04-14_drawdown: BadRequestError
episode 2008-10-13_drawdown failed: ValueError: Claude request failed for episode_id=2008-10-13_drawdown: BadRequestError
episode 2015-08-24_drawdown failed: ValueError: Claude request failed for episode_id=2015-08-24_drawdown: BadRequestError
stopping after 5 failures
9 pending
```

### Findings

| Item | Result |
|---|---|
| Model preflight | Passed. The job reached the per-episode loop. |
| Episodes enriched | 0 of 9. 5 were attempted and all got HTTP 400. 4 were never attempted because the 5-failure cap stopped the run. |
| stop_reason tally | None. No call returned a message. |
| output_config + web_search composed? | **Not confirmed.** Every request got a 400 before any response came back. |
| Spend | $0.00. 400 responses are not billed. No `data/enrichment_spend.json` was written. |
| Cost per episode vs estimate | Not measurable. The estimate is unchanged at $2.24 for 142 episodes (docs/PHASE3_BUDGET.md, regenerated with no diff). |
| DET-07 explanations | Not produced. |

`report_phase3 --stdout`, `tests/test_events_data.py` and the budget-doc commit were not run.
There was no `data/events.json`, and the budget doc did not change, so there was nothing to commit.

### Diagnosis

The provider re-raises every SDK error as just its class name, so the API's
error message is invisible. `answer_json_schema()` follows every structured-outputs restriction
in the current docs:
- no numeric or length constraints;
- `additionalProperties: false` on every object;
- a local `$ref` only.

That makes the schema an unlikely cause. The candidates are:
1. web search is not enabled for the organisation (Console > Settings);
2. the API rejects `output_config.format` combined with the `web_search_20250305` tool;
3. a request-shape problem in the call.

Per the plan, the run was not retried blind.

## Decision (Task 3)

_Pending: awaiting Jason's go / adjust / abort._
