"""Unit tests for jobs/claude_provider.py: ClaudeSearchProvider composes web search +
structured output, handles pause_turn continuation, cross-validates sources, and never
leaks the API key into an error message. No network -- a FakeClient replaces
anthropic.Anthropic entirely; httpx2 is this environment's installed httpx distribution,
used only to construct real anthropic exception instances for the retry test.
"""
from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

import anthropic
import httpx2 as httpx
import pytest

from core.config import SETTINGS
from core.news.prompt import SYSTEM_PROMPT
from core.news.schema import Episode
from jobs.claude_provider import ClaudeSearchProvider

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "news"
SENTINEL_KEY = "TESTKEY-DO-NOT-LEAK"


def _load_fixture(name: str) -> dict:
    data = json.loads((FIXTURES_DIR / name).read_text())
    data.pop("_comment", None)
    return data


EXPLAINED_FIXTURE = _load_fixture("claude_response_explained.json")
PAUSE_TURN_FIXTURE = _load_fixture("claude_response_pause_turn.json")


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def model_dump(self) -> dict:
        return copy.deepcopy(self._payload)


class FakeMessages:
    def __init__(self, responses=None, exceptions=None):
        self._responses = list(responses or [])
        self._exceptions = list(exceptions or [])
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exceptions:
            raise self._exceptions.pop(0)
        return FakeResponse(self._responses.pop(0))


class FakeClient:
    def __init__(self, responses=None, exceptions=None):
        self.messages = FakeMessages(responses, exceptions)


EPISODE_WINDOW = Episode(
    episode_id="2020-03-09_shock",
    start_date=date(2020, 3, 6),
    end_date=date(2020, 3, 10),
    anchor_date=date(2020, 3, 9),
    direction="down",
    trigger="shock",
    move_pct=-0.08,
    search_from=date(2020, 3, 6),
    search_to=date(2020, 3, 10),
    status="closed",
    scheduled_releases=[],
    unscheduled_releases=[],
    catalyst="surprise",
)


def _provider(client) -> ClaudeSearchProvider:
    return ClaudeSearchProvider(
        client, model="claude-haiku-5-5", settings=SETTINGS, retry_wait_max=0
    )


def test_explain_cross_validates_sources_and_returns_explained():
    client = FakeClient(responses=[EXPLAINED_FIXTURE])
    provider = _provider(client)

    enrichment = provider.explain(EPISODE_WINDOW)

    assert enrichment.explanation.status == "explained"
    assert len(enrichment.explanation.sources) == 1
    kept = enrichment.explanation.sources[0]
    assert kept.url == "https://a.example.com/in-window"
    assert kept.title == "In-window story"
    assert kept.published == date(2020, 3, 9)

    dropped_reasons = {d.url: d.reason for d in enrichment.dropped_sources}
    assert dropped_reasons["https://b.example.com/outside-window"] == "outside_window"
    assert dropped_reasons["https://c.example.com/never-searched"] == "not_in_search_results"

    assert enrichment.usage.input_tokens == 1200
    assert enrichment.usage.output_tokens == 300
    assert enrichment.usage.web_search_requests == 1
    assert enrichment.stop_reasons == ["end_turn"]
    assert enrichment.provider == "claude"
    assert enrichment.model == "claude-haiku-5-5"
    assert enrichment.web_search_tool == SETTINGS.web_search_tool_type


def test_explain_null_page_age_in_window_source_becomes_unexplained():
    fixture = copy.deepcopy(EXPLAINED_FIXTURE)
    fixture["content"][1]["content"][0]["page_age"] = None
    client = FakeClient(responses=[fixture])
    provider = _provider(client)

    enrichment = provider.explain(EPISODE_WINDOW)

    assert enrichment.explanation.status == "unexplained"
    assert enrichment.explanation.sources == []


def test_explain_low_confidence_becomes_needs_review():
    fixture = copy.deepcopy(EXPLAINED_FIXTURE)
    text_block = fixture["content"][2]
    answer = json.loads(text_block["text"])
    answer["confidence"] = 0.3
    text_block["text"] = json.dumps(answer)
    client = FakeClient(responses=[fixture])
    provider = _provider(client)

    enrichment = provider.explain(EPISODE_WINDOW)

    assert enrichment.explanation.status == "needs_review"


def test_explain_conflicting_sources_becomes_needs_review():
    fixture = copy.deepcopy(EXPLAINED_FIXTURE)
    text_block = fixture["content"][2]
    answer = json.loads(text_block["text"])
    answer["conflicting_sources"] = True
    text_block["text"] = json.dumps(answer)
    client = FakeClient(responses=[fixture])
    provider = _provider(client)

    enrichment = provider.explain(EPISODE_WINDOW)

    assert enrichment.explanation.status == "needs_review"


