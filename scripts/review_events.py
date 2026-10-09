"""Local-only review tool (REV-01, D-05). No network, no API key, never deployed.
Writes only data/event_overrides.json; data/events.json is read-only here (REV-02).

Usage (from the repo root, no network):
    python -m scripts.review_events [--status needs_review|explained|unexplained|all]
                                     [--episode-id ID] [--include-reviewed]

Steps through the effective queue (events.json merged with event_overrides.json at
read time, core.storage.load_effective_events) with accept, edit, reject, skip or quit.
Each decision is written immediately to data/event_overrides.json -- events.json is
never touched.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

from core.config import SETTINGS
from core.news.overrides import EDITABLE_FIELDS, Override, upsert_override
from core.news.schema import Category, Region, Status
from core.storage import (
    load_effective_events,
    load_episodes,
    load_event_overrides,
    write_event_overrides,
)

PROMPT = "[a]ccept [e]dit [r]eject [s]kip [q]uit > "
# A UI retry limit on malformed terminal input, not an analysis threshold -- stays out
# of core/config.py.
MAX_FIELD_ATTEMPTS = 3

LITERAL_FIELDS: dict[str, Any] = {"category": Category, "region": Region, "status": Status}


class _Quit(Exception):
    """Raised when input_fn runs out of scripted input (EOF) mid-session."""


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read(prompt: str, input_fn) -> str:
    print(prompt, end="", flush=True)
    try:
        return input_fn()
    except (EOFError, StopIteration):
        raise _Quit from None


def _display_record(record: dict, episode_row: dict | None) -> None:
    print(f"\n{record['episode_id']}")
    if episode_row is not None:
        window = f"{episode_row['start_date']} to {episode_row['end_date']}"
        print(
            f"  window: {window}  direction: {episode_row['direction']}  "
            f"move_pct: {episode_row['move_pct']:.4f}  catalyst: {episode_row['catalyst']}"
        )
    print(f"  status: {record['status']}  confidence: {record['confidence']}")
    print(f"  headline: {record['headline']}")
    print(f"  summary: {record['summary']}")
    print(
        f"  category: {record['category']}  region: {record['region']}  "
        f"drivers: {record['drivers']}"
    )
    for source in record.get("sources", []):
        print(f"  source: {source['published']}  {source['publisher']}  {source['url']}")
    print(f"  dropped_sources: {len(record.get('dropped_sources', []))}")


def _prompt_field(field: str, current: Any, input_fn) -> Any | None:
    """Prompt for one editable field. Returns the new value, or None to keep `current`
    (empty input, or MAX_FIELD_ATTEMPTS invalid attempts on a Literal field)."""
    allowed = get_args(LITERAL_FIELDS[field]) if field in LITERAL_FIELDS else None
    attempts = 0
    while True:
        raw = _read(f"{field} [{current}]: ", input_fn)
        if raw == "":
            return None
        if field == "drivers":
            return [d.strip() for d in raw.split(",") if d.strip()]
        if allowed is not None and raw not in allowed:
            attempts += 1
            print(f"invalid {field}: must be one of {allowed}")
            if attempts >= MAX_FIELD_ATTEMPTS:
                return None
            continue
        return raw


def _process_record(record: dict, input_fn) -> tuple[Override | None, str]:
    """Read one decision for `record`. Returns (override_or_None, outcome), outcome in
    {"accepted", "edited", "rejected", "skipped", "quit"}."""
    action = _read(PROMPT, input_fn).strip().lower()
    if action == "q":
        return None, "quit"
    if action == "s":
        return None, "skipped"
    if action == "a":
        override = Override(
            episode_id=record["episode_id"], action="accept", reviewed_at=_now(), note=""
        )
        return override, "accepted"
    if action == "e":
        fields: dict[str, Any] = {}
        for field in EDITABLE_FIELDS:
            new_value = _prompt_field(field, record.get(field), input_fn)
            if new_value is not None:
                fields[field] = new_value
        note = _read("note: ", input_fn)
        override = Override(
            episode_id=record["episode_id"], action="edit", fields=fields,
            reviewed_at=_now(), note=note,
        )
        return override, "edited"
    if action == "r":
        note = _read("note: ", input_fn)
        override = Override(
            episode_id=record["episode_id"], action="reject", reviewed_at=_now(), note=note
        )
        return override, "rejected"
    print(f"unknown action {action!r}; skipping")
    return None, "skipped"


def _build_queue(
    effective: list[dict],
    status: str,
    episode_id: str | None,
    reviewed_ids: set[str],
    include_reviewed: bool,
) -> list[dict]:
    queue = [
        r
        for r in effective
        if (status == "all" or r["status"] == status)
        and (episode_id is None or r["episode_id"] == episode_id)
        and (include_reviewed or r["episode_id"] not in reviewed_ids)
    ]
    queue.sort(key=lambda r: r["episode_id"])
    return queue


def main(argv: list[str] | None = None, input_fn=input) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--status",
        choices=["needs_review", "explained", "unexplained", "all"],
        default="needs_review",
    )
    parser.add_argument("--episode-id", default=None)
    parser.add_argument("--include-reviewed", action="store_true")
    parser.add_argument("--events-path", default=str(SETTINGS.events_path))
    parser.add_argument("--overrides-path", default=str(SETTINGS.event_overrides_path))
    parser.add_argument("--episodes-path", default=str(SETTINGS.episodes_path))
    args = parser.parse_args(argv)

    events_path = Path(args.events_path)
    overrides_path = Path(args.overrides_path)
    episodes_path = Path(args.episodes_path)

    episodes_df = load_episodes(episodes_path)
    episodes_by_id = episodes_df.set_index("episode_id").to_dict("index")

    overrides = load_event_overrides(overrides_path)
    reviewed_ids = {o.episode_id for o in overrides}
    effective = load_effective_events(events_path, overrides_path)

    queue = _build_queue(
        effective, args.status, args.episode_id, reviewed_ids, args.include_reviewed
    )

    counts = {"accepted": 0, "edited": 0, "rejected": 0, "skipped": 0}

    for record in queue:
        _display_record(record, episodes_by_id.get(record["episode_id"]))
        try:
            override, outcome = _process_record(record, input_fn)
        except _Quit:
            break
        if outcome == "quit":
            break
        counts[outcome] += 1
        if override is not None:
            overrides = upsert_override(overrides, override)
            write_event_overrides(overrides, overrides_path)

    remaining = sum(
        1
        for r in load_effective_events(events_path, overrides_path)
        if r["status"] == "needs_review"
    )
    print(
        f"accepted={counts['accepted']} edited={counts['edited']} "
        f"rejected={counts['rejected']} skipped={counts['skipped']} "
        f"remaining_needs_review={remaining}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
