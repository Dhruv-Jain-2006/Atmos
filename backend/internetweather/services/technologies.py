"""Technology detail, history, and relationships — the Research page's data."""

from __future__ import annotations

from sqlalchemy.orm import Session

from internetweather.analysis.explanation import describe, epistemic_status
from internetweather.enums import EpistemicStatus, RecordSource
from internetweather.repositories import signals as signal_repo
from internetweather.repositories import technologies as tech_repo
from internetweather.schemas.technology import (
    HistoryPoint,
    RelatedTechnology,
    RepositorySensor,
    TechnologyDetail,
    TechnologyHistory,
    TechnologyRelationships,
)
from internetweather.services import cards, state

GITHUB_BASE = "https://github.com"

#: Curated edges are asserted by us; computed edges are inferred from data.
_EDGE_STATUS = {
    RecordSource.CURATED: EpistemicStatus.OBSERVATION,
    RecordSource.DISCOVERED: EpistemicStatus.OBSERVATION,
    RecordSource.INFERRED: EpistemicStatus.INFERENCE,
}


def detail(session: Session | None, slug: str) -> TechnologyDetail | None:
    """Returns None only when the technology does not exist.

    A technology with no signals yet is not a 404 — it is a real, tracked
    technology we have not observed long enough to describe.
    """
    if session is None:
        return None

    technology = tech_repo.get_by_slug(session, slug)
    if technology is None:
        return None

    signal = tech_repo.latest_signal(session, technology.id)
    sensors = [
        RepositorySensor(
            full_name=repo.full_name,
            relation=link.relation,
            weight=link.weight,
            stars=repo.stars,
            forks=repo.forks,
            primary_language=repo.primary_language,
            is_archived=repo.is_archived,
            pushed_at=repo.pushed_at_github,
            url=f"{GITHUB_BASE}/{repo.full_name}",
        )
        for repo, link in tech_repo.sensors(session, technology.id)
    ]

    return TechnologyDetail(
        slug=technology.slug,
        name=technology.name,
        subdomain=technology.subdomain,
        summary=technology.summary,
        aliases=list(technology.aliases or []),
        headline=technology.headline,
        first_seen_at=technology.first_seen_at,
        weather_state=signal.weather_state if signal else None,
        signals=cards.snapshot(signal) if signal else None,
        explanation=describe(cards.preview_input(signal)) if signal else None,
        epistemic_status=(
            epistemic_status(signal.confidence) if signal else EpistemicStatus.UNKNOWN
        ),
        repositories=sensors,
        freshness=state.freshness(session, signal.day if signal else None),
    )


def history(
    session: Session | None, slug: str, *, days: int = 90
) -> TechnologyHistory | None:
    if session is None:
        return None

    technology = tech_repo.get_by_slug(session, slug)
    if technology is None:
        return None

    rows = signal_repo.history(session, technology.id, days=days)
    return TechnologyHistory(
        slug=slug,
        points=[
            HistoryPoint(
                day=row.day,
                weather_state=row.weather_state,
                momentum=row.momentum,
                confidence=row.confidence,
                stars_total=row.stars_total,
                stars_delta_1d=row.stars_delta_1d,
                star_velocity_7d=row.star_velocity_7d,
                activity_score=row.activity_score,
            )
            for row in rows
        ],
        freshness=state.freshness(session, rows[-1].day if rows else None),
    )


def relationships(session: Session | None, slug: str) -> TechnologyRelationships | None:
    if session is None:
        return None

    technology = tech_repo.get_by_slug(session, slug)
    if technology is None:
        return None

    day = signal_repo.latest_signal_day(session)
    related = [
        RelatedTechnology(
            slug=neighbour.slug,
            name=neighbour.name,
            subdomain=neighbour.subdomain,
            weather_state=signal.weather_state if signal else None,
            relation_type=edge.relation_type,
            strength=edge.strength,
            epistemic_status=_EDGE_STATUS.get(edge.basis, EpistemicStatus.INFERENCE),
        )
        for neighbour, edge, signal in tech_repo.relationships(session, technology.id, day)
    ]
    return TechnologyRelationships(
        slug=slug, related=related, freshness=state.freshness(session, day)
    )
