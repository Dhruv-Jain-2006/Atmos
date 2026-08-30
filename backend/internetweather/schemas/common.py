"""Shared contract pieces."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from internetweather.enums import EpistemicStatus, Subdomain, WeatherState


class Schema(BaseModel):
    """Base for every response model.

    ``from_attributes`` lets services hand back ORM rows or lightweight row
    tuples without an intermediate dict.
    """

    model_config = ConfigDict(from_attributes=True)


class WeatherStateInfo(Schema):
    """Presentation metadata for one weather state.

    Served so the frontend renders the semantic vocabulary from the API instead
    of hardcoding glyphs that could drift from the classifier.
    """

    state: WeatherState
    glyph: str
    label: str
    meaning: str


class SubdomainInfo(Schema):
    key: Subdomain
    label: str


class Vocabulary(Schema):
    """Everything the UI needs to label data it did not compute."""

    weather_states: list[WeatherStateInfo]
    subdomains: list[SubdomainInfo]
    epistemic_statuses: list[EpistemicStatus]


class DataFreshness(Schema):
    """How current, and how trustworthy, the numbers behind a response are.

    Present on every data response. A platform that claims to observe the
    internet has to be explicit about when it last actually looked.
    """

    as_of: str | None = Field(
        default=None, description="ISO date of the latest computed signal day."
    )
    observed_days: int = Field(
        default=0, description="Distinct days of observation backing these signals."
    )
    #: False before the first ingestion run, or when the database is unreachable.
    has_data: bool = False
    degraded_reason: str | None = Field(
        default=None,
        description="Why data is missing, when it is. Null when has_data is true.",
    )


class Page(Schema):
    total: int
    limit: int
    offset: int
