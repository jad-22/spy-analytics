"""Override model and pure, read-time merge of human review decisions (REV-01, REV-02,
D-05). overrides win at read time; nothing here writes events.json -- the only write
path for overrides is core.storage.write_event_overrides, called from
scripts/review_events.py.

Must NOT import anthropic, requests, httpx, urllib, socket, core.data, jobs, scripts or
streamlit (D-02) -- enforced by tests/test_app_purity.py's AST guard.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core.news.schema import EventExplanation

EDITABLE_FIELDS: tuple[str, ...] = (
    "headline", "summary", "category", "region", "drivers", "status",
)

_EXPLANATION_FIELDS: frozenset[str] = frozenset(EventExplanation.model_fields)


class Override(BaseModel):
    """One human review decision for one episode. `fields` is only populated for
    action="edit" and its keys are restricted to EDITABLE_FIELDS -- a human can never
    touch sources, confidence or provenance fields through this model."""

    episode_id: str
    action: Literal["accept", "edit", "reject"]
    fields: dict[str, Any] = Field(default_factory=dict)
    reviewed_at: str
    note: str = ""

    @model_validator(mode="after")
    def _validate_fields(self) -> Override:
        extra = set(self.fields) - set(EDITABLE_FIELDS)
        if extra:
            raise ValueError(
                f"fields key(s) outside EDITABLE_FIELDS {EDITABLE_FIELDS}: {sorted(extra)}"
            )
        if self.action != "edit" and self.fields:
            raise ValueError(f"fields must be empty for action={self.action!r}")
        return self


def apply_override(record: Mapping[str, Any], override: Override) -> dict[str, Any]:
    """Return a new effective record dict with `override` applied to `record`. Never
    mutates `record`. The status/reviewed rules are enforced by re-validating the
    EventExplanation-field subset through the schema's own after-validator
    (apply_status_rules), so "explained" can never result without a cited source, even
    for a human accept or edit (NEWS-03/NEWS-04).
    """
    result = copy.deepcopy(dict(record))
    candidate = {k: v for k, v in result.items() if k in _EXPLANATION_FIELDS}

    if override.action == "accept":
        if candidate.get("status") == "needs_review":
            candidate["status"] = "explained"
    elif override.action == "edit":
        candidate.update(override.fields)
    elif override.action == "reject":
        candidate["status"] = "unexplained"
        candidate["rejected"] = True

    candidate["reviewed"] = True

    validated = EventExplanation.model_validate(candidate)
    result.update(validated.model_dump(mode="json"))
    result["override_action"] = override.action
    result["reviewed_at"] = override.reviewed_at
    result["review_note"] = override.note
    return result


def apply_overrides(
    records: list[Mapping[str, Any]], overrides: list[Override]
) -> list[dict[str, Any]]:
    """Apply `overrides` to `records` at read time. Pure: never mutates `records` or
    `overrides`. Overrides whose episode_id has no matching record are ignored; records
    without a matching override pass through as an unmodified copy.
    """
    overrides_by_id = {o.episode_id: o for o in overrides}
    result: list[dict[str, Any]] = []
    for record in records:
        override = overrides_by_id.get(record.get("episode_id"))
        if override is None:
            result.append(copy.deepcopy(dict(record)))
        else:
            result.append(apply_override(record, override))
    return result


def upsert_override(overrides: list[Override], new: Override) -> list[Override]:
    """Replace any existing override for `new.episode_id`, keeping the list sorted by
    episode_id. Does not mutate `overrides`."""
    remaining = [o for o in overrides if o.episode_id != new.episode_id]
    remaining.append(new)
    remaining.sort(key=lambda o: o.episode_id)
    return remaining
