"""Weather, Trends, technologies and events — the entire read surface."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from internetweather.db import get_session
from internetweather.enums import EventType, Subdomain, WeatherState
from internetweather.schemas.common import Page
from internetweather.schemas.event import EventDetail, EventList
from internetweather.schemas.technology import (
    TechnologyDetail,
    TechnologyHistory,
    TechnologyList,
    TechnologyRelationships,
)
from internetweather.schemas.trends import Trends, WeatherOverview
from internetweather.services import events as event_service
from internetweather.services import technologies as tech_service
from internetweather.services import trends as trend_service

router = APIRouter(prefix="/api", tags=["weather"])

SlugPath = Annotated[
    str,
    Path(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80, examples=["mcp"]),
]

SlugQuery = Annotated[
    str | None,
    Query(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80, examples=["mcp"]),
]

#: Endpoints that address a single record cannot answer "does this exist?" with
#: no database. A 404 there would assert absence we never checked, so the lookup
#: routes fail loudly with 503 while the list routes still return an honest empty
#: page. Only single-record routes use this.
NO_DATABASE = "no database configured; the API is serving contracts only"


def _require_session(session: Session | None) -> Session:
    if session is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=NO_DATABASE)
    return session


@router.get("/weather", response_model=WeatherOverview, summary="Global conditions")
def weather(session: Session | None = Depends(get_session)) -> WeatherOverview:
    return trend_service.overview(session)


@router.get("/trends", response_model=Trends, summary="The Trends page, in one call")
def trends(
    session: Session | None = Depends(get_session),
    subdomain: Subdomain | None = Query(default=None),
) -> Trends:
    """Bounded by design: four ranked bands plus recent events.

    A single request so the page paints at once — assembling one screen from four
    round trips is what makes an interface feel like a dashboard.
    """
    return trend_service.trends(session, subdomain=subdomain)


@router.get("/technologies", response_model=TechnologyList, summary="Technology universe")
def technologies(
    session: Session | None = Depends(get_session),
    subdomain: Subdomain | None = Query(default=None),
    state: Annotated[list[WeatherState] | None, Query()] = None,
    order: str = Query(default="rank", pattern="^(rank|heating|cooling|anomaly|stars|name)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TechnologyList:
    items, total, freshness = trend_service.technology_page(
        session,
        subdomain=subdomain,
        states=state,
        order=order,
        limit=limit,
        offset=offset,
    )
    return TechnologyList(
        items=items, page=Page(total=total, limit=limit, offset=offset), freshness=freshness
    )


@router.get(
    "/technologies/{slug}",
    response_model=TechnologyDetail,
    summary="Research page header",
)
def technology(
    slug: SlugPath, session: Session | None = Depends(get_session)
) -> TechnologyDetail:
    result = tech_service.detail(_require_session(session), slug)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"unknown technology: {slug}")
    return result


@router.get(
    "/technologies/{slug}/history",
    response_model=TechnologyHistory,
    summary="Signal history",
)
def technology_history(
    slug: SlugPath,
    session: Session | None = Depends(get_session),
    days: int = Query(default=90, ge=7, le=365),
) -> TechnologyHistory:
    result = tech_service.history(_require_session(session), slug, days=days)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"unknown technology: {slug}")
    return result


@router.get(
    "/technologies/{slug}/relationships",
    response_model=TechnologyRelationships,
    summary="Related technologies",
)
def technology_relationships(
    slug: SlugPath, session: Session | None = Depends(get_session)
) -> TechnologyRelationships:
    result = tech_service.relationships(_require_session(session), slug)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"unknown technology: {slug}")
    return result


@router.get("/events", response_model=EventList, summary="Detected ecosystem events")
def events(
    session: Session | None = Depends(get_session),
    subdomain: Subdomain | None = Query(default=None),
    # The Research page's timeline needs one technology's occurrences. Filtering
    # here beats shipping the global log and discarding most of it client-side.
    technology: SlugQuery = None,
    event_type: Annotated[list[EventType] | None, Query()] = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EventList:
    return event_service.listing(
        session,
        subdomain=subdomain,
        technology_slug=technology,
        event_types=event_type,
        limit=limit,
        offset=offset,
    )


@router.get("/events/{event_id}", response_model=EventDetail, summary="Event with evidence")
def event(
    event_id: Annotated[int, Path(ge=1)], session: Session | None = Depends(get_session)
) -> EventDetail:
    result = event_service.detail(_require_session(session), event_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"unknown event: {event_id}")
    return result
