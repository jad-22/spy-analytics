"""Unit tests for core/news/sources.py: page_age parsing, search-result extraction,
source cross-validation against the tool's own results, publisher attribution, and
raw-response sanitization. All hand-built fixtures, no network (NEWS-03/NEWS-05).
"""
from __future__ import annotations

from datetime import date

from core.news.prompt import ClaimedSource
from core.news.sources import (
    extract_search_results,
    filter_sources_in_window,
    parse_page_age,
    publisher_from_url,
    sanitize_raw_response,
)


def test_parse_page_age_month_day_year():
    assert parse_page_age("April 30, 2025") == date(2025, 4, 30)


def test_parse_page_age_iso():
    assert parse_page_age("2008-10-09") == date(2008, 10, 9)


def test_parse_page_age_month_day_year_time():
    assert parse_page_age("Oct 9, 2008 4:15 PM") == date(2008, 10, 9)


def test_parse_page_age_none():
    assert parse_page_age(None) is None


def test_parse_page_age_empty_string():
    assert parse_page_age("") is None


def test_parse_page_age_relative_3_days_ago():
    assert parse_page_age("3 days ago") is None


def test_parse_page_age_yesterday():
    assert parse_page_age("yesterday") is None


def test_parse_page_age_garbage():
    assert parse_page_age("garbage") is None


def test_extract_search_results_maps_url_to_title_and_page_age():
    blocks = [
        {"type": "text", "text": "ignored"},
        {
            "type": "web_search_tool_result",
            "tool_use_id": "t1",
            "content": [
                {
                    "type": "web_search_result",
                    "url": "https://a.example.com/1",
                    "title": "A Story",
                    "page_age": "April 30, 2025",
                },
            ],
        },
        {
            "type": "web_search_tool_result",
            "tool_use_id": "t2",
            "content": [
                {
                    "type": "web_search_result",
                    "url": "https://b.example.com/2",
                    "title": "B Story",
                    "page_age": None,
                },
            ],
        },
    ]
    results = extract_search_results(blocks)
    assert results == {
        "https://a.example.com/1": {"title": "A Story", "page_age": "April 30, 2025"},
        "https://b.example.com/2": {"title": "B Story", "page_age": None},
    }


def test_extract_search_results_ignores_error_shaped_content():
    blocks = [
        {
            "type": "web_search_tool_result",
            "tool_use_id": "t1",
            "content": {"type": "web_search_tool_result_error", "error_code": "x"},
        },
    ]
    assert extract_search_results(blocks) == {}


def test_extract_search_results_ignores_non_result_blocks():
    blocks = [
        {"type": "server_tool_use", "id": "x", "name": "web_search", "input": {"query": "q"}},
        {"type": "text", "text": "hello", "citations": []},
    ]
    assert extract_search_results(blocks) == {}


def test_publisher_from_url_strips_www_and_path():
    assert publisher_from_url("https://www.reuters.com/markets/x") == "reuters.com"


def test_publisher_from_url_no_www():
    assert publisher_from_url("https://apnews.com/article/y") == "apnews.com"


def test_filter_sources_in_window_keeps_in_window_source():
    claimed = [ClaimedSource(url="https://a.example.com/1", title="model's own title")]
    results = {
        "https://a.example.com/1": {"title": "Tool Title", "page_age": "2020-03-15"},
    }
    kept, dropped = filter_sources_in_window(
        claimed, results, date(2020, 3, 13), date(2020, 3, 17)
    )
    assert dropped == []
    assert len(kept) == 1
    assert kept[0].title == "Tool Title"
    assert kept[0].publisher == "a.example.com"
    assert kept[0].published == date(2020, 3, 15)
    assert kept[0].url == "https://a.example.com/1"


def test_filter_sources_in_window_bounds_are_inclusive():
    claimed = [
        ClaimedSource(url="https://a.example.com/1"),
        ClaimedSource(url="https://a.example.com/2"),
    ]
    results = {
        "https://a.example.com/1": {"title": "T1", "page_age": "2020-03-13"},
        "https://a.example.com/2": {"title": "T2", "page_age": "2020-03-17"},
    }
    kept, dropped = filter_sources_in_window(
        claimed, results, date(2020, 3, 13), date(2020, 3, 17)
    )
    assert dropped == []
    assert {s.url for s in kept} == {"https://a.example.com/1", "https://a.example.com/2"}


def test_filter_sources_in_window_drops_not_in_search_results():
    claimed = [ClaimedSource(url="https://never-searched.example.com/1")]
    kept, dropped = filter_sources_in_window(claimed, {}, date(2020, 3, 13), date(2020, 3, 17))
    assert kept == []
    assert len(dropped) == 1
    assert dropped[0].url == "https://never-searched.example.com/1"
    assert dropped[0].reason == "not_in_search_results"


def test_filter_sources_in_window_drops_no_page_age():
    claimed = [ClaimedSource(url="https://a.example.com/1")]
    results = {"https://a.example.com/1": {"title": "T", "page_age": None}}
    kept, dropped = filter_sources_in_window(
        claimed, results, date(2020, 3, 13), date(2020, 3, 17)
    )
    assert kept == []
    assert dropped[0].reason == "no_page_age"


def test_filter_sources_in_window_drops_unparseable_page_age():
    claimed = [ClaimedSource(url="https://a.example.com/1")]
    results = {"https://a.example.com/1": {"title": "T", "page_age": "3 days ago"}}
    kept, dropped = filter_sources_in_window(
        claimed, results, date(2020, 3, 13), date(2020, 3, 17)
    )
    assert kept == []
    assert dropped[0].reason == "unparseable_page_age"


def test_filter_sources_in_window_drops_outside_window():
    claimed = [ClaimedSource(url="https://a.example.com/1")]
    results = {"https://a.example.com/1": {"title": "T", "page_age": "2020-01-01"}}
    kept, dropped = filter_sources_in_window(
        claimed, results, date(2020, 3, 13), date(2020, 3, 17)
    )
    assert kept == []
    assert dropped[0].reason == "outside_window"


def test_filter_sources_in_window_duplicate_claimed_url_kept_once():
    claimed = [
        ClaimedSource(url="https://a.example.com/1"),
        ClaimedSource(url="https://a.example.com/1"),
    ]
    results = {"https://a.example.com/1": {"title": "T", "page_age": "2020-03-15"}}
    kept, _dropped = filter_sources_in_window(
        claimed, results, date(2020, 3, 13), date(2020, 3, 17)
    )
    assert len(kept) == 1


def test_sanitize_raw_response_strips_keys_at_any_depth():
    obj = {
        "content": [
            {
                "type": "web_search_tool_result",
                "content": [
                    {
                        "type": "web_search_result",
                        "url": "https://a.example.com",
                        "encrypted_content": "SECRET",
                    }
                ],
            },
            {
                "type": "text",
                "text": "hello",
                "citations": [
                    {
                        "type": "web_search_result_location",
                        "encrypted_index": "SECRET2",
                        "cited_text": "SECRET3",
                        "url": "https://a.example.com",
                    }
                ],
            },
        ],
    }
    sanitized = sanitize_raw_response(obj)
    dumped = str(sanitized)
    assert "SECRET" not in dumped
    assert "SECRET2" not in dumped
    assert "SECRET3" not in dumped
    assert sanitized["content"][1]["text"] == "hello"
    assert sanitized["content"][0]["content"][0]["url"] == "https://a.example.com"


def test_sanitize_raw_response_does_not_mutate_input():
    obj = {"encrypted_content": "SECRET", "keep": "me"}
    before = dict(obj)
    sanitize_raw_response(obj)
    assert obj == before
