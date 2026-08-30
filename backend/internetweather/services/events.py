"""Event read orchestration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from internetweather.enums import EventType, Subdomain
from internetweather.models import EcosystemEvent, Repository, Technology
from internetweather.repositories import events as event_repo
from internetweather.repositories import signals as signal_repo
from internetweather.schemas.common import Page
from internetweather.schemas.event import (
    EventDetail,
    EventList,
    EventSummary,
    EvidenceLink,
)
from internetweather.services import state

GITHUB_BASE = "https://github.com"


def to_summary(
    event: EcosystemEvent,
    technology: Technology | None,
    repository: Repository | None,
) -> EventSummary:
    return EventSummary(
        id=event.id,
        event_type=event.event_type,
        occurred_on=event.occurred_on,
        title=event.title,
        summary=event.summary,
        magnitude=event.magnitude,
        confidence=event.confidence,
        epistemic_status=event.epistemic_status,
        technology_slug=technology.slug if technology else None,
        technology_name=technology.name if technology else None,
        repository_full_name=repository.full_name if repository else None,
    )


def _evidence_links(event: EcosystemEvent, repository: Repository | None) -> list[EvidenceLink]:
    """Flatten the stored evidence blob into typed links.

    ``evidence`` is written by the detection worker as
    ``{"sources": [{"label":..., "url":..., "detail":...}], "metrics": {...}}``.
    Unknown shapes are surfaced as plain details rather than dropped — silently
    losing provenance is worse than showing it awkwardly.
    """
    links: list[EvidenceLink] = []
    blob = event.evidence or {}

    for source in blob.get("sources", []) or []:
        if isinstance(source, dict):
            links.append(
                EvidenceLink(
                    label=str(source.get("label", "source")),
                    url=source.get("url"),
                    detail=source.get("detail"),
                )
            )

    for key, value in (blob.get("metrics") or {}).items():
        links.append(EvidenceLink(label=str(key), url=None, detail=str(value)))

    if repository is not None:
        links.append(
            EvidenceLink(
                label=repository.full_name,
                url=f"{GITHUB_BASE}/{repository.full_name}",
                detail="observed repository",
            )
        )
    return links


def listing(
    session: Session | None,
    *,
    subdomain: Subdomain | None = None,
    technology_slug: str | None = None,
    event_types: list[EventType] | None = None,
    limit: int = 25,
    offset: int = 0,
) -> EventList:
    if session is None:
        return EventList(
            items=[], page=Page(total=0, limit=limit, offset=offset), freshness=state.degraded()
        )

    day = signal_repo.latest_signal_day(session)
    rows = event_repo.recent(
        session,
        subdomain=subdomain,
        technology_slug=technology_slug,
        event_types=event_types,
        limit=limit,
        offset=offset,
    )
    total = event_repo.count_recent(
        session,
        subdomain=subdomain,
        technology_slug=technology_slug,
        event_types=event_types,
    )
    return EventList(
        items=[to_summary(*row) for row in rows],
        page=Page(total=total, limit=limit, offset=offset),
        freshness=state.freshness(session, day),
    )


def detail(session: Session | None, event_id: int) -> EventDetail | None:
    if session is None:
        return None
    row = event_repo.get(session, event_id)
    if row is None:
        return None

    event, technology, repository = row
    summary = to_summary(event, technology, repository)
    return EventDetail(
        **summary.model_dump(),
        occurred_at=event.occurred_at,
        detected_at=event.detected_at,
        evidence=_evidence_links(event, repository),
    )
