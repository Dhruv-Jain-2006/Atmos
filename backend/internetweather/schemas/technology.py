"""Technology contracts: list, hover preview, detail, history, relationships."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from internetweather.enums import (
    EpistemicStatus,
    RelationshipType,
    RepoRelation,
    Subdomain,
    WeatherState,
)
from internetweather.schemas.common import DataFreshness, Page, Schema


class SignalSnapshot(Schema):
    """The measured numbers behind a weather state.

    Every field here is an OBSERVATION or a deterministic transform of one. The
    UI may show these without an epistemic caveat.
    """

    momentum: float = Field(description="Normalised -1..1 composite. Positive = accelerating.")
    confidence: float = Field(ge=0, le=1)
    stars_total: int
    stars_delta_7d: int | None = None
    stars_delta_28d: int | None = None
    star_velocity_7d: float | None = Field(
        default=None, description="Weighted stars/day over the trailing 7 days."
    )
    star_acceleration: float | None = Field(
        default=None, description="Change in velocity — what 'heating up' actually means."
    )
    activity_score: float | None = None
    commit_velocity_7d: float | None = None
    release_count_28d: int | None = None
    contributor_count_28d: int | None = None
    anomaly_z: float | None = Field(
        default=None, description="Standard deviations from this technology's own baseline."
    )
    repo_count: int = 0
    active_repo_count: int = 0
    sample_days: int = Field(
        default=0, description="Observed days backing this row. Low values mean low confidence."
    )


class TechnologyCard(Schema):
    """One technology as it appears on Trends, including its hover preview.

    Deliberately self-sufficient: the hover intelligence preview must not fire a
    second request, so the sparkline and explanation ship with the card.
    """

    slug: str
    name: str
    subdomain: Subdomain
    summary: str | None = None
    headline: bool = False

    weather_state: WeatherState
    signals: SignalSnapshot

    #: Trailing daily momentum values, oldest first. Drives the inline sparkline.
    spark: list[float] = Field(default_factory=list)

    #: One sentence describing what changed, generated deterministically from
    #: the signal deltas — no LLM in the read path.
    explanation: str | None = None
    epistemic_status: EpistemicStatus = EpistemicStatus.OBSERVATION

    rank_overall: int | None = None
    rank_subdomain: int | None = None
    as_of: date | None = None


class TechnologyList(Schema):
    items: list[TechnologyCard]
    page: Page
    freshness: DataFreshness


class RepositorySensor(Schema):
    """A repository observed on behalf of a technology."""

    full_name: str
    relation: RepoRelation
    weight: float
    stars: int
    forks: int
    primary_language: str | None = None
    is_archived: bool = False
    pushed_at: datetime | None = None
    url: str


class RelatedTechnology(Schema):
    slug: str
    name: str
    subdomain: Subdomain
    weather_state: WeatherState | None = None
    relation_type: RelationshipType
    strength: float = Field(ge=0, le=1)
    #: Computed edges are INFERENCE; curated ones are OBSERVATION.
    epistemic_status: EpistemicStatus


class TechnologyDetail(Schema):
    """The Research page header: what we know, and what it rests on."""

    slug: str
    name: str
    subdomain: Subdomain
    summary: str | None = None
    aliases: list[str] = Field(default_factory=list)
    headline: bool = False
    first_seen_at: datetime | None = None

    weather_state: WeatherState | None = None
    signals: SignalSnapshot | None = None
    explanation: str | None = None
    epistemic_status: EpistemicStatus = EpistemicStatus.OBSERVATION

    repositories: list[RepositorySensor] = Field(default_factory=list)
    freshness: DataFreshness


class HistoryPoint(Schema):
    day: date
    weather_state: WeatherState
    momentum: float
    confidence: float
    stars_total: int
    stars_delta_1d: int | None = None
    star_velocity_7d: float | None = None
    activity_score: float | None = None


class TechnologyHistory(Schema):
    slug: str
    points: list[HistoryPoint]
    freshness: DataFreshness


class TechnologyRelationships(Schema):
    slug: str
    related: list[RelatedTechnology]
    freshness: DataFreshness
