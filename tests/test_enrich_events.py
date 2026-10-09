"""End-to-end tests for jobs/enrich_events.py: NullProvider happy path, incremental
re-runs (NEWS-06), the committed-events-path refusal, filters/caps, dry-run, and the
"claude" provider's env-key handling, preflight, spend ledger, budget guard, failure
accounting and --escalate-needs-review (03-02).

No network: "claude"-provider tests monkeypatch jobs.enrich_events.make_client with a
FakeClaudeClient so jobs/claude_provider.py's real anthropic.Anthropic client is never
constructed.
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace

import pandas as pd
import pytest

from core.config import SETTINGS
from core.storage import load_spend_ledger, write_episodes, write_events, write_spend_ledger
from jobs import enrich_events

SENTINEL_KEY = "TESTKEY-DO-NOT-LEAK"


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


# --- "claude" provider: env key, preflight, spend ledger, budget guard, escalation ---


def _claude_response(
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    web_search_requests: int = 0,
    status: str = "unexplained",
    confidence: float = 0.9,
) -> dict:
    answer = {
        "status": status,
        "headline": "Test headline",
        "summary": "Test summary.",
        "category": "other",
        "region": "Global",
        "drivers": [],
        "sources": [],
        "confidence": confidence,
        "conflicting_sources": False,
    }
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "server_tool_use": {"web_search_requests": web_search_requests},
        },
        "content": [{"type": "text", "text": json.dumps(answer), "citations": []}],
    }


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def model_dump(self) -> dict:
        return copy.deepcopy(self._payload)


class _FakeModels:
    def __init__(self, raise_on_retrieve: Exception | None = None):
        self.raise_on_retrieve = raise_on_retrieve
        self.calls: list[str] = []

    def retrieve(self, model: str):
        self.calls.append(model)
        if self.raise_on_retrieve is not None:
            raise self.raise_on_retrieve


class _FakeMessages:
    def __init__(self, responses: list | None = None):
        self._responses = list(responses or [])
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = self._responses.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return _FakeResponse(payload)


class FakeClaudeClient:
    def __init__(self, responses: list | None = None, raise_on_retrieve: Exception | None = None):
        self.models = _FakeModels(raise_on_retrieve)
        self.messages = _FakeMessages(responses)


@pytest.fixture
def three_closed_episodes(tmp_path):
    """Three closed episodes, no open ones -- for the mid-run failure test."""
    rows = [
        _episode_row(
            "2020-03-16_shock",
            start_date="2020-03-13", end_date="2020-03-16", anchor_date="2020-03-16",
            direction="down", trigger="shock",
            search_from="2020-03-13", search_to="2020-03-17",
            status="closed",
            scheduled_releases=[], unscheduled_releases=[], catalyst="surprise",
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
            status="closed",
            scheduled_releases=[], unscheduled_releases=[], catalyst="surprise",
        ),
    ]
    df = pd.DataFrame(rows)
    path = tmp_path / "episodes.parquet"
    write_episodes(df, path)
    return path


def test_claude_missing_key_exits_1_and_writes_nothing(
    tiny_episodes, tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv(SETTINGS.anthropic_api_key_env, raising=False)
    events_path = tmp_path / "events.json"
    ledger_path = tmp_path / "ledger.json"

    exit_code = enrich_events.main(
        [
            "--provider", "claude",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
            "--ledger-path", str(ledger_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert SETTINGS.anthropic_api_key_env in captured.err
    assert "secret" in captured.err
    assert not events_path.exists()
    assert not ledger_path.exists()


def test_claude_preflight_failure_exits_1_with_zero_create_calls_and_no_ledger_entry(
    tiny_episodes, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv(SETTINGS.anthropic_api_key_env, SENTINEL_KEY)
    fake_client = FakeClaudeClient(raise_on_retrieve=RuntimeError("model not found"))
    monkeypatch.setattr(enrich_events, "make_client", lambda api_key: fake_client)
    events_path = tmp_path / "events.json"
    ledger_path = tmp_path / "ledger.json"

    exit_code = enrich_events.main(
        [
            "--provider", "claude",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
            "--ledger-path", str(ledger_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "not available" in captured.err
    assert len(fake_client.messages.calls) == 0
    assert not ledger_path.exists()
    assert SENTINEL_KEY not in captured.err
    assert SENTINEL_KEY not in captured.out


def test_claude_happy_path_two_episodes_writes_records_and_ledger(
    tiny_episodes, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv(SETTINGS.anthropic_api_key_env, SENTINEL_KEY)
    fake_client = FakeClaudeClient(
        responses=[_claude_response(), _claude_response()]
    )
    monkeypatch.setattr(enrich_events, "make_client", lambda api_key: fake_client)
    events_path = tmp_path / "events.json"
    ledger_path = tmp_path / "ledger.json"

    exit_code = enrich_events.main(
        [
            "--provider", "claude",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
            "--ledger-path", str(ledger_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert SENTINEL_KEY not in captured.out
    assert SENTINEL_KEY not in captured.err

    payload = json.loads(events_path.read_text())
    records = payload["records"]
    assert len(records) == 2
    for record in records:
        assert record["provider"] == "claude"
        assert record["model"] == SETTINGS.news_model
        assert record["prompt_version"] == SETTINGS.news_prompt_version
        assert record["cost_usd"] > 0

    ledger_entries = load_spend_ledger(ledger_path)
    assert len(ledger_entries) == 1
    entry = ledger_entries[0]
    assert SENTINEL_KEY not in json.dumps(entry)
    required_keys = {
        "run_id", "provider", "model", "prompt_version", "episodes_attempted",
        "episodes_written", "failures", "input_tokens", "output_tokens",
        "web_search_requests", "cost_usd", "mode",
    }
    assert required_keys <= entry.keys()
    assert entry["episodes_attempted"] == 2
    assert entry["episodes_written"] == 2
    assert entry["failures"] == 0
    assert entry["mode"] == "backfill"

    lines = [
        line for line in captured.out.splitlines()
        if line.startswith("episode ")
    ]
    assert len(lines) == 2
    for line in lines:
        assert "status=" in line
        assert "searches=" in line
        assert "cost=" in line


def test_claude_budget_guard_pre_existing_ledger_blocks_run(
    tiny_episodes, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv(SETTINGS.anthropic_api_key_env, SENTINEL_KEY)
    fake_client = FakeClaudeClient(responses=[_claude_response(), _claude_response()])
    monkeypatch.setattr(enrich_events, "make_client", lambda api_key: fake_client)

    ledger_path = tmp_path / "ledger.json"
    write_spend_ledger(
        [
            {
                "run_id": "prior-run",
                "provider": "claude",
                "model": SETTINGS.news_model,
                "prompt_version": SETTINGS.news_prompt_version,
                "episodes_attempted": 100,
                "episodes_written": 100,
                "failures": 0,
                "input_tokens": 1,
                "output_tokens": 1,
                "web_search_requests": 1,
                "cost_usd": 24.90,
                "mode": "backfill",
            }
        ],
        ledger_path,
    )
    events_path = tmp_path / "events.json"

    exit_code = enrich_events.main(
        [
            "--provider", "claude",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
            "--ledger-path", str(ledger_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "budget" in captured.err
    assert len(fake_client.messages.calls) == 0
    assert not events_path.exists()

    ledger_entries = load_spend_ledger(ledger_path)
    assert len(ledger_entries) == 1
    assert ledger_entries[0]["run_id"] == "prior-run"


def test_claude_budget_guard_stops_mid_run_keeping_written_records(
    tiny_episodes, tmp_path, monkeypatch, capsys
):
    # claude-haiku-5-5 input price is $0.10/MTok -- 1,000,000 input tokens costs
    # exactly $0.10/episode with no output tokens and no web searches.
    fake_settings = replace(
        SETTINGS, news_budget_usd=0.1499, news_episode_cost_reserve_usd=0.05,
    )
    monkeypatch.setattr(enrich_events, "SETTINGS", fake_settings)
    monkeypatch.setenv(SETTINGS.anthropic_api_key_env, SENTINEL_KEY)
    fake_client = FakeClaudeClient(
        responses=[
            _claude_response(input_tokens=1_000_000, output_tokens=0),
            _claude_response(input_tokens=1_000_000, output_tokens=0),
        ]
    )
    monkeypatch.setattr(enrich_events, "make_client", lambda api_key: fake_client)
    events_path = tmp_path / "events.json"
    ledger_path = tmp_path / "ledger.json"

    exit_code = enrich_events.main(
        [
            "--provider", "claude",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
            "--ledger-path", str(ledger_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "budget" in captured.err
    assert len(fake_client.messages.calls) == 1

    payload = json.loads(events_path.read_text())
    assert len(payload["records"]) == 1

    ledger_entries = load_spend_ledger(ledger_path)
    assert len(ledger_entries) == 1
    assert ledger_entries[0]["episodes_written"] == 1
    assert ledger_entries[0]["cost_usd"] == pytest.approx(0.10)


def test_claude_episode_failure_continues_and_records_failure_in_ledger(
    three_closed_episodes, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv(SETTINGS.anthropic_api_key_env, SENTINEL_KEY)
    fake_client = FakeClaudeClient(
        responses=[
            _claude_response(),
            RuntimeError("transient failure"),
            _claude_response(),
        ]
    )
    monkeypatch.setattr(enrich_events, "make_client", lambda api_key: fake_client)
    events_path = tmp_path / "events.json"
    ledger_path = tmp_path / "ledger.json"

    exit_code = enrich_events.main(
        [
            "--provider", "claude",
            "--episodes-path", str(three_closed_episodes),
            "--events-path", str(events_path),
            "--ledger-path", str(ledger_path),
        ]
    )

    assert exit_code == 1

    payload = json.loads(events_path.read_text())
    ids = {r["episode_id"] for r in payload["records"]}
    assert ids == {"2020-03-16_shock", "2020-04-01_rally"}

    ledger_entries = load_spend_ledger(ledger_path)
    assert len(ledger_entries) == 1
    assert ledger_entries[0]["failures"] == 1
    assert ledger_entries[0]["episodes_attempted"] == 3
    assert ledger_entries[0]["episodes_written"] == 2


def test_escalate_needs_review_only_resends_matching_records(
    tiny_episodes, tmp_path, monkeypatch
):
    monkeypatch.setenv(SETTINGS.anthropic_api_key_env, SENTINEL_KEY)
    fake_client = FakeClaudeClient(responses=[_claude_response(status="explained", confidence=0.9)])
    monkeypatch.setattr(enrich_events, "make_client", lambda api_key: fake_client)

    events_path = tmp_path / "events.json"
    needs_review_record = _hand_built_record(
        "2020-03-16_shock", scheduled=False, enriched_at="2026-01-01T00:00:00Z"
    )
    needs_review_record["status"] = "needs_review"
    needs_review_record["model"] = SETTINGS.news_model
    already_escalated_record = _hand_built_record(
        "2020-03-23_drawdown", scheduled=False, enriched_at="2026-01-01T00:00:00Z"
    )
    already_escalated_record["status"] = "needs_review"
    already_escalated_record["model"] = SETTINGS.news_escalation_model
    write_events([needs_review_record, already_escalated_record], events_path)
    ledger_path = tmp_path / "ledger.json"

    exit_code = enrich_events.main(
        [
            "--provider", "claude",
            "--escalate-needs-review",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
            "--ledger-path", str(ledger_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(events_path.read_text())
    records_by_id = {r["episode_id"]: r for r in payload["records"]}
    assert records_by_id["2020-03-16_shock"]["model"] == SETTINGS.news_escalation_model
    # Already-escalated record must be left untouched -- only one create() call made.
    assert records_by_id["2020-03-23_drawdown"]["model"] == SETTINGS.news_escalation_model
    assert records_by_id["2020-03-23_drawdown"]["enriched_at"] == "2026-01-01T00:00:00Z"
    assert len(fake_client.messages.calls) == 1

    ledger_entries = load_spend_ledger(ledger_path)
    assert ledger_entries[0]["mode"] == "escalation"


def test_escalate_needs_review_requires_claude_provider(tiny_episodes, tmp_path, capsys):
    events_path = tmp_path / "events.json"
    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--escalate-needs-review",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "escalat" in captured.err.lower()
    assert not events_path.exists()


def test_null_provider_never_creates_or_modifies_ledger(tiny_episodes, tmp_path):
    events_path = tmp_path / "events.json"
    ledger_path = tmp_path / "ledger.json"

    exit_code = enrich_events.main(
        [
            "--provider", "null",
            "--episodes-path", str(tiny_episodes),
            "--events-path", str(events_path),
            "--ledger-path", str(ledger_path),
        ]
    )

    assert exit_code == 0
    assert not ledger_path.exists()
