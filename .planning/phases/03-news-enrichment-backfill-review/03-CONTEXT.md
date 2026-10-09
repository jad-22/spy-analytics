# Phase 3: News Enrichment, Backfill & Review - Context

**Gathered:** 2026-10-09
**Status:** Ready for planning
**Source:** plan-phase check-in (no discuss-phase run); open questions from 03-RESEARCH.md answered by Jason

<domain>
## Phase Boundary

Every detected episode (142 in `data/episodes.parquet`) gets a sourced, pydantic-validated explanation or is
honestly marked `unexplained` / `needs_review`, within the $25 budget. Jason can accept, edit or reject records
locally. No public app pages change in this phase (Event Explorer is Phase 4).

</domain>

<decisions>
## Implementation Decisions

### Model and pricing (verified 2026-10-09 against platform.claude.com models overview + pricing pages)
- **D-01:** Default enrichment model is `claude-haiku-5-5` ($0.10 / $0.50 per MTok for prompts ≤100k tokens). Escalation model for `needs_review` re-runs is `claude-sonnet-5-5` ($2 / $10 per MTok). Web search is $10 per 1,000 searches. Model IDs and prices live in `core/config.py`. The CLAUDE.md "unverified" note about these IDs is superseded.

### Module placement
- **D-02:** Pure logic lives in `core/news/` (pydantic schema, `NewsProvider` protocol, `NullProvider`, source/window validation, status rules, override merging). No network and no `anthropic` import in `core/`.
- **D-03:** The networked `ClaudeSearchProvider` (anthropic SDK + web search) lives under `jobs/`. `core/` stays network-free apart from `core/data.py`. The app never imports `jobs/`.

### API key and where the backfill runs
- **D-04:** The recorded backfill that writes the committed `data/events.json` runs as a manual GitHub Actions `workflow_dispatch` job using the `ANTHROPIC_API_KEY` repo secret, then commits the data. Local spike and dev runs may read `ANTHROPIC_API_KEY` from the shell environment. The key is never written to the repo, `data/`, logs, or stored raw responses, and never set in Streamlit Cloud.

### Review tool
- **D-05:** The review tool is a local-only CLI (`python -m scripts.review_events`) that steps through records with accept, edit or reject actions and writes `data/event_overrides.json`. No Streamlit UI. Overrides win at read time and are never merged back into `events.json`.

### Claude's Discretion
- Exact prompt wording, the pydantic field set beyond the roadmap's list, per-run episode cap and per-request `max_uses` values (within budget), and whether Phase 2's scheduled-release and catalyst tags are passed into the prompt (research recommends yes).
- A small pre-backfill spike (5-10 episodes) to confirm that web search and structured output compose in one call is expected (research recommendation).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `docs/SPEC.md`: event explanation schema, data model, budget, honesty rules
- `docs/ROADMAP.md`: phase tasks and gates
- `.planning/REQUIREMENTS.md`: NEWS-01..08, REV-01..02, OPS-03
- `.planning/phases/03-news-enrichment-backfill-review/03-RESEARCH.md`: API mechanics, pitfalls, security
- `.planning/phases/02-event-detection-macro-calendar/02-CONTEXT.md`: episode IDs and episode data model
- `CLAUDE.md`: core/ purity, config placement, test-per-fix, Windows `.venv\python.exe`

</canonical_refs>

<deferred>
## Deferred Ideas

- Event Explorer UI that shows events is Phase 4.
- Nightly incremental enrichment wiring into the scheduled workflow, unless the planner finds it is required by a Phase 3 requirement.

</deferred>

---

*Phase: 03-news-enrichment-backfill-review*
*Context gathered: 2026-10-09 via plan-phase check-in*
