"""Unit tests for core/news/prompt.py: SYSTEM_PROMPT content, build_user_prompt's
per-episode context, the strict JSON schema for output_config, and the prompt
fingerprint used to detect an unversioned prompt edit. All hand-built fixtures, no
network.
"""
from __future__ import annotations

from datetime import date

from core.config import SETTINGS
from core.news.prompt import (
    PROMPT_FINGERPRINTS,
    SYSTEM_PROMPT,
    ModelAnswer,
    answer_json_schema,
    build_user_prompt,
    prompt_fingerprint,
)
from core.news.schema import Episode


def _episode(**overrides) -> Episode:
    fields = {
        "episode_id": "2020-03-16_shock",
        "start_date": date(2020, 3, 13),
        "end_date": date(2020, 3, 16),
        "anchor_date": date(2020, 3, 16),
        "direction": "down",
        "trigger": "shock",
        "move_pct": -0.08,
        "search_from": date(2020, 3, 13),
        "search_to": date(2020, 3, 17),
        "status": "closed",
        "scheduled_releases": ["FOMC 2020-03-15"],
        "unscheduled_releases": [],
        "catalyst": "scheduled",
    }
    fields.update(overrides)
    return Episode(**fields)


def test_system_prompt_mentions_unexplained_and_ignore():
    assert "unexplained" in SYSTEM_PROMPT
    assert "ignore" in SYSTEM_PROMPT


def test_system_prompt_interpolates_headline_limit():
    assert str(SETTINGS.news_headline_max_chars) in SYSTEM_PROMPT


def test_build_user_prompt_scheduled_episode_contains_dates_and_release():
    episode = _episode()
    prompt = build_user_prompt(episode)
    assert "2020-03-13" in prompt  # search_from
    assert "2020-03-17" in prompt  # search_to
    assert "down" in prompt
    assert "-8.00%" in prompt
    assert "shock" in prompt
    assert "FOMC 2020-03-15" in prompt


def test_build_user_prompt_surprise_episode_states_no_scheduled_release():
    episode = _episode(scheduled_releases=[], catalyst="surprise")
    prompt = build_user_prompt(episode)
    assert "no scheduled" in prompt.lower()


def test_build_user_prompt_positive_move_is_signed():
    episode = _episode(direction="up", move_pct=0.08)
    prompt = build_user_prompt(episode)
    assert "+8.00%" in prompt


def test_model_answer_has_no_scheduled_field():
    assert "scheduled" not in ModelAnswer.model_fields


def test_answer_json_schema_root_additional_properties_false():
    schema = answer_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(ModelAnswer.model_fields.keys())


def test_answer_json_schema_claimed_source_additional_properties_false():
    schema = answer_json_schema()
    defs = schema.get("$defs", {})
    claimed_source = defs.get("ClaimedSource")
    assert claimed_source is not None
    assert claimed_source["additionalProperties"] is False
    assert set(claimed_source["required"]) == {"url", "title"}


def test_prompt_fingerprint_matches_pinned_version():
    assert prompt_fingerprint() == PROMPT_FINGERPRINTS[SETTINGS.news_prompt_version]
