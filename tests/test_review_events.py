"""Tests for scripts/review_events.py: the local-only accept/edit/reject CLI (REV-01).

No network. main() is driven with a scripted input_fn so no real stdin/tty is needed.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import pytest

from core.storage import load_event_overrides, write_episodes, write_events
from scripts import review_events

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "review_events.py"

ONE_SOURCE = [
    {
        "title": "Example source",
        "url": "https://example.com/story",
        "publisher": "Example Wire",
        "published": "2020-03-16",
    }
]


def _record(
    episode_id: str,
    *,
    status: str,
    sources: list[dict] | None = None,
    headline: str = "Original headline",
    summary: str = "Original summary.",
    category: str = "other",
    region: str = "Global",
    confidence: float = 0.9,
) -> dict:
    return {
        "episode_id": episode_id,
        "status": status,
        "headline": headline,
        "summary": summary,
        "category": category,
        "region": region,
        "scheduled": True,
        "drivers": [],
        "sources": ONE_SOURCE if sources is None else sources,
        "confidence": confidence,
        "conflicting_sources": False,
        "reviewed": False,
        "rejected": False,
        "provider": "claude",
        "model": "claude-haiku-5-5",
        "prompt_version": "v1",
        "web_search_tool": "web_search_20250305",
        "enriched_at": "2026-01-01T00:00:00Z",
        "search_from": "2020-03-13",
        "search_to": "2020-03-17",
        "usage": {"input_tokens": 100, "output_tokens": 50, "web_search_requests": 1},
        "cost_usd": 0.01,
        "stop_reasons": ["end_turn"],
        "dropped_sources": [],
        "raw_response": None,
    }


def _episode_row(episode_id: str, *, direction: str = "down", move_pct: float = -0.08, catalyst: str = "surprise") -> dict:
    return {
        "episode_id": episode_id,
        "start_date": pd.Timestamp("2020-03-13"),
        "end_date": pd.Timestamp("2020-03-16"),
        "anchor_date": pd.Timestamp("2020-03-16"),
        "direction": direction,
        "trigger": "shock",
        "move_pct": move_pct,
        "search_from": pd.Timestamp("2020-03-13"),
        "search_to": pd.Timestamp("2020-03-17"),
        "status": "closed",
        "scheduled_releases": [],
        "unscheduled_releases": [],
        "catalyst": catalyst,
    }


@pytest.fixture
def three_records(tmp_path):
    """needs_review, explained, unexplained -- one of each -- plus matching episode rows."""
    events_path = tmp_path / "events.json"
    overrides_path = tmp_path / "event_overrides.json"
    episodes_path = tmp_path / "episodes.parquet"

    records = [
        _record("2020-03-16_shock", status="needs_review"),
        _record("2020-05-01_rally", status="explained"),
        _record("2020-06-01_drawdown", status="unexplained", sources=[]),
    ]
    write_events(records, events_path)

    episodes_df = pd.DataFrame(
        [
            _episode_row("2020-03-16_shock"),
            _episode_row("2020-05-01_rally", direction="up", move_pct=0.08, catalyst="scheduled"),
            _episode_row("2020-06-01_drawdown"),
        ]
    )
    write_episodes(episodes_df, episodes_path)

    return events_path, overrides_path, episodes_path


def _main(three_records, answers, **extra_args):
    events_path, overrides_path, episodes_path = three_records
    argv = [
        "--events-path", str(events_path),
        "--overrides-path", str(overrides_path),
        "--episodes-path", str(episodes_path),
    ]
    for flag, value in extra_args.items():
        cli_flag = "--" + flag.replace("_", "-")
        if value is True:
            argv.append(cli_flag)
        else:
            argv += [cli_flag, str(value)]
    exit_code = review_events.main(argv, input_fn=iter(answers).__next__)
    return exit_code, events_path, overrides_path


def test_default_queue_accept_writes_override_without_touching_events(three_records):
    events_path, overrides_path, _ = three_records
    before = events_path.read_bytes()

    exit_code, events_path, overrides_path = _main(three_records, ["a"])

    assert exit_code == 0
    assert events_path.read_bytes() == before
    overrides = load_event_overrides(overrides_path)
    assert len(overrides) == 1
    assert overrides[0].episode_id == "2020-03-16_shock"
    assert overrides[0].action == "accept"


def test_edit_overlays_only_provided_fields_with_note(three_records):
    exit_code, _, overrides_path = _main(
        three_records,
        ["e", "Better headline", "", "geopolitics", "", "", "", "fixed cause"],
    )

    assert exit_code == 0
    overrides = load_event_overrides(overrides_path)
    assert len(overrides) == 1
    override = overrides[0]
    assert override.action == "edit"
    assert override.fields == {"headline": "Better headline", "category": "geopolitics"}
    assert override.note == "fixed cause"


def test_invalid_category_reprompts_then_leaves_unchanged(three_records):
    exit_code, _, overrides_path = _main(
        three_records,
        ["e", "", "", "bogus", "bogus", "bogus", "", "", "", "note"],
    )

    assert exit_code == 0
    overrides = load_event_overrides(overrides_path)
    override = overrides[0]
    assert "category" not in override.fields


def test_reject_saves_override_with_note(three_records):
    exit_code, events_path, overrides_path = _main(three_records, ["r", "wrong story"])
    before = events_path.read_bytes()

    assert exit_code == 0
    overrides = load_event_overrides(overrides_path)
    override = overrides[0]
    assert override.action == "reject"
    assert override.note == "wrong story"
    assert events_path.read_bytes() == before


def test_skip_writes_nothing(three_records):
    exit_code, _, overrides_path = _main(three_records, ["s"])

    assert exit_code == 0
    assert not overrides_path.exists()


def test_quit_stops_immediately_and_returns_zero(three_records):
    exit_code, _, overrides_path = _main(three_records, ["q"])

    assert exit_code == 0
    assert not overrides_path.exists()


def test_eof_from_input_fn_exits_cleanly(three_records):
    exit_code, _, overrides_path = _main(three_records, [])

    assert exit_code == 0
    assert not overrides_path.exists()


def test_status_and_episode_id_filter_reaches_explained_record(three_records):
    exit_code, _, overrides_path = _main(
        three_records,
        ["a"],
        status="explained",
        episode_id="2020-05-01_rally",
    )

    assert exit_code == 0
    overrides = load_event_overrides(overrides_path)
    assert len(overrides) == 1
    assert overrides[0].episode_id == "2020-05-01_rally"


def test_include_reviewed_flag_controls_visibility(three_records):
    # First session: accept the already-explained record (status doesn't change, but
    # it now has an override on file).
    exit_code, _, overrides_path = _main(
        three_records, ["a"], status="explained", episode_id="2020-05-01_rally"
    )
    assert exit_code == 0
    overrides_after = load_event_overrides(overrides_path)
    assert len(overrides_after) == 1
    assert overrides_after[0].action == "accept"

    # Without --include-reviewed, the explained queue is now empty (already has an
    # override), so no prompt is read -- an empty answers iterator must not raise.
    exit_code, _, overrides_path = _main(three_records, [], status="explained")
    assert exit_code == 0
    overrides_after = load_event_overrides(overrides_path)
    assert len(overrides_after) == 1  # unchanged

    # With --include-reviewed, the already-overridden record reappears and can be
    # reviewed again (reject this time).
    exit_code, _, overrides_path = _main(
        three_records, ["r", "reconsidered"], status="explained", include_reviewed=True
    )
    assert exit_code == 0
    overrides_after = load_event_overrides(overrides_path)
    assert len(overrides_after) == 1
    assert overrides_after[0].action == "reject"


def test_drivers_edited_as_comma_list_become_list(three_records):
    exit_code, _, overrides_path = _main(
        three_records,
        ["e", "", "", "", "", "a, b", "", "note"],
    )

    assert exit_code == 0
    overrides = load_event_overrides(overrides_path)
    assert overrides[0].fields == {"drivers": ["a", "b"]}


def test_display_shows_expected_record_fields(three_records, capsys):
    _main(three_records, ["a"])
    captured = capsys.readouterr()

    assert "2020-03-16_shock" in captured.out
    assert "needs_review" in captured.out
    assert "Original headline" in captured.out
    assert "Original summary." in captured.out
    assert "other" in captured.out
    assert "Global" in captured.out
    assert "2020-03-16" in captured.out
    assert "down" in captured.out
    assert "Example Wire" in captured.out
    assert "https://example.com/story" in captured.out
    assert "dropped_sources: 0" in captured.out


def test_summary_line_reports_counts(three_records, capsys):
    exit_code, _, _ = _main(three_records, ["a"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "accepted=1 edited=0 rejected=0 skipped=0" in captured.out
    assert "remaining_needs_review=0" in captured.out


def test_no_jobs_anthropic_or_requests_imports():
    tree = ast.parse(SCRIPT_PATH.read_text(), filename=str(SCRIPT_PATH))
    forbidden = {"jobs", "anthropic", "requests", "httpx", "urllib", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden, f"forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in forbidden, f"forbidden import: {node.module}"


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc_info:
        review_events.main(["--help"])
    assert exc_info.value.code == 0


def test_accept_events_file_byte_identical_through_full_session(three_records):
    events_path, _, _ = three_records
    before = events_path.read_bytes()

    exit_code, _, _ = _main(
        three_records,
        ["a"],
        status="all",
    )
    assert exit_code == 0
    assert events_path.read_bytes() == before

    # Edit a second record, then reject a third, confirming events.json never moves.
    payload = json.loads(events_path.read_text())
    assert payload["records"]
    assert events_path.read_bytes() == before
