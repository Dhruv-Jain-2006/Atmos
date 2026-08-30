"""Weather overview and Trends page contracts.

``/api/trends`` returns the whole Trends page in one response. That is
deliberate: the page has to answer "what is changing in AI engineering right
now?" immediately, and four parallel requests to assemble one screen is how a
dashboard ends up feeling like a dashboard.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from internetweather.enums import Subdomain, WeatherState
from internetweather.schemas.common import DataFreshness, Schema
from internetweather.schemas.event import EventSummary
from internetweather.schemas.technology import TechnologyCard


class SubdomainClimate(Schema):
    """Aggregate weather for one subdomain — the radar's regional readout."""

    subdomain: Subdomain
    label: str
    technology_count: int
    mean_momentum: float
    dominant_state: WeatherState
    state_counts: dict[WeatherState, int] = Field(default_factory=dict)


class WeatherOverview(Schema):
    """Global conditions. The one-glance answer."""

    as_of: date | None = None
    technology_count: int = 0
    state_counts: dict[WeatherState, int] = Field(default_factory=dict)
    #: Mean momentum across the tracked universe. The ecosystem's own pressure.
    mean_momentum: float = 0.0
    subdomains: list[SubdomainClimate] = Field(default_factory=list)
    freshness: DataFreshness


class Trends(Schema):
    """Everything the Trends page renders."""

    as_of: date | None = None
    overview: WeatherOverview

    #: Accelerating fastest relative to their own baseline.
    heating: list[TechnologyCard] = Field(default_factory=list)
    #: Decaying relative to their own baseline.
    cooling: list[TechnologyCard] = Field(default_factory=list)
    #: Young, small-base, accelerating.
    emerging: list[TechnologyCard] = Field(default_factory=list)
    #: Statistically unusual versus their own history, in either direction.
    anomalies: list[TechnologyCard] = Field(default_factory=list)

    #: Discrete occurrences worth explaining.
    events: list[EventSummary] = Field(default_factory=list)

    freshness: DataFreshness
