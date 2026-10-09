"""ClaudeSearchProvider: the repo's only `import anthropic` (D-03). Used only by
jobs/enrich_events.py -- never by app/ or core/, which stay network-free (D-02). The
Anthropic API key itself is never read, stored or printed by this module;
jobs/enrich_events.py owns key handling and passes an already-constructed client in
(D-04/OPS-03). Every SDK exception is re-raised as a ValueError naming only the
episode_id and the exception's type name -- never str(exc), which could embed request
details (NEWS-05 Pitfall #5, mirrors core/data.py::fetch_fred_release_dates).
"""
from __future__ import annotations

import anthropic
import pydantic
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import SETTINGS
from core.news.prompt import SYSTEM_PROMPT, ModelAnswer, answer_json_schema, build_user_prompt
from core.news.schema import Enrichment, Episode, EventExplanation, Usage
from core.news.sources import (
    extract_search_results,
    filter_sources_in_window,
    sanitize_raw_response,
)

_RETRYABLE_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)


class ClaudeSearchProvider:
    """NewsProvider backed by the real Claude API: web search (server tool) composed
    with structured output (output_config.format) in one request, pause_turn
    continuation across up to SETTINGS.news_max_continuations re-calls, source
    cross-validation against the tool's own results (NEWS-03) and leak-safe error
    handling (NEWS-05 Pitfall #5)."""

    name = "claude"

    def __init__(
        self,
        client: object,
        model: str,
        settings=SETTINGS,
        retry_wait_max: float = SETTINGS.fetch_wait_max_s,
    ) -> None:
        self.client = client
        self.model = model
        self.settings = settings
        self.retry_wait_max = retry_wait_max

    def _retryer(self) -> Retrying:
        wait_max = self.retry_wait_max
        wait_min = 0.0 if wait_max <= 0 else self.settings.fetch_wait_min_s
        return Retrying(
            stop=stop_after_attempt(self.settings.fetch_attempts),
            wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
            retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
            reraise=True,
        )

    def explain(self, episode: Episode) -> Enrichment:
        messages: list[dict] = [{"role": "user", "content": build_user_prompt(episode)}]
        raw: list[dict] = []
        all_blocks: list[dict] = []
        stop_reasons: list[str] = []
        total_input = 0
        total_output = 0
        total_searches = 0
        continuations = 0
        content: list[dict] = []

        while True:
            max_uses = self.settings.news_max_searches_per_request - total_searches
            if continuations > 0 and max_uses <= 0:
                raise ValueError(
                    f"Claude request failed for episode_id={episode.episode_id}: "
                    "search budget exhausted before end_turn"
                )

            tools = [
                {
                    "type": self.settings.web_search_tool_type,
                    "name": "web_search",
                    "max_uses": max_uses,
                }
            ]

            try:
                response = self._retryer()(
                    self.client.messages.create,
                    model=self.model,
                    max_tokens=self.settings.news_max_output_tokens,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=tools,
                    output_config={
                        "format": {"type": "json_schema", "schema": answer_json_schema()}
                    },
                )
            except Exception as exc:  # noqa: BLE001 - never leak the underlying message
                raise ValueError(
                    f"Claude request failed for episode_id={episode.episode_id}: "
                    f"{type(exc).__name__}"
                ) from None

            dump = response.model_dump()
            raw.append(sanitize_raw_response(dump))

            usage = dump.get("usage") or {}
            total_input += usage.get("input_tokens", 0) or 0
            total_output += usage.get("output_tokens", 0) or 0
            server_tool_use = usage.get("server_tool_use") or {}
            total_searches += server_tool_use.get("web_search_requests", 0) or 0

            content = dump.get("content", [])
            all_blocks.extend(content)
            stop_reason = dump.get("stop_reason")
            stop_reasons.append(stop_reason)

            if stop_reason == "end_turn":
                break
            if stop_reason == "pause_turn" and continuations < self.settings.news_max_continuations:
                messages.append({"role": "assistant", "content": content})
                continuations += 1
                continue
            raise ValueError(
                f"Claude request failed for episode_id={episode.episode_id}: "
                f"stop_reason={stop_reason!r}"
            )

        text_blocks = [b for b in content if b.get("type") == "text"]
        if not text_blocks:
            raise ValueError(
                f"Claude request failed for episode_id={episode.episode_id}: "
                "no text block in final response"
            )
        try:
            answer = ModelAnswer.model_validate_json(text_blocks[-1]["text"])
        except pydantic.ValidationError as exc:
            raise ValueError(
                f"Claude request failed for episode_id={episode.episode_id}: "
                f"{len(exc.errors())} validation error(s)"
            ) from None

        results = extract_search_results(all_blocks)
        kept, dropped = filter_sources_in_window(
            answer.sources, results, episode.search_from, episode.search_to
        )

        explanation = EventExplanation(
            episode_id=episode.episode_id,
            status=answer.status,
            headline=answer.headline,
            summary=answer.summary,
            category=answer.category,
            region=answer.region,
            scheduled=episode.catalyst == "scheduled",
            drivers=answer.drivers,
            sources=kept,
            confidence=answer.confidence,
            conflicting_sources=answer.conflicting_sources,
        )

        return Enrichment(
            explanation=explanation,
            provider=self.name,
            model=self.model,
            web_search_tool=self.settings.web_search_tool_type,
            usage=Usage(
                input_tokens=total_input,
                output_tokens=total_output,
                web_search_requests=total_searches,
            ),
            stop_reasons=stop_reasons,
            dropped_sources=dropped,
            raw_response=raw,
        )
