"""Offline integrity checks on committed enrichment data: data/events.json,
data/enrichment_spend.json, data/event_overrides.json (NEWS-02..08, REV-02).

Runs with no network -- every assertion reads files Jason committed after a real
backfill run (03-06). Skipped entirely until data/events.json exists, so this module
collects cleanly before then, exactly like tests/test_macro_calendar_data.py.
"""
from __future__ import annotations

import pytest

from core.config import SETTINGS
from core.news.cost import ledger_total_usd
from core.news.prompt import PROMPT_FINGERPRINTS
from core.news.schema import EnrichmentRecord
from core.storage import load_episodes, load_events, load_spend_ledger

pytestmark = pytest.mark.skipif(
    not SETTINGS.events_path.exists(), reason="data/events.json not written yet"
)

_LEAK_SUBSTRINGS = ("sk-ant-", "x-api-key", "encrypted_content", "cited_text")


@pytest.fixture(scope="module")
def records() -> list[dict]:
    return load_events(SETTINGS.events_path)


@pytest.fixture(scope="module")
def episodes_by_id() -> dict:
    df = load_episodes(SETTINGS.episodes_path)
    return {row["episode_id"]: row for _, row in df.iterrows()}


def test_every_record_validates(records: list[dict]) -> None:
    for record in records:
        EnrichmentRecord.model_validate(record)


def test_no_record_has_provider_null(records: list[dict]) -> None:
    for record in records:
        assert record["provider"] != "null", record["episode_id"]


def test_prompt_version_and_model_are_known(records: list[dict]) -> None:
    known_models = {name for name, _, _ in SETTINGS.news_model_prices_usd_per_mtok}
    for record in records:
        assert record["prompt_version"] in PROMPT_FINGERPRINTS, record["episode_id"]
        assert record["model"] in known_models, record["episode_id"]


def test_search_window_matches_episode(records: list[dict], episodes_by_id: dict) -> None:
    for record in records:
        episode = episodes_by_id[record["episode_id"]]
        assert record["search_from"] == str(episode["search_from"].date()), record["episode_id"]
        assert record["search_to"] == str(episode["search_to"].date()), record["episode_id"]


def test_sources_published_inside_window(records: list[dict]) -> None:
    for record in records:
        search_from = record["search_from"]
        search_to = record["search_to"]
        for source in record.get("sources", []):
            assert search_from <= source["published"] <= search_to, record["episode_id"]


def test_scheduled_matches_episode_catalyst(records: list[dict], episodes_by_id: dict) -> None:
    for record in records:
        episode = episodes_by_id[record["episode_id"]]
        assert record["scheduled"] == (episode["catalyst"] == "scheduled"), record["episode_id"]


def test_explained_status_has_at_least_one_source(records: list[dict]) -> None:
    for record in records:
        if record["status"] == "explained":
            assert len(record.get("sources", [])) >= 1, record["episode_id"]


def test_no_leaked_secret_or_copyright_pattern_in_committed_files() -> None:
    paths = [
        SETTINGS.events_path,
        SETTINGS.news_spend_ledger_path,
        SETTINGS.event_overrides_path,
    ]
    for path in paths:
        if not path.exists():
            continue
        lowered = path.read_text().lower()
        for pattern in _LEAK_SUBSTRINGS:
            assert pattern not in lowered, f"{path} contains {pattern!r}"


def test_ledger_total_within_budget() -> None:
    ledger = load_spend_ledger(SETTINGS.news_spend_ledger_path)
    assert ledger_total_usd(ledger) <= SETTINGS.news_budget_usd
