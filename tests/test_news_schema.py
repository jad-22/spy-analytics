"""Unit tests for core/news/schema.py: the code-enforced status rules (NEWS-03/NEWS-04),
pydantic field validation, and the EnrichmentRecord round-trip. All hand-built fixtures,
no network.
"""
from __future__ import annotations

from datetime import date

import pydantic
import pytest

from core.config import SETTINGS
from core.news.schema import (
    EnrichmentRecord,
    Source,
    Status,
    Usage,
    apply_status_rules,
    is_current_record,
)


@pytest.mark.parametrize(
    "status, n_sources, confidence, conflicting, reviewed, expected",
    [
        ("explained", 0, 0.9, False, False, "unexplained"),
        ("explained", 1, 0.49, False, False, "needs_review"),
        ("explained", 1, 0.5, False, False, "explained"),
        ("explained", 1, 0.9, True, False, "needs_review"),
        ("needs_review", 2, 0.95, False, False, "needs_review"),
        ("unexplained", 2, 0.95, False, False, "unexplained"),
        ("needs_review", 1, 0.2, False, True, "needs_review"),
        ("explained", 1, 0.2, False, True, "explained"),
        ("explained", 0, 0.9, False, True, "unexplained"),
    ],
)
def test_apply_status_rules(status, n_sources, confidence, conflicting, reviewed, expected):
    result: Status = apply_status_rules(
        status, n_sources, confidence, conflicting, reviewed, threshold=0.5
    )
    assert result == expected


def test_source_rejects_non_http_url():
    with pytest.raises(pydantic.ValidationError):
        Source(title="t", url="ftp://example.com", publisher="p", published=date(2020, 1, 1))


def _sample_record(**overrides) -> EnrichmentRecord:
    fields = {
        "episode_id": "2020-03-16_shock",
        "status": "explained",
        "headline": "Fed signals emergency action",
        "summary": "Sourced summary of the move.",
        "category": "monetary_policy",
        "region": "US",
        "scheduled": True,
        "drivers": ["rate cut"],
        "sources": [
            Source(
                title="Reuters report",
                url="https://example.com/story",
                publisher="Reuters",
                published=date(2020, 3, 16),
            )
        ],
        "confidence": 0.9,
        "conflicting_sources": False,
        "reviewed": False,
        "rejected": False,
        "provider": "claude",
        "model": SETTINGS.news_model,
        "prompt_version": SETTINGS.news_prompt_version,
        "web_search_tool": SETTINGS.web_search_tool_type,
        "enriched_at": "2026-01-01T00:00:00Z",
        "search_from": date(2020, 3, 13),
        "search_to": date(2020, 3, 17),
        "usage": Usage(input_tokens=100, output_tokens=50, web_search_requests=1),
        "cost_usd": 0.01,
        "stop_reasons": ["end_turn"],
        "dropped_sources": [],
        "raw_response": None,
    }
    fields.update(overrides)
    return EnrichmentRecord(**fields)


def test_enrichment_record_round_trips_through_json():
    record = _sample_record()
    dumped = record.model_dump(mode="json")
    rebuilt = EnrichmentRecord.model_validate(dumped)
    assert rebuilt == record


def test_is_current_record_null_provider_never_current():
    assert is_current_record({"provider": "null", "prompt_version": "v1"}, "v1") is False


def test_is_current_record_prompt_version_mismatch_not_current():
    assert is_current_record({"provider": "claude", "prompt_version": "v0"}, "v1") is False


def test_is_current_record_claude_current_version_is_current():
    assert is_current_record({"provider": "claude", "prompt_version": "v1"}, "v1") is True
