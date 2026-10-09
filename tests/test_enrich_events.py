"""End-to-end tests for jobs/enrich_events.py: NullProvider happy path, incremental
re-runs (NEWS-06), the committed-events-path refusal, filters/caps and dry-run.

No network: every test runs the "null" provider only.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd
import pytest

from core.config import SETTINGS
from core.storage import write_episodes, write_events
from jobs import enrich_events


def _episode_row(
    episode_id: str,
    *,
    start_date: str,
    end_date: str,
    anchor_date: str,
    direction: str,
    trigger: str,
    search_from: str,
    search_to: str,
    status: str,
    scheduled_releases: list[str],
    unscheduled_releases: list[str],
    catalyst: str,
) -> dict:
    return {
        "episode_id": episode_id,
        "start_date": pd.Timestamp(start_date),
        "end_date": pd.Timestamp(end_date),
        "anchor_date": pd.Timestamp(anchor_date),
        "direction": direction,
        "trigger": trigger,
        "triggers": trigger,
        "move_pct": -0.08 if direction == "down" else 0.08,
        "max_z": 3.0,
        "severity": 4.5,
        "search_from": pd.Timestamp(search_from),
        "search_to": pd.Timestamp(search_to),
        "recovery_date": pd.NaT,
        "status": status,
        "detector_version": SETTINGS.detector_version,
        "scheduled_releases": scheduled_releases,
        "unscheduled_releases": unscheduled_releases,
        "catalyst": catalyst,
    }


@pytest.fixture
def tiny_episodes(tmp_path):
    """Three rows: one closed+scheduled, one closed+surprise, one still open."""
    rows = [
        _episode_row(
            "2020-03-16_shock",
            start_date="2020-03-13", end_date="2020-03-16", anchor_date="2020-03-16",
            direction="down", trigger="shock",
            search_from="2020-03-13", search_to="2020-03-17",
            status="closed",
            scheduled_releases=["FOMC 2020-03-15"], unscheduled_releases=[], catalyst="scheduled",
        ),
        _episode_row(
            "2020-03-23_drawdown",
            start_date="2020-03-19", end_date="2020-03-23", anchor_date="2020-03-20",
            direction="down", trigger="drawdown",
            search_from="2020-03-18", search_to="2020-03-24",
            status="closed",
            scheduled_releases=[], unscheduled_releases=[], catalyst="surprise",
        ),
        _episode_row(
            "2020-04-01_rally",
            start_date="2020-03-26", end_date="2020-04-01", anchor_date="2020-03-30",
            direction="up", trigger="rally",
            search_from="2020-03-26", search_to="2020-04-02",
            status="open",
            scheduled_releases=[], unscheduled_releases=[], catalyst="surprise",
        ),
    ]
    df = pd.DataFrame(rows)
    path = tmp_path / "episodes.parquet"
    write_episodes(df, path)
    return path


def _hand_built_record(episode_id: str, *, scheduled: bool, enriched_at: str) -> dict:
    return {
        "episode_id": episode_id,
        "status": "explained",
        "headline": "Hand-built real record",
        "summary": "Pre-existing real record from a prior claude run.",
        "category": "other",
        "region": "Global",
        "scheduled": scheduled,
        "drivers": [],
        "sources": [
            {
                "title": "Example source",
                "url": "https://example.com/story",
                "publisher": "Example Wire",
                "published": "2020-03-16",
            }
        ],
        "confidence": 0.9,
        "conflicting_sources": False,
        "reviewed": False,
        "rejected": False,
        "provider": "claude",
        "model": SETTINGS.news_model,
        "prompt_version": SETTINGS.news_prompt_version,
        "web_search_tool": SETTINGS.web_search_tool_type,
        "enriched_at": enriched_at,
        "search_from": "2020-03-13",
        "search_to": "2020-03-17",
        "usage": {"input_tokens": 100, "output_tokens": 50, "web_search_requests": 1},
        "cost_usd": 0.01,
        "stop_reasons": ["end_turn"],
        "dropped_sources": [],
        "raw_response": None,
    }


def test_null_run_writes_one_record_per_closed_episode(tiny_episodes, tmp_path):
    events_path = tmp_path / "events.json"
    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(events_path.read_text())
    assert payload["schema_version"] == 1
    records = payload["records"]
    ids = [r["episode_id"] for r in records]
    assert ids == sorted(["2020-03-16_shock", "2020-03-23_drawdown"])

    required_keys = {
        "model", "prompt_version", "enriched_at", "usage", "cost_usd", "raw_response",
        "search_from", "search_to",
    }
    for record in records:
        assert record["status"] == "unexplained"
        assert record["provider"] == "null"
        assert required_keys <= record.keys()

    scheduled_record = next(r for r in records if r["episode_id"] == "2020-03-16_shock")
    surprise_record = next(r for r in records if r["episode_id"] == "2020-03-23_drawdown")
    assert scheduled_record["scheduled"] is True
    assert surprise_record["scheduled"] is False


def test_open_episodes_are_skipped(tiny_episodes, tmp_path):
    events_path = tmp_path / "events.json"
    enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
        ]
    )
    payload = json.loads(events_path.read_text())
    ids = [r["episode_id"] for r in payload["records"]]
    assert "2020-04-01_rally" not in ids


def test_rerun_with_real_records_is_idempotent(tiny_episodes, tmp_path, capsys):
    events_path = tmp_path / "events.json"
    records = [
        _hand_built_record(
            "2020-03-16_shock", scheduled=True, enriched_at="2026-01-01T00:00:00Z"
        ),
        _hand_built_record(
            "2020-03-23_drawdown", scheduled=False, enriched_at="2026-01-01T00:00:00Z"
        ),
    ]
    write_events(records, events_path)
    before = events_path.read_bytes()

    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert events_path.read_bytes() == before
    assert "0 pending" in captured.out


def test_null_records_are_not_current(tiny_episodes, tmp_path, capsys):
    events_path = tmp_path / "events.json"
    enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
        ]
    )
    capsys.readouterr()  # discard first run's output

    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "2 pending" in captured.out


def test_null_provider_refuses_committed_events_path(tiny_episodes, tmp_path, monkeypatch, capsys):
    fake_committed = tmp_path / "committed_events.json"
    fake_settings = replace(SETTINGS, events_path=fake_committed)
    monkeypatch.setattr(enrich_events, "SETTINGS", fake_settings)
    existed_before = fake_committed.exists()

    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "refusing" in captured.err
    assert fake_committed.exists() == existed_before


def test_episode_ids_filter_and_cap(tiny_episodes, tmp_path):
    one_id_path = tmp_path / "events_one_id.json"
    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(one_id_path),
            "--episode-ids", "2020-03-23_drawdown",
        ]
    )
    assert exit_code == 0
    payload = json.loads(one_id_path.read_text())
    assert [r["episode_id"] for r in payload["records"]] == ["2020-03-23_drawdown"]

    capped_path = tmp_path / "events_capped.json"
    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(capped_path),
            "--max-episodes", "1",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capped_path.read_text())
    # earliest pending by start_date is 2020-03-16_shock (start 2020-03-13)
    assert [r["episode_id"] for r in payload["records"]] == ["2020-03-16_shock"]

    over_cap_path = tmp_path / "events_over_cap.json"
    over_cap = SETTINGS.news_max_episodes_per_run + 1
    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(over_cap_path),
            "--max-episodes", str(over_cap),
        ]
    )
    assert exit_code == 1
    assert not over_cap_path.exists()

    bad_format_path = tmp_path / "events_bad_format.json"
    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(bad_format_path),
            "--episode-ids", "not-a-real-id",
        ]
    )
    assert exit_code == 1
    assert not bad_format_path.exists()

    unknown_id_path = tmp_path / "events_unknown_id.json"
    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(unknown_id_path),
            "--episode-ids", "2099-01-01_shock",
        ]
    )
    assert exit_code == 1
    assert not unknown_id_path.exists()


def test_dry_run_writes_nothing(tiny_episodes, tmp_path, capsys):
    events_path = tmp_path / "events.json"
    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "2 pending" in captured.out
    assert not events_path.exists()
