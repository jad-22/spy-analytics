"""Pydantic schema and code-enforced status rules for news enrichment.

Must NOT import anthropic, requests, httpx, urllib, socket, core.data, jobs, scripts or
streamlit (D-02) -- enforced by tests/test_app_purity.py's AST guard. Implements NEWS-02
(validated explanation schema), NEWS-03 (sources must come from the provider's own
cross-validated search results, never trusted model prose -- enforced by the caller, not
this module), NEWS-04 (confidence/conflict/zero-source status downgrades, code-enforced,
never upgraded) and NEWS-05 (EnrichmentRecord provenance shape: provider, model,
prompt_version, web_search_tool, enriched_at, usage, cost_usd, raw_response).
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.config import SETTINGS

Category = Literal[
    "monetary_policy", "inflation_data", "growth_data", "geopolitics",
    "pandemic_health", "banking_credit", "earnings_tech",
    "fiscal_trade_policy", "energy_commodities", "other",
]
Region = Literal["US", "Europe", "China", "Global", "Other"]
Status = Literal["explained", "unexplained", "needs_review"]


class Episode(BaseModel):
    """A pending-or-done episode row from data/episodes.parquet, narrowed to the fields
    the enrichment prompt and job need. Frozen -- never mutated after construction."""

    model_config = ConfigDict(frozen=True)

    episode_id: str
    start_date: date
    end_date: date
    anchor_date: date
    direction: Literal["up", "down"]
    trigger: str
    move_pct: float
    search_from: date
    search_to: date
    status: str
    scheduled_releases: list[str]
    unscheduled_releases: list[str]
    catalyst: str

    @classmethod
    def from_row(cls, row: Mapping) -> Episode:
        """Build an Episode from a data/episodes.parquet row. Converts pandas Timestamps
        to date and numpy arrays (pyarrow's round-trip type for list[str] columns) to
        plain list[str]."""

        def _to_date(value: object) -> date:
            return pd.Timestamp(value).date()

        def _to_str_list(value: object) -> list[str]:
            if value is None:
                return []
            if isinstance(value, np.ndarray):
                return [str(v) for v in value.tolist()]
            return [str(v) for v in list(value)]

        return cls(
            episode_id=str(row["episode_id"]),
            start_date=_to_date(row["start_date"]),
            end_date=_to_date(row["end_date"]),
            anchor_date=_to_date(row["anchor_date"]),
            direction=row["direction"],
            trigger=str(row["trigger"]),
            move_pct=float(row["move_pct"]),
            search_from=_to_date(row["search_from"]),
            search_to=_to_date(row["search_to"]),
            status=str(row["status"]),
            scheduled_releases=_to_str_list(row["scheduled_releases"]),
            unscheduled_releases=_to_str_list(row["unscheduled_releases"]),
            catalyst=str(row["catalyst"]),
        )


class Source(BaseModel):
    """A single cited source. NEWS-03: only ever constructed by a provider after
    cross-validating the URL and date against the search tool's own raw results --
    never from the model's self-reported prose alone."""

    title: str
    url: str
    publisher: str
    published: date

    @field_validator("url")
    @classmethod
    def _validate_scheme(cls, v: str) -> str:
        if not v.startswith(("https://", "http://")):
            raise ValueError(f"url must start with http:// or https://: {v!r}")
        return v


class DroppedSource(BaseModel):
    """A claimed source the provider discarded during cross-validation, and why."""

    url: str
    reason: Literal[
        "not_in_search_results", "no_page_age", "unparseable_page_age", "outside_window",
    ]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    web_search_requests: int = 0


def apply_status_rules(
    status: Status,
    n_sources: int,
    confidence: float,
    conflicting: bool,
    reviewed: bool,
    threshold: float,
) -> Status:
    """Code-enforced status downgrade (NEWS-03/NEWS-04). Never returns a status "better"
    than its input:

    1. Zero sources always forces "unexplained" -- nothing can be explained without a
       cited, cross-validated source, even a human review can't override this.
    2. An input of "unexplained" always stays "unexplained".
    3. A human review decision (reviewed=True) wins and is returned unchanged, except
       where rule 1 already applies.
    4. Otherwise, a confidence below threshold, a conflicting-sources flag, or an input
       already "needs_review" all force "needs_review" (the "already needs_review" leg is
       what makes rule 4 one-directional -- it can never climb back up to "explained").
    5. Otherwise "explained".
    """
    if n_sources == 0:
        return "unexplained"
    if status == "unexplained":
        return "unexplained"
    if reviewed:
        return status
    if confidence < threshold or conflicting or status == "needs_review":
        return "needs_review"
    return "explained"


class EventExplanation(BaseModel):
    """NEWS-02's validated explanation schema. status is never trusted as given --
    the after-validator always recomputes it via apply_status_rules (NEWS-03/NEWS-04)."""

    episode_id: str
    status: Status
    headline: str
    summary: str
    category: Category
    region: Region
    scheduled: bool
    drivers: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    conflicting_sources: bool = False
    reviewed: bool = False
    rejected: bool = False

    @model_validator(mode="after")
    def _enforce_status_rules(self) -> EventExplanation:
        if len(self.headline) > SETTINGS.news_headline_max_chars:
            raise ValueError(
                f"headline exceeds {SETTINGS.news_headline_max_chars} chars: {self.headline!r}"
            )
        self.status = apply_status_rules(
            self.status,
            n_sources=len(self.sources),
            confidence=self.confidence,
            conflicting=self.conflicting_sources,
            reviewed=self.reviewed,
            threshold=SETTINGS.news_confidence_threshold,
        )
        return self


class Enrichment(BaseModel):
    """What a NewsProvider.explain() call returns: the validated explanation plus the
    provenance NEWS-05 requires to build an EnrichmentRecord. Widened beyond
    EventExplanation alone (docs/SPEC.md's sketch) so usage/model/raw_response travel
    with the explanation -- see core/news/base.py's docstring."""

    explanation: EventExplanation
    provider: str
    model: str
    web_search_tool: str | None
    usage: Usage
    stop_reasons: list[str] = Field(default_factory=list)
    dropped_sources: list[DroppedSource] = Field(default_factory=list)
    raw_response: list[dict] | None = None


class EnrichmentRecord(EventExplanation):
    """One persisted data/events.json record: the explanation plus NEWS-05's full
    provenance (provider, model, prompt_version, web_search_tool, enriched_at, usage,
    cost_usd, stop_reasons, dropped_sources, raw_response)."""

    provider: str
    model: str
    prompt_version: str
    web_search_tool: str | None
    enriched_at: str
    search_from: date
    search_to: date
    usage: Usage
    cost_usd: float
    stop_reasons: list[str]
    dropped_sources: list[DroppedSource]
    raw_response: list[dict] | None


def to_record(
    enrichment: Enrichment,
    episode: Episode,
    prompt_version: str,
    enriched_at: str,
    cost_usd: float,
) -> EnrichmentRecord:
    """Build the EnrichmentRecord written to data/events.json for one episode."""
    explanation = enrichment.explanation
    return EnrichmentRecord(
        **explanation.model_dump(),
        provider=enrichment.provider,
        model=enrichment.model,
        prompt_version=prompt_version,
        web_search_tool=enrichment.web_search_tool,
        enriched_at=enriched_at,
        search_from=episode.search_from,
        search_to=episode.search_to,
        usage=enrichment.usage,
        cost_usd=cost_usd,
        stop_reasons=enrichment.stop_reasons,
        dropped_sources=enrichment.dropped_sources,
        raw_response=enrichment.raw_response,
    )


def is_current_record(record: Mapping, prompt_version: str) -> bool:
    """True iff `record` is a real (non-null-provider) record matching the current
    prompt version -- NEWS-06: null-provider placeholders never block real enrichment,
    and a stale prompt version is treated as pending again."""
    return record.get("provider") != "null" and record.get("prompt_version") == prompt_version
