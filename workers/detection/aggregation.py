"""Aggregate repository-level daily metrics into technology-level signals.

Pure functions: measured data in, interpretable signal dimensions out.
No database, no network, no LLM.  Every formula is deterministic and testable.

The seven signal dimensions each answer a different question:

1. VELOCITY       – Is activity changing?
2. ACCELERATION   – Is the rate of change itself increasing?
3. ANOMALY        – Is current activity unusual relative to the technology's baseline?
4. BREADTH        – Is the signal distributed across multiple repositories?
5. PERSISTENCE    – Has the signal persisted across multiple observations?
6. EVENT INTENSITY – Are there discrete events such as releases/activity bursts?
7. EVIDENCE DEPTH – How much trustworthy observation history supports the conclusion?
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, stdev

from internetweather.enums import RepoRelation, Subdomain
from internetweather.models import (
    RepositoryMetricDaily,
    Technology,
)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RepoLink:
    """One repository linked to a technology, with its relationship weight."""
    repository_id: int
    full_name: str
    weight: float
    relation: RepoRelation


@dataclass
class RepoDay:
    """One repository's observation for one day."""
    repository_id: int
    day: date
    stars: int | None = None
    forks: int | None = None
    watchers: int | None = None
    open_issues: int | None = None
    stars_delta: int | None = None
    forks_delta: int | None = None
    commits: int | None = None
    releases: int | None = None
    contributors_active: int | None = None
    is_backfilled: bool = False


@dataclass
class TechSignals:
    """Computed signals for one technology on one day."""
    technology_id: int
    slug: str
    name: str
    subdomain: Subdomain
    day: date

    # --- Levels ---
    stars_total: int = 0
    repo_count: int = 0
    active_repo_count: int = 0
    sample_days: int = 0

    # --- Velocity ---
    stars_delta_1d: int | None = None
    stars_delta_7d: int | None = None
    stars_delta_28d: int | None = None
    star_velocity_7d: float | None = None
    star_velocity_28d: float | None = None
    star_acceleration: float | None = None

    # --- Activity ---
    activity_score: float | None = None
    commit_velocity_7d: float | None = None
    release_count_28d: int | None = None
    contributor_count_28d: int | None = None

    # --- Anomaly ---
    anomaly_z: float | None = None
    volatility: float | None = None

    # --- Metadata ---
    recent_event_magnitude: float = 0.0
    age_days: int | None = None


# ---------------------------------------------------------------------------
# Data loading (pure transforms of SQLAlchemy results)
# ---------------------------------------------------------------------------

def load_repo_links(technologies: list[Technology]) -> dict[int, list[RepoLink]]:
    """Group technology_repository links by technology_id.

    Returns {technology_id: [RepoLink, ...]}.
    """
    links: dict[int, list[RepoLink]] = defaultdict(list)
    for tech in technologies:
        for tr in tech.repositories:
            links[tech.id].append(
                RepoLink(
                    repository_id=tr.repository_id,
                    full_name=tr.repository.full_name,
                    weight=tr.weight,
                    relation=tr.relation,
                )
            )
    return dict(links)


def load_repo_days(
    metrics: list[RepositoryMetricDaily],
) -> dict[int, dict[date, RepoDay]]:
    """Group repository_metric_daily rows by (repository_id, day).

    Returns {repository_id: {day: RepoDay}}.
    """
    by_repo: dict[int, dict[date, RepoDay]] = defaultdict(dict)
    for m in metrics:
        by_repo[m.repository_id][m.day] = RepoDay(
            repository_id=m.repository_id,
            day=m.day,
            stars=m.stars,
            forks=m.forks,
            watchers=m.watchers,
            open_issues=m.open_issues,
            stars_delta=m.stars_delta,
            forks_delta=m.forks_delta,
            commits=m.commits,
            releases=m.releases,
            contributors_active=m.contributors_active,
            is_backfilled=m.is_backfilled,
        )
    return dict(by_repo)


