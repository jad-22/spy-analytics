"""Incremental, idempotent news enrichment job: turns pending closed episodes from
data/episodes.parquet into validated EnrichmentRecord rows in data/events.json.

Usage:
    python -m jobs.enrich_events --provider null --events-path <tmp> --dry-run
    python -m jobs.enrich_events --provider null --events-path <tmp>

The real network-calling provider (D-03, added in plan 03-02) lives in jobs/, not
core/news/ -- core/ stays network-free (D-02), so this job only ever depends on a
NewsProvider, never `anthropic` directly. Its API key, when added, is read only from the
ANTHROPIC_API_KEY environment variable / GitHub Actions secret, never a CLI argument
(D-04/OPS-03).

A failure partway through a run never loses or corrupts already-written records: each
episode's record is upserted and the whole file rewritten (single call site:
_write_events) immediately after that episode succeeds, so a later failure only stops
further progress -- it never deletes what already finished.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pydantic

from core.config import SETTINGS
from core.news.base import NewsProvider
from core.news.null import NullProvider
from core.news.schema import Episode, is_current_record, to_record
from core.storage import load_episodes, load_events, write_events

EPISODE_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_(shock|gap|drawdown|rally)$")

# name -> factory(args) -> NewsProvider. 03-02 adds "claude" here.
PROVIDERS = {
    "null": lambda args: NullProvider(),
}


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="null")
    parser.add_argument("--episodes-path", default=str(SETTINGS.episodes_path))
    parser.add_argument("--events-path", default=None)
    parser.add_argument(
        "--episode-ids", default="", help="comma-separated episode_ids; empty means all pending"
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--max-episodes", default="", help="empty means SETTINGS.news_max_episodes_per_run"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    events_path = Path(args.events_path) if args.events_path else SETTINGS.events_path

    if args.provider == "null" and events_path == SETTINGS.events_path:
        print(
            "refusing to write null-provider records to the committed events file; "
            "pass --events-path",
            file=sys.stderr,
        )
        return 1

    max_episodes = (
        SETTINGS.news_max_episodes_per_run
        if args.max_episodes == ""
        else int(args.max_episodes)
    )
    if max_episodes > SETTINGS.news_max_episodes_per_run:
        print(
            f"--max-episodes {max_episodes} exceeds SETTINGS.news_max_episodes_per_run "
            f"({SETTINGS.news_max_episodes_per_run})",
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

    pending = select_pending(
        episodes, existing_records, SETTINGS.news_prompt_version, episode_ids, args.force,
        max_episodes,
    )
    print(f"{len(pending)} pending")

    if args.dry_run or not pending:
        return 0

    provider: NewsProvider = PROVIDERS[args.provider](args)
    records_by_id = {r["episode_id"]: r for r in existing_records}
    failures = 0

    for episode in pending:
        try:
            enrichment = provider.explain(episode)
            enriched_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            record = to_record(
                enrichment, episode, SETTINGS.news_prompt_version, enriched_at, cost_usd=0.0,
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

        if failures >= SETTINGS.news_max_failures_per_run:
            print(f"stopping after {failures} failures", file=sys.stderr)
            break

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
