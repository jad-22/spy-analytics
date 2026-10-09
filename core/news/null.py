"""Deterministic NewsProvider for tests and offline dev. No network (NEWS-01)."""
from __future__ import annotations

from core.news.schema import Enrichment, Episode, EventExplanation, Usage


class NullProvider:
    """Always returns an "unexplained" stub. `scheduled` still comes from Phase 2's
    catalyst tag (never a model claim), since that part of the record is deterministic,
    free, and already-computed -- there is no reason a stub provider should get it
    wrong."""

    name = "null"
    model = "null"

    def explain(self, episode: Episode) -> Enrichment:
        return Enrichment(
            explanation=EventExplanation(
                episode_id=episode.episode_id,
                status="unexplained",
                headline="No enrichment (null provider)",
                summary="Null provider stub; no web search was performed.",
                category="other",
                region="Global",
                scheduled=episode.catalyst == "scheduled",
                confidence=0.0,
            ),
            provider=self.name,
            model=self.model,
            web_search_tool=None,
            usage=Usage(),
            raw_response=None,
        )
