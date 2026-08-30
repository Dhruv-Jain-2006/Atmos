"""Ecosystem event contracts."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from internetweather.enums import EpistemicStatus, EventType
from internetweather.schemas.common import DataFreshness, Page, Schema


class EvidenceLink(Schema):
    """A traceable source for a claim.

    Present on every event so "show me the evidence" is answerable without a
    round trip through the research engine.
    """

    label: str
    url: str | None = None
    detail: str | None = Field(
        default=None, description="The measured value that triggered this, when applicable."
    )


class EventSummary(Schema):
    id: int
    event_type: EventType
    occurred_on: date
    title: str
    summary: str | None = None
    magnitude: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    epistemic_status: EpistemicStatus
    technology_slug: str | None = None
    technology_name: str | None = None
    repository_full_name: str | None = None


class EventDetail(EventSummary):
    occurred_at: datetime | None = None
    detected_at: datetime | None = None
    evidence: list[EvidenceLink] = Field(default_factory=list)


class EventList(Schema):
    items: list[EventSummary]
    page: Page
    freshness: DataFreshness
