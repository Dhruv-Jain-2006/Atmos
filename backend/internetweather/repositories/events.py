"""Queries over detected ecosystem events."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from internetweather.enums import EventType, Subdomain
from internetweather.models import EcosystemEvent, Repository, Technology

EventRow = tuple[EcosystemEvent, Technology | None, Repository | None]


def _base() -> Select[EventRow]:
    # Outer joins: an event can be about a repository we have not yet attributed
    # to a technology, and dropping it would hide a real observation.
    return (
        select(EcosystemEvent, Technology, Repository)
        .outerjoin(Technology, Technology.id == EcosystemEvent.technology_id)
        .outerjoin(Repository, Repository.id == EcosystemEvent.repository_id)
    )


def recent(
    session: Session,
    *,
    since: date | None = None,
    subdomain: Subdomain | None = None,
    technology_slug: str | None = None,
    event_types: list[EventType] | None = None,
    limit: int = 25,
    offset: int = 0,
) -> list[EventRow]:
    stmt = _base()
    if since is not None:
        stmt = stmt.where(EcosystemEvent.occurred_on >= since)
    if subdomain is not None:
        stmt = stmt.where(Technology.subdomain == subdomain)
    if technology_slug is not None:
        stmt = stmt.where(Technology.slug == technology_slug)
    if event_types:
        stmt = stmt.where(EcosystemEvent.event_type.in_(event_types))
    stmt = (
        stmt.order_by(
            EcosystemEvent.occurred_on.desc(),
            EcosystemEvent.magnitude.desc(),
            EcosystemEvent.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).all())


def count_recent(
    session: Session,
    *,
    since: date | None = None,
    subdomain: Subdomain | None = None,
    technology_slug: str | None = None,
    event_types: list[EventType] | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(EcosystemEvent)
        .outerjoin(Technology, Technology.id == EcosystemEvent.technology_id)
    )
    if since is not None:
        stmt = stmt.where(EcosystemEvent.occurred_on >= since)
    if subdomain is not None:
        stmt = stmt.where(Technology.subdomain == subdomain)
    if technology_slug is not None:
        stmt = stmt.where(Technology.slug == technology_slug)
    if event_types:
        stmt = stmt.where(EcosystemEvent.event_type.in_(event_types))
    return session.scalar(stmt) or 0


def get(session: Session, event_id: int) -> EventRow | None:
    return session.execute(_base().where(EcosystemEvent.id == event_id)).first()


def for_technology(
    session: Session, technology_id: int, *, limit: int = 25
) -> list[EcosystemEvent]:
    return list(
        session.scalars(
            select(EcosystemEvent)
            .where(EcosystemEvent.technology_id == technology_id)
            .order_by(EcosystemEvent.occurred_on.desc(), EcosystemEvent.magnitude.desc())
            .limit(limit)
        )
    )


def default_window(as_of: date, *, days: int = 14) -> date:
    return as_of - timedelta(days=days)
