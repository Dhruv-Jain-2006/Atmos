"""Research contracts.

The research engine is out of scope for this slice, but its contract is defined
now so the generated OpenAPI document — and therefore the frontend's TypeScript
client — is complete and stable. The routes exist and return 501.

Two properties are fixed here and will not change when the engine lands:

* Research is asynchronous. ``POST /api/research`` returns a job, never a result.
* Every finding carries an ``epistemic_status`` and its supporting evidence.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from internetweather.enums import EpistemicStatus, ResearchStatus
from internetweather.schemas.common import Schema
from internetweather.schemas.event import EvidenceLink


class ResearchRequest(Schema):
    technology_slug: str | None = None
    event_id: int | None = None
    question: str | None = Field(
        default=None,
        max_length=500,
        description="Optional focus, e.g. 'Why is MCP accelerating?'",
    )


class ResearchJob(Schema):
    research_id: str
    status: ResearchStatus
    technology_slug: str | None = None
    question: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    progress_note: str | None = None


class Finding(Schema):
    """One claim, with its epistemic standing attached.

    ``epistemic_status`` is required, not optional. That is the mechanism by
    which speculation cannot be presented as fact.
    """

    statement: str
    epistemic_status: EpistemicStatus
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceLink] = Field(default_factory=list)
    counter_evidence: list[EvidenceLink] = Field(default_factory=list)


class ResearchResult(ResearchJob):
    executive_finding: Finding | None = None
    supporting_findings: list[Finding] = Field(default_factory=list)
    unknowns: list[str] = Field(
        default_factory=list, description="What the evidence could not settle."
    )
    watch_next: list[str] = Field(default_factory=list)


class ChatRequest(Schema):
    message: str = Field(min_length=1, max_length=2000)


class ChatReply(Schema):
    """A Copilot answer. Grounded in Internet Weather data or it does not ship."""

    reply: str
    epistemic_status: EpistemicStatus
    evidence: list[EvidenceLink] = Field(default_factory=list)
    #: Structured queries the Copilot ran, so an answer is auditable.
    data_used: list[str] = Field(default_factory=list)
