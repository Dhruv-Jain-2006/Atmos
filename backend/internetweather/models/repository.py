"""GitHub repositories — the developer-behaviour sensors — and their daily facts."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from internetweather.enums import RecordSource, TrackingState
from internetweather.models._columns import enum_column
from internetweather.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from internetweather.models.technology import TechnologyRepository


class Repository(Base, TimestampMixin):
    """A tracked GitHub repository.

    Identity is ``github_id``, not ``full_name``. Verifying the seed universe
    turned up nine repositories that had been renamed or transferred; keying on
    the mutable name would have silently forked their history into two series.
    ``full_name`` is still unique — it is how humans and the seed file refer to a
    repo — but a rename updates it in place against the stable numeric id.
    """

    __tablename__ = "repository"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)

    full_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    owner: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)

    description: Mapped[str | None] = mapped_column(Text)
    homepage: Mapped[str | None] = mapped_column(Text)
    primary_language: Mapped[str | None] = mapped_column(String(60))
    topics: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    license_spdx: Mapped[str | None] = mapped_column(String(40))
    default_branch: Mapped[str | None] = mapped_column(String(120))

    is_fork: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at_github: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pushed_at_github: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Latest observed levels. Denormalised from repository_metric_daily so a
    # repo card renders without touching the fact table.
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    forks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watchers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Last ``ETag`` from the GitHub API. Replaying it makes an unchanged repo a
    #: 304, which costs no rate-limit quota at all.
    etag: Mapped[str | None] = mapped_column(String(120))

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Quota-aware backoff: workers skip repositories until this moment passes,
    #: so a quiet repo is polled less often than a moving one.
    next_sync_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tracking_state: Mapped[TrackingState] = enum_column(
        TrackingState, nullable=False, default=TrackingState.ACTIVE
    )
    source: Mapped[RecordSource] = enum_column(
        RecordSource, nullable=False, default=RecordSource.CURATED
    )

    technologies: Mapped[list[TechnologyRepository]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # The ingestion worker's hot query: what is due for a sync?
        Index("ix_repository_tracking_state_next_sync_after", "tracking_state", "next_sync_after"),
    )


class RepositoryMetricDaily(Base):
    """One row per repository per day. The atomic fact table.

    Daily rollups, not per-poll snapshots: polling four times a day and storing
    every poll would quadruple the row count for no analytical gain, and Neon's
    free tier caps storage at 0.5 GB.
    """

    __tablename__ = "repository_metric_daily"

    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repository.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)

    # Levels, as observed at the last poll of the day.
    # NULL means "unknown" — backfilled rows have no snapshot for these fields.
    stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watchers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_issues: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Deltas versus the previous stored day. Precomputed because velocity is
    # read far more often than it is written, and window functions over a
    # sparse series are error-prone when days are missing.
    stars_delta: Mapped[int | None] = mapped_column(Integer)
    forks_delta: Mapped[int | None] = mapped_column(Integer)

    # Activity counts for the day. These are the day-one trend signal
    # (locked decision #13): they need no historical backfill to be meaningful.
    commits: Mapped[int | None] = mapped_column(Integer)
    releases: Mapped[int | None] = mapped_column(Integer)
    issues_opened: Mapped[int | None] = mapped_column(Integer)
    prs_merged: Mapped[int | None] = mapped_column(Integer)
    contributors_active: Mapped[int | None] = mapped_column(Integer)

    #: True when the row was created during historical backfill. Backfilled rows
    #: have NULL stars/forks/watchers/open_issues (unknown historical levels)
    #: but may have observed commits and releases from GitHub's stats API.
    is_backfilled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "(stars IS NULL OR stars >= 0) AND (forks IS NULL OR forks >= 0)",
            name="non_negative_levels",
        ),
        # Retention pruning and whole-day recomputes scan by day.
        Index("ix_repository_metric_daily_day", "day"),
    )
