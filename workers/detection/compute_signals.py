"""Aggregate repository daily facts into per-technology signals and events.

This is the DETECT stage of the product loop.  Deterministic and statistical
only — no LLM.  The classifier lives in ``internetweather.analysis.weather_state``
and is already implemented and tested.

For every active technology:

1.  Load its linked repositories and their relationship weights.
2.  Load the trailing 28 days of repository_metric_daily for those repos.
3.  Aggregate into technology-level signals (velocity, acceleration, anomaly,
    breadth, persistence, event intensity, evidence depth).
4.  Classify via weather_state.classify() → WeatherState, momentum, confidence.
5.  Upsert one technology_signal_daily row.
6.  Emit ecosystem_event rows for meaningful transitions and anomalies.
7.  Assign rank_overall and rank_subdomain via window functions.

Recomputes the trailing 7 days on every run so late-arriving backfill data
corrects previous classifications.

    uv run python -m workers.detection.compute_signals --day 2026-08-26
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import joinedload

from internetweather.analysis.explanation import (
    PreviewInput,
)
from internetweather.analysis.weather_state import SignalInput, classify
from internetweather.enums import EpistemicStatus, EventType, WeatherState
from internetweather.models import (
    EcosystemEvent,
    RepositoryMetricDaily,
    Technology,
    TechnologyRepository,
    TechnologySignalDaily,
)
from workers._runtime import RunStats, configure_logging, require_database, tracked_run
from workers.detection.aggregation import (
    compute_tech_signals,
    load_repo_days,
    load_repo_links,
)

log = logging.getLogger("detection.compute_signals")

RECOMPUTE_WINDOW = 7  # reclassify trailing 7 days
BACKFILL_WINDOW = 28  # anomaly baseline


def _load_technologies(session) -> list[Technology]:
    """Load all active technologies with their repository links."""
    return list(
        session.scalars(
            select(Technology)
            .where(Technology.is_active.is_(True))
            .options(
                joinedload(Technology.repositories).joinedload(
                    TechnologyRepository.repository
                )
            )
        ).unique()
    )


def _load_metrics(
    session, repo_ids: list[int], since: date
) -> list[RepositoryMetricDaily]:
    """Load repository_metric_daily for the given repos since a date."""
    if not repo_ids:
        return []
    return list(
        session.scalars(
            select(RepositoryMetricDaily).where(
                RepositoryMetricDaily.repository_id.in_(repo_ids),
                RepositoryMetricDaily.day >= since,
            )
        )
    )


def _upsert_signal(session, sig, classification, preview_input) -> None:
    """Upsert one technology_signal_daily row."""
    row = {
        "technology_id": sig.technology_id,
        "day": sig.day,
        "weather_state": classification.state.value,
        "momentum": classification.momentum,
        "confidence": classification.confidence,
        "stars_total": sig.stars_total,
        "stars_delta_1d": sig.stars_delta_1d,
        "stars_delta_7d": sig.stars_delta_7d,
        "stars_delta_28d": sig.stars_delta_28d,
        "star_velocity_7d": sig.star_velocity_7d,
        "star_velocity_28d": sig.star_velocity_28d,
        "star_acceleration": sig.star_acceleration,
        "activity_score": sig.activity_score,
        "commit_velocity_7d": sig.commit_velocity_7d,
        "release_count_28d": sig.release_count_28d,
        "contributor_count_28d": sig.contributor_count_28d,
        "repo_count": sig.repo_count,
        "active_repo_count": sig.active_repo_count,
        "anomaly_z": sig.anomaly_z,
        "sample_days": sig.sample_days,
        "computed_at": datetime.now(UTC),
    }

    stmt = insert(TechnologySignalDaily).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["technology_id", "day"],
        set_={k: v for k, v in row.items() if k not in ("technology_id", "day")},
    )
    session.execute(stmt)


def _detect_events(
    session,
    tech: Technology,
    sig,
    classification,
    prev_signal: TechnologySignalDaily | None,
) -> None:
    """Generate ecosystem_event rows for meaningful transitions."""
    today = sig.day

    # --- State transition ---
    if prev_signal is not None and prev_signal.weather_state != classification.state:
        magnitude = _transition_magnitude(prev_signal.weather_state, classification.state)
        if magnitude > 0:
            _emit_event(
                session,
                technology_id=tech.id,
                event_type=_event_type_for_state(classification.state),
                occurred_on=today,
                title=f"{tech.name} became {classification.state.value.upper()}",
                summary=(
                    f"{tech.name} transitioned from "
                    f"{prev_signal.weather_state.value} to {classification.state.value}."
                ),
                magnitude=magnitude,
                confidence=classification.confidence,
                evidence={
                    "metrics": {
                        "previous_state": prev_signal.weather_state.value,
                        "new_state": classification.state.value,
                        "momentum": classification.momentum,
                        "anomaly_z": sig.anomaly_z,
                        "stars_total": sig.stars_total,
                    }
                },
                dedupe_key=f"state_transition:{tech.id}:{today}:{classification.state.value}",
            )

    # --- Significant anomaly ---
    if sig.anomaly_z is not None and abs(sig.anomaly_z) >= 2.0:
        direction = "spike" if sig.anomaly_z > 0 else "drop"
        _emit_event(
            session,
            technology_id=tech.id,
            event_type=EventType.ANOMALY,
            occurred_on=today,
            title=f"{tech.name} anomaly: {direction} detected",
            summary=(
                f"{tech.name} is {sig.anomaly_z:+.1f}σ from its own baseline "
                f"({sig.stars_total} stars, {sig.repo_count} repos)."
            ),
            magnitude=min(1.0, abs(sig.anomaly_z) / 4.0),
            confidence=classification.confidence,
            evidence={
                "metrics": {
                    "anomaly_z": sig.anomaly_z,
                    "star_velocity_7d": sig.star_velocity_7d,
                    "star_velocity_28d": sig.star_velocity_28d,
                    "stars_total": sig.stars_total,
                    "sample_days": sig.sample_days,
                }
            },
            dedupe_key=f"anomaly:{tech.id}:{today}:{direction}",
        )

    # --- Significant release burst ---
    if sig.release_count_28d is not None and sig.release_count_28d >= 3:
        _emit_event(
            session,
            technology_id=tech.id,
            event_type=EventType.RELEASE,
            occurred_on=today,
            title=f"{tech.name}: {sig.release_count_28d} releases in 28 days",
            summary=(
                f"{sig.release_count_28d} releases across "
                f"{sig.repo_count} repositories in the last 28 days."
            ),
            magnitude=min(1.0, sig.release_count_28d / 10.0),
            confidence=classification.confidence,
            evidence={
                "metrics": {
                    "release_count_28d": sig.release_count_28d,
                    "repo_count": sig.repo_count,
                }
            },
            dedupe_key=f"release_burst:{tech.id}:{today}:{sig.release_count_28d}",
        )


def _emit_event(
    session,
    *,
    technology_id: int,
    event_type: EventType,
    occurred_on: date,
    title: str,
    summary: str,
    magnitude: float,
    confidence: float,
    evidence: dict,
    dedupe_key: str,
) -> None:
    """Upsert an ecosystem event, deduplicating by dedupe_key."""
    row = {
        "technology_id": technology_id,
        "repository_id": None,
        "event_type": event_type.value,
        "occurred_on": occurred_on,
        "occurred_at": datetime.now(UTC),
        "title": title,
        "summary": summary,
        "magnitude": magnitude,
        "confidence": confidence,
        "epistemic_status": EpistemicStatus.OBSERVATION.value,
        "evidence": evidence,
        "dedupe_key": dedupe_key,
        "detected_at": datetime.now(UTC),
    }

    stmt = insert(EcosystemEvent).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["dedupe_key"],
        set_={k: v for k, v in row.items() if k != "dedupe_key"},
    )
    session.execute(stmt)


def _transition_magnitude(prev: WeatherState, new: WeatherState) -> float:
    """Estimate significance of a state transition. 0 = not worth an event."""
    # Major transitions are more significant
    major = {
        (WeatherState.STABLE, WeatherState.HOT),
        (WeatherState.STABLE, WeatherState.EMERGING),
        (WeatherState.STABLE, WeatherState.COOLING),
        (WeatherState.EMERGING, WeatherState.HOT),
        (WeatherState.HOT, WeatherState.STORM),
        (WeatherState.COOLING, WeatherState.STABLE),
    }
    if (prev, new) in major:
        return 0.5
    # Minor transitions
    if prev != new:
        return 0.3
    return 0.0


def _event_type_for_state(state: WeatherState) -> EventType:
    """Map weather state to event type for state transitions."""
    mapping = {
        WeatherState.HOT: EventType.STAR_SPIKE,
        WeatherState.EMERGING: EventType.STAR_SPIKE,
        WeatherState.BREAKING: EventType.ANOMALY,
        WeatherState.STORM: EventType.ANOMALY,
        WeatherState.COOLING: EventType.ANOMALY,
        WeatherState.STABLE: EventType.ANOMALY,
    }
    return mapping.get(state, EventType.ANOMALY)


def _assign_ranks(session, day: date) -> None:
    """Assign rank_overall and rank_subdomain for a given day."""
    # Subquery for ranks
    ranked = (
        select(
            TechnologySignalDaily.technology_id,
            func.rank()
            .over(
                order_by=TechnologySignalDaily.momentum.desc(),
            )
            .label("rank_overall"),
            func.rank()
            .over(
                partition_by=Technology.subdomain,
                order_by=TechnologySignalDaily.momentum.desc(),
            )
            .label("rank_subdomain"),
        )
        .join(Technology, Technology.id == TechnologySignalDaily.technology_id)
        .where(TechnologySignalDaily.day == day)
        .subquery()
    )

    session.execute(
        update(TechnologySignalDaily)
        .where(TechnologySignalDaily.day == day)
        .values(
            rank_overall=select(ranked.c.rank_overall)
            .where(ranked.c.technology_id == TechnologySignalDaily.technology_id)
            .correlate(TechnologySignalDaily)
            .scalar_subquery(),
            rank_subdomain=select(ranked.c.rank_subdomain)
            .where(ranked.c.technology_id == TechnologySignalDaily.technology_id)
            .correlate(TechnologySignalDaily)
            .scalar_subquery(),
        )
    )


def compute_signals(
    stats: RunStats,
    *,
    target_day: date | None = None,
    recompute_window: int = RECOMPUTE_WINDOW,
) -> None:
    """Core detection logic.  Processes the target day and trailing window."""
    with tracked_run("detection", "compute_signals") as (session, run_stats):
        technologies = _load_technologies(session)
        if not technologies:
            log.warning("no active technologies found")
            return

        repo_links_map = load_repo_links(technologies)
        all_repo_ids = list(
            {link.repository_id for links in repo_links_map.values() for link in links}
        )

        if target_day is None:
            target_day = datetime.now(UTC).date()

        # Load 28 days of metrics for the full baseline, regardless of the
        # recompute window.  The classifier and aggregation functions need
        # 28-day velocity and anomaly baselines that span beyond the trailing
        # recompute window.
        metrics_start = target_day - timedelta(days=BACKFILL_WINDOW)
        window_start = target_day - timedelta(days=recompute_window - 1)
        metrics = _load_metrics(session, all_repo_ids, metrics_start)
        repo_days = load_repo_days(metrics)

        # Load previous signals for state transition detection
        prev_signals: dict[int, TechnologySignalDaily] = {}
        prev_day = target_day - timedelta(days=1)
        for sig_row in session.scalars(
            select(TechnologySignalDaily).where(
                TechnologySignalDaily.day == prev_day
            )
        ):
            prev_signals[sig_row.technology_id] = sig_row

        processed = 0
        events_emitted = 0

        # Process each day in the recompute window
        day = window_start
        while day <= target_day:
            for tech in technologies:
                links = repo_links_map.get(tech.id, [])
                if not links:
                    continue

                sig = compute_tech_signals(tech, links, repo_days, day)

                signal_input = SignalInput(
                    star_velocity_7d=sig.star_velocity_7d,
                    star_velocity_28d=sig.star_velocity_28d,
                    activity_velocity_7d=sig.commit_velocity_7d,
                    activity_velocity_28d=sig.activity_score,
                    anomaly_z=sig.anomaly_z,
                    volatility=sig.volatility,
                    stars_total=sig.stars_total,
                    sample_days=sig.sample_days,
                    repo_count=sig.repo_count,
                    active_repo_count=sig.active_repo_count,
                    age_days=sig.age_days,
                    recent_event_magnitude=sig.recent_event_magnitude,
                )

                classification = classify(signal_input)
                preview = PreviewInput.from_classification(classification, signal_input)

                _upsert_signal(session, sig, classification, preview)

                # Events only for the target day
                if day == target_day:
                    prev_sig = prev_signals.get(tech.id)
                    _detect_events(session, tech, sig, classification, prev_sig)
                    events_emitted += 1

                processed += 1

            day += timedelta(days=1)

        # Assign ranks for the target day
        _assign_ranks(session, target_day)

        run_stats.records_written = processed
        run_stats.cursor = {
            "target_day": str(target_day),
            "technologies": len(technologies),
            "signals_computed": processed,
            "events_emitted": events_emitted,
        }

        log.info(
            "compute_signals done: technologies=%d signals=%d events=%d",
            len(technologies),
            processed,
            events_emitted,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--day",
        type=str,
        default=None,
        help="Target date (YYYY-MM-DD). Default: today.",
    )
    parser.add_argument(
        "--recompute-window",
        type=int,
        default=RECOMPUTE_WINDOW,
        help=f"Days to recompute (default: {RECOMPUTE_WINDOW})",
    )
    args = parser.parse_args(argv)
    configure_logging()

    if not require_database("detection.compute_signals"):
        return 2

    target_day = None
    if args.day:
        target_day = date.fromisoformat(args.day)

    stats = RunStats()
    try:
        compute_signals(
            stats,
            target_day=target_day,
            recompute_window=args.recompute_window,
        )
    except Exception:
        log.exception("compute_signals failed")
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
