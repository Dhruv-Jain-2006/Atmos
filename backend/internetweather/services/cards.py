"""Mapping stored signal rows onto the wire contract.

The hover intelligence preview is assembled here, from columns that are already
loaded. No extra query, no LLM call, no second request from the client.
"""

from __future__ import annotations

from collections.abc import Sequence

from internetweather.analysis.explanation import (
    PreviewInput,
    describe,
    epistemic_status,
)
from internetweather.models import Technology, TechnologySignalDaily
from internetweather.schemas.technology import SignalSnapshot, TechnologyCard


def snapshot(signal: TechnologySignalDaily) -> SignalSnapshot:
    return SignalSnapshot(
        momentum=signal.momentum,
        confidence=signal.confidence,
        stars_total=signal.stars_total,
        stars_delta_7d=signal.stars_delta_7d,
        stars_delta_28d=signal.stars_delta_28d,
        star_velocity_7d=signal.star_velocity_7d,
        star_acceleration=signal.star_acceleration,
        activity_score=signal.activity_score,
        commit_velocity_7d=signal.commit_velocity_7d,
        release_count_28d=signal.release_count_28d,
        contributor_count_28d=signal.contributor_count_28d,
        anomaly_z=signal.anomaly_z,
        repo_count=signal.repo_count,
        active_repo_count=signal.active_repo_count,
        sample_days=signal.sample_days,
    )


def preview_input(signal: TechnologySignalDaily) -> PreviewInput:
    return PreviewInput(
        state=signal.weather_state,
        momentum=signal.momentum,
        confidence=signal.confidence,
        sample_days=signal.sample_days,
        star_velocity_7d=signal.star_velocity_7d,
        star_velocity_28d=signal.star_velocity_28d,
        anomaly_z=signal.anomaly_z,
        repo_count=signal.repo_count,
        active_repo_count=signal.active_repo_count,
    )


def to_card(
    technology: Technology,
    signal: TechnologySignalDaily,
    spark: Sequence[float] | None = None,
) -> TechnologyCard:
    preview = preview_input(signal)
    return TechnologyCard(
        slug=technology.slug,
        name=technology.name,
        subdomain=technology.subdomain,
        summary=technology.summary,
        headline=technology.headline,
        weather_state=signal.weather_state,
        signals=snapshot(signal),
        spark=list(spark or []),
        explanation=describe(preview),
        epistemic_status=epistemic_status(signal.confidence),
        rank_overall=signal.rank_overall,
        rank_subdomain=signal.rank_subdomain,
        as_of=signal.day,
    )
