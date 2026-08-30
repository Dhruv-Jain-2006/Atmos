"""Operational contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from internetweather.schemas.common import Schema


class DatabaseHealth(Schema):
    configured: bool
    reachable: bool
    error: str | None = None


class Health(Schema):
    """Liveness plus honest degradation.

    ``status`` is ``ok`` when data can be served and ``degraded`` when the API is
    up but has no database. Degraded is a real product state, not a failure: the
    contracts and vocabulary still resolve.
    """

    status: str = Field(description="ok | degraded")
    version: str
    environment: str
    database: DatabaseHealth
    checked_at: datetime


class IngestionSummary(Schema):
    """Last run per job. How you know whether the observatory is actually looking."""

    source: str
    job: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    api_calls: int = 0
    api_calls_saved: int = 0
    records_written: int = 0
    rate_limit_remaining: int | None = None
    error: str | None = None


class SystemStatus(Schema):
    health: Health
    ingestion: list[IngestionSummary] = Field(default_factory=list)
    tracked_technologies: int = 0
    tracked_repositories: int = 0
    observed_days: int = 0
