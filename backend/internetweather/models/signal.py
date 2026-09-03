"""Derived signals: the DETECT stage of the product loop.

Nothing in this module is ingested. Every column is the output of
``internetweather.analysis`` running over ``repository_metric_daily``. That
separation is what keeps weather states computed rather than hardcoded.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from internetweather.enums import EpistemicStatus, EventType, WeatherState
from internetweather.models._columns import enum_column
from internetweather.models.base import Base


class TechnologySignalDaily(Base):
    """Aggregated daily signal for one technology — what the Trends page reads.

    Denormalised on purpose. The Trends page must answer "what is changing in AI
    engineering right now?" in one indexed query, so ranks and weather states are
    precomputed here by a worker rather than derived per request.
    """

    __tablename__ = "technology_signal_daily"

    technology_id: Mapped[int] = mapped_column(
        ForeignKey("technology.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)

    # --- Classification -------------------------------------------------
    weather_state: Mapped[WeatherState] = enum_column(WeatherState, nullable=False)
    #: Normalised -1..1 composite. Positive = accelerating.
    momentum: Mapped[float] = mapped_column(Float, nullable=False)
    #: 0..1. Driven by how much history and how many repos support the verdict.
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # --- Attention signals ----------------------------------------------
    #: None when no stars snapshot is available for today.  Distinct from 0.
    stars_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stars_delta_1d: Mapped[int | None] = mapped_column(Integer)
    stars_delta_7d: Mapped[int | None] = mapped_column(Integer)
    stars_delta_28d: Mapped[int | None] = mapped_column(Integer)
    #: Weighted stars/day over the window, using technology_repository.weight.
    star_velocity_7d: Mapped[float | None] = mapped_column(Float)
    star_velocity_28d: Mapped[float | None] = mapped_column(Float)
    #: Change in velocity. This, not the level, is what "heating up" means.
    star_acceleration: Mapped[float | None] = mapped_column(Float)

    # --- Builder-activity signals ---------------------------------------
    activity_score: Mapped[float | None] = mapped_column(Float)
    commit_velocity_7d: Mapped[float | None] = mapped_column(Float)
    release_count_28d: Mapped[int | None] = mapped_column(Integer)
    contributor_count_28d: Mapped[int | None] = mapped_column(Integer)

    # --- Support / anomaly ----------------------------------------------
    repo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_repo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Standard deviations from the technology's own recent baseline.
    anomaly_z: Mapped[float | None] = mapped_column(Float)
    #: Observed days backing this row. Low values must lower confidence, never
    #: be dressed up as EMERGING.
    sample_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Precomputed ordering -------------------------------------------
    rank_overall: Mapped[int | None] = mapped_column(Integer)
    rank_subdomain: Mapped[int | None] = mapped_column(Integer)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("momentum >= -1 AND momentum <= 1", name="momentum_range"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        # The Trends query: latest day, ordered by precomputed rank.
        Index("ix_technology_signal_daily_day_rank_overall", "day", "rank_overall"),
        Index("ix_technology_signal_daily_day_momentum", "day", "momentum"),
    )


class EcosystemEvent(Base):
    """A discrete, dated occurrence worth explaining.

    Events are the bridge from DETECT to INVESTIGATE: a star spike or a major
    release is what the Research page is asked to account for.
    """

    __tablename__ = "ecosystem_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    technology_id: Mapped[int | None] = mapped_column(
        ForeignKey("technology.id", ondelete="CASCADE")
    )
    repository_id: Mapped[int | None] = mapped_column(
        ForeignKey("repository.id", ondelete="SET NULL")
    )

    event_type: Mapped[EventType] = enum_column(EventType, nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    title: Mapped[str] = mapped_column(String(280), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    #: 0..1 relative significance, used for ordering on the Trends page.
    magnitude: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Detected events are OBSERVATION. Anything the research engine concludes
    #: later is INFERENCE or HYPOTHESIS, and the UI must render it differently.
    epistemic_status: Mapped[EpistemicStatus] = enum_column(
        EpistemicStatus, nullable=False, default=EpistemicStatus.OBSERVATION
    )

    #: Provenance for this event: source URLs and the metric values that
    #: triggered it. Every significant claim has to be traceable.
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    #: Stable hash of (type, subject, day, discriminator). Makes detection
    #: idempotent — reruns update rather than duplicate.
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("magnitude >= 0 AND magnitude <= 1", name="magnitude_range"),
        Index("ix_ecosystem_event_occurred_on_magnitude", "occurred_on", "magnitude"),
        Index("ix_ecosystem_event_technology_id_occurred_on", "technology_id", "occurred_on"),
    )
