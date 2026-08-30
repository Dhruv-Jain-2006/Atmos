"""Health and system status."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from internetweather import __version__
from internetweather.config import get_settings
from internetweather.db import check_db, get_session
from internetweather.repositories import ops as ops_repo
from internetweather.repositories import signals as signal_repo
from internetweather.repositories import technologies as tech_repo
from internetweather.schemas.system import (
    DatabaseHealth,
    Health,
    IngestionSummary,
    SystemStatus,
)

router = APIRouter(tags=["system"])


def _health(connectivity: tuple[bool, str | None]) -> Health:
    settings = get_settings()
    reachable, error = connectivity
    return Health(
        status="ok" if reachable else "degraded",
        version=__version__,
        environment=settings.environment,
        database=DatabaseHealth(
            configured=settings.database_configured, reachable=reachable, error=error
        ),
        checked_at=datetime.now(UTC),
    )


@router.get("/health", response_model=Health, summary="Liveness and degradation")
def health(connectivity: tuple[bool, str | None] = Depends(check_db)) -> Health:
    """Always 200.

    A degraded API is still a working API: contracts and vocabulary resolve
    without a database. Returning 500 here would make an ordinary cold start
    look like an outage.
    """
    return _health(connectivity)


@router.get(
    "/api/status",
    response_model=SystemStatus,
    summary="Is the observatory actually observing?",
)
def status(
    session: Session | None = Depends(get_session),
    connectivity: tuple[bool, str | None] = Depends(check_db),
) -> SystemStatus:
    report = SystemStatus(health=_health(connectivity))
    if session is None:
        return report

    report.tracked_technologies = tech_repo.count_active(session)
    report.tracked_repositories = tech_repo.count_tracked_repositories(session)
    report.observed_days = signal_repo.observed_day_count(session)
    report.ingestion = [
        IngestionSummary(
            source=run.source,
            job=run.job,
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            api_calls=run.api_calls,
            api_calls_saved=run.api_calls_saved,
            records_written=run.records_written,
            rate_limit_remaining=run.rate_limit_remaining,
            error=run.error,
        )
        for run in ops_repo.latest_runs(session)
    ]
    return report
