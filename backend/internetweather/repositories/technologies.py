"""Queries over the technology universe."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from internetweather.models import (
    Repository,
    Technology,
    TechnologyRelationship,
    TechnologyRepository,
    TechnologySignalDaily,
)


def get_by_slug(session: Session, slug: str) -> Technology | None:
    return session.scalar(select(Technology).where(Technology.slug == slug))


def count_active(session: Session) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(Technology).where(Technology.is_active.is_(True))
        )
        or 0
    )


def count_tracked_repositories(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Repository)) or 0


def latest_signal(
    session: Session, technology_id: int
) -> TechnologySignalDaily | None:
    return session.scalar(
        select(TechnologySignalDaily)
        .where(TechnologySignalDaily.technology_id == technology_id)
        .order_by(TechnologySignalDaily.day.desc())
        .limit(1)
    )


def sensors(session: Session, technology_id: int) -> list[tuple[Repository, TechnologyRepository]]:
    """Repositories observed for a technology, strongest signal weight first."""
    stmt = (
        select(Repository, TechnologyRepository)
        .join(TechnologyRepository, TechnologyRepository.repository_id == Repository.id)
        .where(TechnologyRepository.technology_id == technology_id)
        .order_by(TechnologyRepository.weight.desc(), Repository.stars.desc())
    )
    return list(session.execute(stmt).all())


def relationships(
    session: Session, technology_id: int, day: date | None, *, limit: int = 24
) -> list[tuple[Technology, TechnologyRelationship, TechnologySignalDaily | None]]:
    """Outgoing edges, with each neighbour's current weather where known.

    The signal join is an outer join on purpose: a neighbour with no computed
    signal yet must still appear as a relationship rather than vanish.
    """
    stmt = (
        select(Technology, TechnologyRelationship, TechnologySignalDaily)
        .join(
            TechnologyRelationship,
            TechnologyRelationship.target_technology_id == Technology.id,
        )
        .outerjoin(
            TechnologySignalDaily,
            (TechnologySignalDaily.technology_id == Technology.id)
            & (TechnologySignalDaily.day == day),
        )
        .where(TechnologyRelationship.source_technology_id == technology_id)
        .order_by(TechnologyRelationship.strength.desc(), Technology.name.asc())
        .limit(limit)
    )
    return list(session.execute(stmt).all())