# ---------------------------------------------------------------------------
# Daily weighted delta computation
# ---------------------------------------------------------------------------

def _weighted_delta_on_day(
    repo_links: list[RepoLink],
    repo_days: dict[int, dict[date, RepoDay]],
    target_day: date,
) -> tuple[float | None, int]:
    """Compute the weighted star delta for one technology on one day.

    Returns (weighted_delta, repos_with_known_delta).
    weighted_delta is None when no repo has a known delta.
    """
    total_delta = 0.0
    known = 0

    for link in repo_links:
        days = repo_days.get(link.repository_id, {})
        today = days.get(target_day)
        yesterday = days.get(target_day - timedelta(days=1))

        # Prefer pre-computed stars_delta when available (and not backfilled).
        if today is not None and today.stars_delta is not None and not today.is_backfilled:
            total_delta += link.weight * today.stars_delta
            known += 1
        elif (
            today is not None
            and today.stars is not None
            and yesterday is not None
            and yesterday.stars is not None
            and not today.is_backfilled
            and not yesterday.is_backfilled
        ):
            total_delta += link.weight * (today.stars - yesterday.stars)
            known += 1
        # else: unknown delta for this repo, skip

    return (total_delta, known) if known > 0 else (None, 0)


def compute_daily_weighted_deltas(
    repo_links: list[RepoLink],
    repo_days: dict[int, dict[date, RepoDay]],
    window_start: date,
    window_end: date,
) -> list[float]:
    """Compute daily weighted star deltas for a date window.

    Only includes days where at least one repo has a known delta.
    Returns a list of daily weighted deltas (may be shorter than the window).
    """
    deltas: list[float] = []
    day = window_start
    while day <= window_end:
        delta, _ = _weighted_delta_on_day(repo_links, repo_days, day)
        if delta is not None:
            deltas.append(delta)
        day += timedelta(days=1)
    return deltas


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def compute_activity_on_day(
    repo_links: list[RepoLink],
    repo_days: dict[int, dict[date, RepoDay]],
    target_day: date,
) -> float:
    """Compute weighted activity score for one day.

    Activity = weighted (commits + releases * 5).
    Releases are weighted 5x because they are more significant discrete events.
    """
    score = 0.0
    for link in repo_links:
        days = repo_days.get(link.repository_id, {})
        rd = days.get(target_day)
        if rd is None:
            continue
        commits = rd.commits or 0
        releases = rd.releases or 0
        score += link.weight * (commits + releases * 5)
    return score


