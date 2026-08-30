"""Ingestion bookkeeping.

Quota-aware ingestion needs memory. This table is how a worker knows what the
previous run consumed, where it stopped, and whether it should run at all.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from internetweather.enums import IngestionStatus
from internetweather.models._columns import enum_column
from internetweather.models.base import Base


class IngestionRun(Base):
    """One execution of one worker job."""

    __tablename__ = "ingestion_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    #: Data source, e.g. "github". Future sources reuse this table unchanged.
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Job within the source, e.g. "sync_metrics", "discover", "backfill_stars".
    job: Mapped[str] = mapped_column(String(60), nullable=False)

    status: Mapped[IngestionStatus] = enum_column(
        IngestionStatus, nullable=False, default=IngestionStatus.RUNNING
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Quota accounting. Cheap to write, and the only honest way to know whether
    # the schedule fits inside 5,000 requests/hour.
    api_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_calls_saved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer)
    rate_limit_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    records_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Resume point for interrupted or quota-exhausted runs, so the next run
    #: continues instead of restarting and re-spending quota.
    cursor: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_ingestion_run_source_job_started_at", "source", "job", "started_at"),
    )
