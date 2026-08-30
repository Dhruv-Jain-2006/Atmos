"""Assembling the Trends page and the weather overview."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from internetweather.enums import Subdomain, WeatherState
from internetweather.repositories import events as event_repo
from internetweather.repositories import signals as signal_repo
from internetweather.schemas.common import DataFreshness
from internetweather.schemas.technology import TechnologyCard
from internetweather.schemas.trends import SubdomainClimate, Trends, WeatherOverview
from internetweather.services import cards, state
from internetweather.services.events import to_summary
from internetweather.universe import load_universe

#: Cards per band on the Trends page. Bounded so the payload stays small and the
#: radar stays legible — this is not an infinite list.
BAND_SIZE = 8
EVENT_LIMIT = 12


def _subdomain_labels() -> dict[Subdomain, str]:
    """Human labels come from the curated universe, not from enum name mangling."""
    try:
        universe = load_universe()
    except (FileNotFoundError, ValueError):
        return {key: key.value.replace("_", " ").title() for key in Subdomain}
    return {key: meta.name for key, meta in universe.subdomains.items()}


def _dominant(counts: dict[WeatherState, int]) -> WeatherState:
    if not counts:
        return WeatherState.STABLE
    return max(counts.items(), key=lambda item: (item[1], item[0].value))[0]


def overview(session: Session | None) -> WeatherOverview:
    if session is None:
        return WeatherOverview(freshness=state.degraded())

    day = signal_repo.latest_signal_day(session)
    if day is None:
        return WeatherOverview(freshness=state.freshness(session, None))

    labels = _subdomain_labels()
    climate = []
    for subdomain, count, mean in signal_repo.climate_by_subdomain(session, day):
        counts = signal_repo.state_counts(session, day, subdomain=subdomain)
        climate.append(
            SubdomainClimate(
                subdomain=subdomain,
                label=labels.get(subdomain, subdomain.value),
                technology_count=count,
                mean_momentum=round(mean, 4),
                dominant_state=_dominant(counts),
                state_counts=counts,
            )
        )

    counts = signal_repo.state_counts(session, day)
    return WeatherOverview(
        as_of=day,
        technology_count=sum(counts.values()),
        state_counts=counts,
        mean_momentum=round(signal_repo.mean_momentum(session, day), 4),
        subdomains=climate,
        freshness=state.freshness(session, day),
    )


def _band(
    session: Session,
    day: date,
    *,
    order: str,
    states: Sequence[WeatherState] | None = None,
    subdomain: Subdomain | None = None,
) -> list[TechnologyCard]:
    rows = signal_repo.signals_for_day(
        session, day, order=order, states=states, subdomain=subdomain, limit=BAND_SIZE
    )
    sparks = signal_repo.spark_series(session, [tech.id for tech, _ in rows], day)
    return [cards.to_card(tech, signal, sparks.get(tech.id)) for tech, signal in rows]


def trends(session: Session | None, *, subdomain: Subdomain | None = None) -> Trends:
    """The whole Trends page.

    Bounded work: four ranked bands of ``BAND_SIZE`` plus one event query. Adding
    a technology to the universe does not make this slower.
    """
    if session is None:
        return Trends(overview=overview(None), freshness=state.degraded())

    day = signal_repo.latest_signal_day(session)
    if day is None:
        empty = state.freshness(session, None)
        return Trends(overview=overview(session), freshness=empty)

    event_rows = event_repo.recent(
        session,
        since=event_repo.default_window(day),
        subdomain=subdomain,
        limit=EVENT_LIMIT,
    )

    return Trends(
        as_of=day,
        overview=overview(session),
        heating=_band(session, day, order="heating", subdomain=subdomain),
        cooling=_band(session, day, order="cooling", subdomain=subdomain),
        emerging=_band(
            session, day, order="heating", states=[WeatherState.EMERGING], subdomain=subdomain
        ),
        anomalies=_band(session, day, order="anomaly", subdomain=subdomain),
        events=[to_summary(*row) for row in event_rows],
        freshness=state.freshness(session, day),
    )


def technology_page(
    session: Session | None,
    *,
    subdomain: Subdomain | None = None,
    states: Sequence[WeatherState] | None = None,
    order: str = "rank",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[TechnologyCard], int, DataFreshness]:
    """Paginated technology list. Returns (items, total, freshness)."""
    if session is None:
        return [], 0, state.degraded()

    day = signal_repo.latest_signal_day(session)
    if day is None:
        return [], 0, state.freshness(session, None)

    rows = signal_repo.signals_for_day(
        session,
        day,
        subdomain=subdomain,
        states=states,
        order=order,
        limit=limit,
        offset=offset,
    )
    sparks = signal_repo.spark_series(session, [tech.id for tech, _ in rows], day)
    total = signal_repo.count_signals_for_day(
        session, day, subdomain=subdomain, states=states
    )
    items = [cards.to_card(tech, signal, sparks.get(tech.id)) for tech, signal in rows]
    return items, total, state.freshness(session, day)