def compute_tech_signals(
    tech: Technology,
    repo_links: list[RepoLink],
    repo_days: dict[int, dict[date, RepoDay]],
    today: date,
    window_days: int = 28,
) -> TechSignals:
    """Compute all signal dimensions for one technology on one day.

    Pure function: all data is passed in, nothing is fetched.
    """
    signals = TechSignals(
        technology_id=tech.id,
        slug=tech.slug,
        name=tech.name,
        subdomain=tech.subdomain,
        day=today,
    )

    if not repo_links:
        return signals

    signals.repo_count = len(repo_links)
    window_start = today - timedelta(days=window_days - 1)

    # --- Stars total (unweighted sum of live observations) ---
    total_stars = 0
    for link in repo_links:
        days = repo_days.get(link.repository_id, {})
        rd = days.get(today)
        if rd is not None and rd.stars is not None:
            total_stars += rd.stars
    signals.stars_total = total_stars

    # --- Sample days (days where at least one repo has a non-NULL metric) ---
    sample_days_set: set[date] = set()
    for link in repo_links:
        days = repo_days.get(link.repository_id, {})
        for day, rd in days.items():
            if (
                rd.stars is not None
                or rd.commits is not None
                or rd.releases is not None
            ):
                sample_days_set.add(day)
    signals.sample_days = len(sample_days_set)

    # --- Active repos (any commits or releases in last 7 days) ---
    active_repos: set[int] = set()
    seven_days_ago = today - timedelta(days=6)
    for link in repo_links:
        days = repo_days.get(link.repository_id, {})
        for day, rd in days.items():
            if day >= seven_days_ago and (
                (rd.commits is not None and rd.commits > 0)
                or (rd.releases is not None and rd.releases > 0)
            ):
                active_repos.add(link.repository_id)
                break
    signals.active_repo_count = len(active_repos)

    # --- Daily weighted deltas ---
    all_deltas = compute_daily_weighted_deltas(
        repo_links, repo_days, window_start, today
    )

    # --- Stars deltas (1d, 7d, 28d) ---
    # 1-day delta: most recent daily weighted delta
    if all_deltas:
        signals.stars_delta_1d = round(all_deltas[-1])

    # 7-day delta: sum of last 7 daily deltas
    recent_7 = all_deltas[-7:] if len(all_deltas) >= 1 else []
    if len(recent_7) >= 1:
        signals.stars_delta_7d = round(sum(recent_7))

    # 28-day delta: sum of all daily deltas in window
    if all_deltas:
        signals.stars_delta_28d = round(sum(all_deltas))

    # --- Star velocity (weighted stars/day) ---
    if signals.stars_delta_7d is not None:
        signals.star_velocity_7d = signals.stars_delta_7d / min(len(recent_7), 7)
    if signals.stars_delta_28d is not None:
        signals.star_velocity_28d = signals.stars_delta_28d / min(len(all_deltas), 28)

    # --- Star acceleration ---
    eps = 0.05
    if signals.star_velocity_7d is not None and signals.star_velocity_28d is not None:
        v7 = max(signals.star_velocity_7d, 0.0) + eps
        v28 = max(signals.star_velocity_28d, 0.0) + eps
        ratio = v7 / v28
        if ratio > 0:
            signals.star_acceleration = round(math.log(ratio), 6)

    # --- Anomaly z-score ---
    if len(all_deltas) >= 7:
        mu = mean(all_deltas)
        sigma = stdev(all_deltas) if len(all_deltas) >= 2 else 0.0
        if signals.star_velocity_7d is not None and sigma > eps:
            signals.anomaly_z = round(
                (signals.star_velocity_7d - mu) / sigma, 4
            )
        else:
            signals.anomaly_z = 0.0

        # Volatility: coefficient of variation of daily deltas
        if mu != 0 and sigma > 0:
            signals.volatility = round(abs(sigma / mu), 4) if mu != 0 else None
        elif sigma > 0:
            # Mean is zero but there's variation – high relative volatility
            signals.volatility = 2.0  # ceiling

    # --- Activity signals ---
    activity_7d = []
    activity_28d = []
    release_count = 0
    contributor_max = 0

    day = window_start
    while day <= today:
        act = compute_activity_on_day(repo_links, repo_days, day)
        if day >= today - timedelta(days=6):
            activity_7d.append(act)
        activity_28d.append(act)

        # Release count: sum of releases across all repos for the day
        day_releases = 0
        day_contributors = 0
        for link in repo_links:
            days = repo_days.get(link.repository_id, {})
            rd = days.get(day)
            if rd is not None:
                day_releases += rd.releases or 0
                if rd.contributors_active is not None:
                    day_contributors = max(day_contributors, rd.contributors_active)
        release_count += day_releases
        contributor_max = max(contributor_max, day_contributors)
        day += timedelta(days=1)

    if activity_7d:
        signals.commit_velocity_7d = round(
            sum(activity_7d) / len(activity_7d), 4
        )
    if activity_28d:
        signals.activity_score = round(
            sum(activity_28d) / len(activity_28d), 4
        )

    signals.release_count_28d = release_count if release_count > 0 else None
    signals.contributor_count_28d = contributor_max if contributor_max > 0 else None

    # Age is computed externally from repository.created_at_github
    # because the metric loading query doesn't include it.
    # The caller should set signals.age_days before classification.

    return signals
