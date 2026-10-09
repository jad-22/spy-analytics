"""Unit tests for core/news/overrides.py: Override model and the pure, read-time
merge (REV-02). All records are hand-built dicts shaped like
EnrichmentRecord.model_dump(mode="json").
"""
from __future__ import annotations

import copy

import pytest
from core.news.overrides import (
    EDITABLE_FIELDS,
    Override,
    apply_override,
    apply_overrides,
    upsert_override,
)
from pydantic import ValidationError

from core.storage import (
    load_effective_events,
    load_event_overrides,
    write_event_overrides,
    write_events,
)

ONE_SOURCE = [
    {
        "title": "Example source",
        "url": "https://example.com/story",
        "publisher": "Example Wire",
        "published": "2020-03-16",
    }
]


def _record(
    episode_id: str = "2020-03-16_shock",
    *,
    status: str = "needs_review",
    sources: list[dict] | None = None,
    headline: str = "Original headline",
    summary: str = "Original summary.",
    category: str = "other",
    region: str = "Global",
    scheduled: bool = True,
    drivers: list[str] | None = None,
    confidence: float = 0.4,
    conflicting_sources: bool = False,
    reviewed: bool = False,
    rejected: bool = False,
) -> dict:
    return {
        "episode_id": episode_id,
        "status": status,
        "headline": headline,
        "summary": summary,
        "category": category,
        "region": region,
        "scheduled": scheduled,
        "drivers": drivers or [],
        "sources": ONE_SOURCE if sources is None else sources,
        "confidence": confidence,
        "conflicting_sources": conflicting_sources,
        "reviewed": reviewed,
        "rejected": rejected,
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


def _override(episode_id: str, action: str, **kwargs) -> Override:
    return Override(
        episode_id=episode_id, action=action, reviewed_at="2026-10-09T12:00:00Z", **kwargs
    )


# --- Override model validation -------------------------------------------------------


def test_override_rejects_fields_key_outside_editable_fields():
    with pytest.raises(ValidationError):
        Override(
            episode_id="x",
            action="edit",
            fields={"sources": []},
            reviewed_at="2026-10-09T12:00:00Z",
        )


def test_override_rejects_confidence_field_key():
    with pytest.raises(ValidationError):
        Override(
            episode_id="x",
            action="edit",
            fields={"confidence": 0.9},
            reviewed_at="2026-10-09T12:00:00Z",
        )


def test_override_rejects_nonempty_fields_for_accept():
    with pytest.raises(ValidationError):
        Override(
            episode_id="x",
            action="accept",
            fields={"headline": "New"},
            reviewed_at="2026-10-09T12:00:00Z",
        )


def test_override_rejects_nonempty_fields_for_reject():
    with pytest.raises(ValidationError):
        Override(
            episode_id="x",
            action="reject",
            fields={"headline": "New"},
            reviewed_at="2026-10-09T12:00:00Z",
        )


def test_editable_fields_constant():
    assert EDITABLE_FIELDS == ("headline", "summary", "category", "region", "drivers", "status")


# --- apply_override: accept -----------------------------------------------------------


def test_accept_needs_review_with_source_becomes_explained():
    record = _record(status="needs_review", confidence=0.9)
    override = _override(record["episode_id"], "accept")

    result = apply_override(record, override)

    assert result["status"] == "explained"
    assert result["reviewed"] is True
    assert result["override_action"] == "accept"
    assert result["reviewed_at"] == "2026-10-09T12:00:00Z"


def test_accept_needs_review_with_zero_sources_stays_unexplained():
    record = _record(status="needs_review", sources=[])
    override = _override(record["episode_id"], "accept")

    result = apply_override(record, override)

    assert result["status"] == "unexplained"
    assert result["reviewed"] is True


def test_accept_explained_record_status_unchanged():
    record = _record(status="explained", confidence=0.9)
    override = _override(record["episode_id"], "accept")

    result = apply_override(record, override)

    assert result["status"] == "explained"
    assert result["reviewed"] is True


def test_accept_unexplained_record_status_unchanged():
    record = _record(status="unexplained", sources=[])
    override = _override(record["episode_id"], "accept")

    result = apply_override(record, override)

    assert result["status"] == "unexplained"
    assert result["reviewed"] is True


# --- apply_override: edit ---------------------------------------------------------------


def test_edit_overlays_only_given_fields_and_keeps_sources():
    record = _record(status="explained", confidence=0.9, headline="Old", category="other")
    override = _override(
        record["episode_id"], "edit", fields={"headline": "New", "category": "geopolitics"}
    )

    result = apply_override(record, override)

    assert result["headline"] == "New"
    assert result["category"] == "geopolitics"
    assert result["sources"] == ONE_SOURCE
    assert result["summary"] == record["summary"]


def test_edit_status_explained_with_zero_sources_forces_unexplained():
    record = _record(status="needs_review", sources=[])
    override = _override(record["episode_id"], "edit", fields={"status": "explained"})

    result = apply_override(record, override)

    assert result["status"] == "unexplained"


def test_edit_invalid_category_raises_validation_error():
    record = _record(status="explained", confidence=0.9)
    override = _override(record["episode_id"], "edit", fields={"category": "bogus"})

    with pytest.raises(ValidationError):
        apply_override(record, override)


# --- apply_override: reject -------------------------------------------------------------


def test_reject_sets_unexplained_rejected_and_keeps_headline():
    record = _record(status="explained", confidence=0.9, headline="Original headline")
    override = _override(record["episode_id"], "reject", note="wrong story")

    result = apply_override(record, override)

    assert result["status"] == "unexplained"
    assert result["rejected"] is True
    assert result["reviewed"] is True
    assert result["headline"] == "Original headline"
    assert result["review_note"] == "wrong story"


# --- apply_overrides: purity -------------------------------------------------------------


def test_apply_overrides_does_not_mutate_inputs():
    records = [_record("ep-1", status="needs_review", confidence=0.9), _record("ep-2", status="explained", confidence=0.9)]
    overrides = [_override("ep-1", "accept")]
    before_records = copy.deepcopy(records)
    before_overrides = [o.model_copy(deep=True) for o in overrides]

    apply_overrides(records, overrides)

    assert records == before_records
    assert overrides == before_overrides


def test_apply_overrides_ignores_override_with_no_matching_record():
    records = [_record("ep-1", status="explained", confidence=0.9)]
    overrides = [_override("no-such-episode", "accept")]

    result = apply_overrides(records, overrides)

    assert len(result) == 1
    assert result[0]["episode_id"] == "ep-1"
    assert "override_action" not in result[0]


def test_apply_overrides_passes_through_records_without_override_unchanged():
    records = [_record("ep-1", status="explained", confidence=0.9)]

    result = apply_overrides(records, [])

    assert result == records


# --- upsert_override ---------------------------------------------------------------------


def test_upsert_override_replaces_existing_and_sorts():
    first = _override("b-episode", "accept")
    second = _override("a-episode", "accept")
    replacement = _override("b-episode", "reject", note="changed my mind")

    result = upsert_override([first, second], replacement)

    assert [o.episode_id for o in result] == ["a-episode", "b-episode"]
    b = next(o for o in result if o.episode_id == "b-episode")
    assert b.action == "reject"
    assert b.note == "changed my mind"


# --- storage: load_event_overrides / load_effective_events --------------------------------


def test_load_event_overrides_missing_path_returns_empty_list(tmp_path):
    assert load_event_overrides(tmp_path / "missing_overrides.json") == []


def test_load_effective_events_with_missing_overrides_file_returns_events_unchanged(tmp_path):
    events_path = tmp_path / "events.json"
    overrides_path = tmp_path / "event_overrides.json"
    records = [_record("ep-1", status="explained", confidence=0.9)]
    write_events(records, events_path)

    effective = load_effective_events(events_path, overrides_path)

    assert effective == records


def test_load_effective_events_merges_overrides_at_read_time(tmp_path):
    events_path = tmp_path / "events.json"
    overrides_path = tmp_path / "event_overrides.json"
    records = [_record("ep-1", status="needs_review", confidence=0.9)]
    write_events(records, events_path)
    write_event_overrides([_override("ep-1", "accept")], overrides_path)

    effective = load_effective_events(events_path, overrides_path)
    before = events_path.read_bytes()

    assert effective[0]["status"] == "explained"
    assert events_path.read_bytes() == before
