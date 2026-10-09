"""Incremental, idempotent news enrichment job: turns pending closed episodes from
data/episodes.parquet into validated EnrichmentRecord rows in data/events.json.

Usage:
    python -m jobs.enrich_events --provider null --events-path <tmp> --dry-run
    python -m jobs.enrich_events --provider null --events-path <tmp>
    ANTHROPIC_API_KEY=... python -m jobs.enrich_events --provider claude
    ANTHROPIC_API_KEY=... python -m jobs.enrich_events --provider claude --escalate-needs-review

The real network-calling provider (jobs/claude_provider.py::ClaudeSearchProvider, D-03)
lives in jobs/, not core/news/ -- core/ stays network-free (D-02). This module is the
only other place that imports `anthropic`, and only for its Anthropic(...) client
constructor (make_client) -- it never calls the API directly itself, that is
ClaudeSearchProvider's job. There is deliberately no --api-key argument: the key is
read only from the ANTHROPIC_API_KEY environment variable / GitHub Actions secret,
never a CLI argument, never printed (D-04/OPS-03).

A failure partway through a run never loses or corrupts already-written records: each
episode's record is upserted and the whole file rewritten (single call site:
_write_events) immediately after that episode succeeds, so a later failure only stops
further progress -- it never deletes what already finished. The same holds for the
"claude" provider's spend ledger (_write_ledger): both files are rewritten after every
episode, so a crash never loses accounting (NEWS-07).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import anthropic
import pydantic

from core.config import SETTINGS
from core.news.base import NewsProvider
from core.news.cost import cost_usd, ledger_total_usd
from core.news.null import NullProvider
from core.news.schema import Episode, is_current_record, to_record
from core.storage import (
    load_episodes,
    load_events,
    load_spend_ledger,
    write_events,
    write_spend_ledger,
)
from jobs.claude_provider import ClaudeSearchProvider

EPISODE_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_(shock|gap|drawdown|rally)$")

# name -> factory(args) -> NewsProvider. "claude" is handled separately in main()
# because it needs a constructed client and a model-dependent preflight check before
# it can be built -- see _build_claude_provider.
PROVIDERS = {
    "null": lambda args: NullProvider(),
}


def make_client(api_key: str) -> anthropic.Anthropic:
    """Construct the Anthropic SDK client. Module-level and monkeypatchable so tests
    never need a real key or network access. tenacity (inside ClaudeSearchProvider)
    owns retries, so max_retries=0 here."""
    return anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=SETTINGS.news_api_timeout_s)


def select_needs_review(
    episodes: list[Episode],
    records: list[dict],
    escalation_model: str,
    episode_ids: list[str] | None,
    max_episodes: int,
) -> list[Episode]:
    """Episodes whose current record is "needs_review" and not already on the
    escalation model, optionally restricted to `episode_ids`, sorted by start_date,
    truncated to `max_episodes` (--escalate-needs-review)."""
    episodes_by_id = {ep.episode_id: ep for ep in episodes}
    wanted_ids = {
        r["episode_id"]
        for r in records
        if r.get("status") == "needs_review" and r.get("model") != escalation_model
    }
    if episode_ids is not None:
        wanted_ids &= set(episode_ids)

    pending = [episodes_by_id[eid] for eid in wanted_ids if eid in episodes_by_id]
    pending.sort(key=lambda ep: ep.start_date)
    return pending[:max_episodes]


def select_pending(
    episodes: list[Episode],
    records: list[dict],
    prompt_version: str,
    episode_ids: list[str] | None,
    force: bool,
    max_episodes: int,
) -> list[Episode]:
    """Closed episodes without a current record (NEWS-06), optionally restricted to
    `episode_ids`, sorted by start_date, truncated to `max_episodes`.

    A non-forced id with a current record stays skipped even if named in `episode_ids`
    -- `force` is required to deliberately re-enrich an already-current episode.
    """
    current_ids = {r["episode_id"] for r in records if is_current_record(r, prompt_version)}
    forced_ids = set(episode_ids) if (force and episode_ids) else set()

    pending = [
        ep
        for ep in episodes
        if ep.status == "closed" and (ep.episode_id not in current_ids or ep.episode_id in forced_ids)
    ]
    if episode_ids is not None:
        wanted = set(episode_ids)
        pending = [ep for ep in pending if ep.episode_id in wanted]

    pending.sort(key=lambda ep: ep.start_date)
    return pending[:max_episodes]


def _write_events(records_by_id: dict[str, dict], events_path: Path) -> None:
    """Single call site for the write path."""
    write_events(list(records_by_id.values()), events_path)


def _write_ledger(prior_entries: list[dict], run_entry: dict, ledger_path: Path) -> None:
    """Single call site for the spend-ledger write path (NEWS-07). Replaces the
    current run's entry (matched by run_id) among the prior entries loaded at the
    start of this run, so the ledger total always reflects every call made so far --
    even if this process crashes mid-run."""
    updated = [e for e in prior_entries if e["run_id"] != run_entry["run_id"]]
    updated.append(run_entry)
    write_spend_ledger(updated, ledger_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=sorted({*PROVIDERS, "claude"}), default="null")
    parser.add_argument("--episodes-path", default=str(SETTINGS.episodes_path))
    parser.add_argument("--events-path", default=None)
    parser.add_argument("--ledger-path", default=None)
    parser.add_argument(
        "--episode-ids", default="", help="comma-separated episode_ids; empty means all pending"
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--max-episodes", default="", help="empty means SETTINGS.news_max_episodes_per_run"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--escalate-needs-review",
        action="store_true",
        help="re-send existing needs_review records to SETTINGS.news_escalation_model "
        "instead of enriching new pending episodes; requires --provider claude",
    )
    parser.add_argument("--retry-wait-max", type=float, default=SETTINGS.fetch_wait_max_s)
    args = parser.parse_args(argv)

    settings = SETTINGS  # module-level name; tests monkeypatch this binding directly

    if args.escalate_needs_review and args.provider != "claude":
        print("--escalate-needs-review requires --provider claude", file=sys.stderr)
        return 1

    events_path = Path(args.events_path) if args.events_path else settings.events_path
    ledger_path = Path(args.ledger_path) if args.ledger_path else settings.news_spend_ledger_path

    if args.provider == "null" and events_path == settings.events_path:
        print(
            "refusing to write null-provider records to the committed events file; "
            "pass --events-path",
            file=sys.stderr,
        )
        return 1

    max_episodes = (
        settings.news_max_episodes_per_run
        if args.max_episodes == ""
        else int(args.max_episodes)
    )
    if max_episodes > settings.news_max_episodes_per_run:
        print(
            f"--max-episodes {max_episodes} exceeds SETTINGS.news_max_episodes_per_run "
            f"({settings.news_max_episodes_per_run})",
            file=sys.stderr,
        )
        return 1

    episode_ids_arg = [e for e in args.episode_ids.split(",") if e] if args.episode_ids else []
    episode_ids: list[str] | None = episode_ids_arg or None

    try:
        episodes_df = load_episodes(Path(args.episodes_path))
    except (OSError, ValueError) as exc:
        print(f"enrichment failed: {exc}", file=sys.stderr)
        return 1

    if episode_ids is not None:
        known_ids = set(episodes_df["episode_id"])
        bad = [eid for eid in episode_ids if not EPISODE_ID_RE.match(eid) or eid not in known_ids]
        if bad:
            print(f"unknown or malformed --episode-ids: {bad}", file=sys.stderr)
            return 1

    existing_records = load_events(events_path, missing_ok=True)
    episodes = [Episode.from_row(row) for _, row in episodes_df.iterrows()]

    model = settings.news_model
    client = None
    if args.provider == "claude":
        api_key = os.environ.get(settings.anthropic_api_key_env, "")
        if not api_key:
            print(
                f"{settings.anthropic_api_key_env} is not set; set it in your shell for a "
                "local spike or as the ANTHROPIC_API_KEY repo secret for the backfill "
                "workflow (never commit it)",
                file=sys.stderr,
            )
            return 1

        model = settings.news_escalation_model if args.escalate_needs_review else settings.news_model
        client = make_client(api_key)
        try:
            client.models.retrieve(model)
        except Exception as exc:  # noqa: BLE001 - never leak the underlying message
            print(f"model {model} not available: {type(exc).__name__}", file=sys.stderr)
            return 1

    if args.escalate_needs_review:
        pending = select_needs_review(
            episodes, existing_records, model, episode_ids, max_episodes,
        )
    else:
        pending = select_pending(
            episodes, existing_records, settings.news_prompt_version, episode_ids, args.force,
            max_episodes,
        )
    print(f"{len(pending)} pending")

    if args.dry_run or not pending:
        return 0

    if args.provider == "claude":
        provider: NewsProvider = ClaudeSearchProvider(
            client, model=model, settings=settings, retry_wait_max=args.retry_wait_max,
        )
    else:
        provider = PROVIDERS[args.provider](args)

    records_by_id = {r["episode_id"]: r for r in existing_records}
    failures = 0
    attempted = 0
    written = 0
    budget_stopped = False

    ledger_prior_entries: list[dict] = []
    run_id = uuid.uuid4().hex
    run_input_tokens = 0
    run_output_tokens = 0
    run_searches = 0
    run_cost = 0.0
    mode = "escalation" if args.escalate_needs_review else "backfill"
    if args.provider == "claude":
        ledger_prior_entries = load_spend_ledger(ledger_path)

    for episode in pending:
        if args.provider == "claude":
            prior_total = ledger_total_usd(ledger_prior_entries)
            if prior_total + run_cost + settings.news_episode_cost_reserve_usd > settings.news_budget_usd:
                print(
                    f"budget cap reached: ledger ${prior_total:.2f} + run ${run_cost:.2f} + "
                    f"reserve ${settings.news_episode_cost_reserve_usd:.2f} > budget "
                    f"${settings.news_budget_usd:.2f}",
                    file=sys.stderr,
                )
                budget_stopped = True
                break

        attempted += 1  # noqa: SIM113 - budget check above must run before counting an attempt
        try:
            enrichment = provider.explain(episode)
            enriched_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            episode_cost = (
                cost_usd(enrichment.usage, enrichment.model, settings)
                if args.provider == "claude"
                else 0.0
            )
            record = to_record(
                enrichment, episode, settings.news_prompt_version, enriched_at,
                cost_usd=episode_cost,
            )
        except (ValueError, pydantic.ValidationError) as exc:
            print(
                f"episode {episode.episode_id} failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            failures += 1
        except Exception as exc:  # noqa: BLE001 - never leak an unknown exception's message
            print(f"episode {episode.episode_id} failed: {type(exc).__name__}", file=sys.stderr)
            failures += 1
        else:
            records_by_id[episode.episode_id] = record.model_dump(mode="json")
            _write_events(records_by_id, events_path)
            written += 1
            if args.provider == "claude":
                run_cost += episode_cost
                run_input_tokens += enrichment.usage.input_tokens
                run_output_tokens += enrichment.usage.output_tokens
                run_searches += enrichment.usage.web_search_requests
                budget_left = (
                    settings.news_budget_usd
                    - ledger_total_usd(ledger_prior_entries)
                    - run_cost
                )
                print(
                    f"episode {episode.episode_id}: status={record.status} "
                    f"searches={enrichment.usage.web_search_requests} cost=${episode_cost:.4f} "
                    f"run_total=${run_cost:.4f} budget_left=${budget_left:.2f}"
                )

        if args.provider == "claude":
            run_entry = {
                "run_id": run_id,
                "provider": "claude",
                "model": model,
                "prompt_version": settings.news_prompt_version,
                "episodes_attempted": attempted,
                "episodes_written": written,
                "failures": failures,
                "input_tokens": run_input_tokens,
                "output_tokens": run_output_tokens,
                "web_search_requests": run_searches,
                "cost_usd": run_cost,
                "mode": mode,
            }
            _write_ledger(ledger_prior_entries, run_entry, ledger_path)

        if failures >= settings.news_max_failures_per_run:
            print(f"stopping after {failures} failures", file=sys.stderr)
            break

    return 1 if (failures or budget_stopped) else 0


if __name__ == "__main__":
    raise SystemExit(main())
