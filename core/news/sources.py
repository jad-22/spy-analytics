"""Source cross-validation and raw-response sanitization for news enrichment.

Must NOT import anthropic, requests, httpx, urllib, socket, core.data, jobs, scripts or
streamlit (D-02) -- enforced by tests/test_app_purity.py's AST guard. Implements
NEWS-03 (a claimed source only counts if its URL was actually returned by a web search
and its page_age falls inside the episode's search window -- the model's own self-
reported "published" date is never trusted, Pitfall 2) and NEWS-05's sanitizer (raw
response storage must never include encrypted content blocks or quoted article text --
the copyright rule).
"""
from __future__ import annotations

import re
from datetime import date

from dateutil import parser as date_parser

from core.news.prompt import ClaimedSource
from core.news.schema import DroppedSource, Source

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_STRIP_KEYS = frozenset({"encrypted_content", "encrypted_index", "cited_text"})


def parse_page_age(page_age: str | None) -> date | None:
    """Parse a web_search_tool_result's free-text page_age (e.g. "April 30, 2025") into
    a date, or None if it is missing or can't be confidently parsed. A string with no
    4-digit year (1900-2099) -- e.g. "3 days ago", "yesterday" -- is rejected before
    ever reaching dateutil's fuzzy parser, so a relative phrase is never silently
    resolved against "now" and mistaken for an absolute date."""
    if not page_age:
        return None
    if not _YEAR_RE.search(page_age):
        return None
    try:
        return date_parser.parse(page_age, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def extract_search_results(blocks: list[dict]) -> dict[str, dict]:
    """Map url -> {"title", "page_age"} for every web_search_result item inside every
    web_search_tool_result block in `blocks`. Non-matching block types and error-shaped
    tool-result content ({"type": "web_search_tool_result_error", ...}, where "content"
    is a dict rather than a list) are ignored. This is the sole source of truth for
    NEWS-03 -- callers must never read a claimed source's own "published" field."""
    results: dict[str, dict] = {}
    for block in blocks:
        if block.get("type") != "web_search_tool_result":
            continue
        content = block.get("content")
        if not isinstance(content, list):
            continue  # error-shaped result; nothing usable
        for item in content:
            if item.get("type") == "web_search_result" and "url" in item:
                results[item["url"]] = {
                    "title": item.get("title", ""),
                    "page_age": item.get("page_age"),
                }
    return results


def publisher_from_url(url: str) -> str:
    """Lowercase hostname without a leading "www." -- avoids importing urllib (forbidden
    in core/, D-02) for a one-line parse."""
    rest = url.split("://", 1)[-1]
    host = rest.split("/", 1)[0]
    host = host.rsplit("@", 1)[-1]  # strip userinfo if present
    host = host.split(":", 1)[0]  # strip port
    host = host.lower()
    return host.removeprefix("www.")


def filter_sources_in_window(
    claimed: list[ClaimedSource],
    results: dict[str, dict],
    search_from: date,
    search_to: date,
) -> tuple[list[Source], list[DroppedSource]]:
    """Cross-validate every claimed source against `results` (extract_search_results'
    output) and the episode's search window. A claimed URL is kept only if it was
    actually returned by a search AND its page_age parses to a date inside
    [search_from, search_to] (inclusive). The kept Source uses the tool result's own
    title (never the model's claimed title), publisher_from_url(url), and the parsed
    date -- never the model's prose. A duplicate claimed URL is processed once."""
    kept: list[Source] = []
    dropped: list[DroppedSource] = []
    seen: set[str] = set()

    for src in claimed:
        if src.url in seen:
            continue
        seen.add(src.url)

        result = results.get(src.url)
        if result is None:
            dropped.append(DroppedSource(url=src.url, reason="not_in_search_results"))
            continue

        page_age = result.get("page_age")
        if page_age is None:
            dropped.append(DroppedSource(url=src.url, reason="no_page_age"))
            continue

        published = parse_page_age(page_age)
        if published is None:
            dropped.append(DroppedSource(url=src.url, reason="unparseable_page_age"))
            continue

        if not (search_from <= published <= search_to):
            dropped.append(DroppedSource(url=src.url, reason="outside_window"))
            continue

        kept.append(
            Source(
                title=result.get("title", ""),
                url=src.url,
                publisher=publisher_from_url(src.url),
                published=published,
            )
        )

    return kept, dropped


def sanitize_raw_response(obj: object) -> object:
    """Recursively copy `obj`, dropping "encrypted_content", "encrypted_index" and
    "cited_text" keys at any depth (they hold encrypted page content or quoted article
    text -- NEWS-05, the copyright rule "no stored article text"). Never mutates the
    input."""
    if isinstance(obj, dict):
        return {k: sanitize_raw_response(v) for k, v in obj.items() if k not in _STRIP_KEYS}
    if isinstance(obj, list):
        return [sanitize_raw_response(v) for v in obj]
    return obj