def test_explain_handles_pause_turn_continuation():
    client = FakeClient(responses=[PAUSE_TURN_FIXTURE, EXPLAINED_FIXTURE])
    provider = _provider(client)

    enrichment = provider.explain(EPISODE_WINDOW)

    assert len(client.messages.calls) == 2
    assert enrichment.stop_reasons == ["pause_turn", "end_turn"]
    assert enrichment.usage.input_tokens == 500 + 1200
    assert enrichment.usage.output_tokens == 50 + 300
    assert enrichment.usage.web_search_requests == 1 + 1

    second_call = client.messages.calls[1]
    assert second_call["messages"][-1]["role"] == "assistant"
    assert second_call["messages"][-1]["content"] == PAUSE_TURN_FIXTURE["content"]
    assert second_call["tools"][0]["max_uses"] == SETTINGS.news_max_searches_per_request - 1


def test_explain_raises_after_too_many_pause_turn_continuations():
    responses = [PAUSE_TURN_FIXTURE] * (SETTINGS.news_max_continuations + 2)
    client = FakeClient(responses=responses)
    provider = _provider(client)

    with pytest.raises(ValueError) as exc_info:
        provider.explain(EPISODE_WINDOW)
    assert EPISODE_WINDOW.episode_id in str(exc_info.value)


def test_explain_raises_on_max_tokens_stop_reason():
    fixture = copy.deepcopy(PAUSE_TURN_FIXTURE)
    fixture["stop_reason"] = "max_tokens"
    client = FakeClient(responses=[fixture])
    provider = _provider(client)

    with pytest.raises(ValueError) as exc_info:
        provider.explain(EPISODE_WINDOW)
    assert EPISODE_WINDOW.episode_id in str(exc_info.value)


def test_explain_raises_on_refusal_stop_reason():
    fixture = copy.deepcopy(PAUSE_TURN_FIXTURE)
    fixture["stop_reason"] = "refusal"
    client = FakeClient(responses=[fixture])
    provider = _provider(client)

    with pytest.raises(ValueError) as exc_info:
        provider.explain(EPISODE_WINDOW)
    assert EPISODE_WINDOW.episode_id in str(exc_info.value)


def test_every_call_passes_model_tools_and_output_config():
    client = FakeClient(responses=[EXPLAINED_FIXTURE])
    provider = _provider(client)
    provider.explain(EPISODE_WINDOW)

    call = client.messages.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["max_tokens"] == SETTINGS.news_max_output_tokens
    assert call["system"] == SYSTEM_PROMPT
    assert call["tools"][0]["type"] == SETTINGS.web_search_tool_type
    assert call["tools"][0]["name"] == "web_search"
    assert call["tools"][0]["max_uses"] == SETTINGS.news_max_searches_per_request
    assert call["output_config"]["format"]["type"] == "json_schema"


def test_fake_client_exception_with_sentinel_key_does_not_leak():
    exc = RuntimeError(f"auth failed for key={SENTINEL_KEY}")
    client = FakeClient(exceptions=[exc])
    provider = _provider(client)

    with pytest.raises(ValueError) as exc_info:
        provider.explain(EPISODE_WINDOW)
    assert SENTINEL_KEY not in str(exc_info.value)
    assert EPISODE_WINDOW.episode_id in str(exc_info.value)


def test_retryable_errors_are_retried_fetch_attempts_times():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(429, request=req)
    exceptions = [
        anthropic.RateLimitError("rate limited", response=resp, body=None)
        for _ in range(SETTINGS.fetch_attempts)
    ]
    client = FakeClient(exceptions=exceptions)
    provider = _provider(client)

    with pytest.raises(ValueError):
        provider.explain(EPISODE_WINDOW)
    assert len(client.messages.calls) == SETTINGS.fetch_attempts


def test_raw_response_is_sanitized_list_with_no_encrypted_keys():
    client = FakeClient(responses=[EXPLAINED_FIXTURE])
    provider = _provider(client)

    enrichment = provider.explain(EPISODE_WINDOW)

    dumped = json.dumps(enrichment.raw_response)
    assert "encrypted_content" not in dumped
    assert "encrypted_index" not in dumped
    assert "cited_text" not in dumped
    assert isinstance(enrichment.raw_response, list)
    assert len(enrichment.raw_response) == 1
