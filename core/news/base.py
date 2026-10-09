"""NewsProvider interface (NEWS-01). No network import here -- any provider that needs
one (the real Claude provider, D-03) lives in jobs/, not core/news/.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.news.schema import Enrichment, Episode


@runtime_checkable
class NewsProvider(Protocol):
    """Anything that can plug into jobs/enrich_events.py.

    docs/SPEC.md sketches `explain(episode) -> EventExplanation`; the return type here
    is widened to `Enrichment` so NEWS-05's provenance (provider, model, usage,
    raw_response, dropped_sources, stop_reasons) travels with the explanation instead of
    being bolted on by the caller. `name` is a short, stable, filesystem/dict-key-safe
    identifier (matches core/signals.py::Strategy's convention) -- it is also the
    PROVIDERS registry key in jobs/enrich_events.py.

    Future providers (e.g. a GDELT or finance-news-API source, V2-03) implement this
    exact Protocol without jobs/enrich_events.py changing at all.
    """

    name: str

    def explain(self, episode: Episode) -> Enrichment: ...
