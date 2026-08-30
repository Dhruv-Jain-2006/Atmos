"""Queries over derived signals.

Every function here is bounded and indexed. There are no per-item lookups: the
Trends page costs two queries regardless of how many technologies it renders.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from internetweather.enums import Subdomain, WeatherState
from internetweather.models import (
    RepositoryMetricDaily,
    Technology,
    TechnologySignalDaily,
)

SignalRow = tuple[Technology, TechnologySignalDaily]

#: Trailing window for the hover-preview sparkline.
SPARK_DAYS = 28


def latest_signal_day(session: Session) -> date | None:
    """The most recent day the detection worker has computed."""
    return session.scalar(select(func.max(TechnologySignalDaily.day)))


def observed_day_count(session: Session) -> int:
    """Distinct days of ingested observation. Drives reported confidence."""
    return (
        session.scalar(select(func.count(func.distinct(RepositoryMetricDaily.day)))) or 0
    )


def _base(day: date, subdomain: Subdomain | None) -> Select[SignalRow]:
    stmt = (
        select(Technology, TechnologySignalDaily)
        .join(
            TechnologySignalDaily,
            TechnologySignalDaily.technology_id == Technology.id,
        )
        .where(TechnologySignalDaily.day == day)
        .where(Technology.is_active.is_(True))
    )
    if subdomain is not None:
        stmt = stmt.where(Technology.subdomain == subdomain)
    return stmt


def signals_for_day(
    session: Session,
    day: date,
    *,
    subdomain: Subdomain | None = None,
    states: Sequence[WeatherState] | None = None,
    order: str = "rank",
    limit: int = 50,
    offset: int = 0,
) -> list[SignalRow]:
    """One page of technology cards for a given day.

    ``order`` is an allow-list, not a passthrough — an ORDER BY assembled from
    raw client input is an injection surface.
    """
    stmt = _base(day, subdomain)
    if states:
        stmt = stmt.where(TechnologySignalDaily.weather_state.in_(list(states)))

    orderings = {
        "rank": TechnologySignalDaily.rank_overall.asc().nullslast(),
        "heating": TechnologySignalDaily.momentum.desc(),
        "cooling": TechnologySignalDaily.momentum.asc(),
        "anomaly": func.abs(TechnologySignalDaily.anomaly_z).desc().nullslast(),
        "stars": TechnologySignalDaily.stars_total.desc(),
        "name": Technology.name.asc(),
    }
    if order not in orderings:
        raise ValueError(f"unsupported ordering: {order}")

    stmt = stmt.order_by(orderings[order], Technology.slug.asc()).limit(limit).offset(offset)
    return list(session.execute(stmt).all())


def count_signals_for_day(
    session: Session,
    day: date,
    *,
    subdomain: Subdomain | None = None,
    states: Sequence[WeatherState] | None = None,
) -> int:
    stmt = select(func.count()).select_from(
        _base(day, subdomain).subquery()
        if states is None
        else _base(day, subdomain)
        .where(TechnologySignalDaily.weather_state.in_(list(states)))
        .subquery()
    )
    return session.scalar(stmt) or 0


def spark_series(
    session: Session,
    technology_ids: Sequence[int],
    day: date,
    *,
    days: int = SPARK_DAYS,
) -> dict[int, list[float]]:
    """Trailing momentum per technology, oldest first.

    A single ``IN`` query rather than one per card — the composite primary key
    ``(technology_id, day)`` serves it directly.
    """
    if not technology_ids:
        return {}

    start = day - timedelta(days=days - 1)
    rows = session.execute(
        select(
            TechnologySignalDaily.technology_id,
            TechnologySignalDaily.momentum,
        )
        .where(TechnologySignalDaily.technology_id.in_(list(technology_ids)))
        .where(TechnologySignalDaily.day.between(start, day))
        .order_by(TechnologySignalDaily.technology_id, TechnologySignalDaily.day)
    ).all()

    series: dict[int, list[float]] = {tech_id: [] for tech_id in technology_ids}
    for tech_id, momentum in rows:
        series[tech_id].append(float(momentum))
    return series


def history(
    session: Session, technology_id: int, *, days: int = 90
) -> list[TechnologySignalDaily]:
    """Chronological signal history for the Research page timeline."""
    stmt = (
        select(TechnologySignalDaily)
        .where(TechnologySignalDaily.technology_id == technology_id)
        .order_by(TechnologySignalDaily.day.desc())
        .limit(days)
    )
    rows = list(session.scalars(stmt))
    rows.reverse()
    return rows


def climate_by_subdomain(session: Session, day: date) -> list[tuple[Subdomain, int, float]]:
    """(subdomain, technology count, mean momentum) — aggregated in the database."""
    stmt = (
        select(
            Technology.subdomain,
            func.count().label("n"),
            func.avg(TechnologySignalDaily.momentum).label("mean_momentum"),
        )
        .join(
            TechnologySignalDaily,
            TechnologySignalDaily.technology_id == Technology.id,
        )
        .where(TechnologySignalDaily.day == day)
        .where(Technology.is_active.is_(True))
        .group_by(Technology.subdomain)
        .order_by(Technology.subdomain)
    )
    return [
        (row.subdomain, int(row.n), float(row.mean_momentum or 0.0))
        for row in session.execute(stmt)
    ]


def state_counts(
    session: Session, day: date, *, subdomain: Subdomain | None = None
) -> dict[WeatherState, int]:
    stmt = (
        select(TechnologySignalDaily.weather_state, func.count().label("n"))
        .join(Technology, Technology.id == TechnologySignalDaily.technology_id)
        .where(TechnologySignalDaily.day == day)
        .where(Technology.is_active.is_(True))
        .group_by(TechnologySignalDaily.weather_state)
    )
    if subdomain is not None:
        stmt = stmt.where(Technology.subdomain == subdomain)
    return {row.weather_state: int(row.n) for row in session.execute(stmt)}


def mean_momentum(session: Session, day: date) -> float:
    value = session.scalar(
        select(func.avg(TechnologySignalDaily.momentum))
        .join(Technology, Technology.id == TechnologySignalDaily.technology_id)
        .where(TechnologySignalDaily.day == day)
        .where(Technology.is_active.is_(True))
    )
    return float(value or 0.0)
