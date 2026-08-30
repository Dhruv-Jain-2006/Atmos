"""Incrementally sync repository levels and daily activity facts.

Resolved repositories produce one compact, idempotent daily row in
``repository_metric_daily``.  Each execution:

  1. Selects repositories where tracking_state = ACTIVE and
     next_sync_after <= now(), limited by --budget.
  2. For each repository:
     a. GET /repos/{o}/{n} with If-None-Match (304 = free).
     b. GET /repos/{o}/{n}/stats/commit_activity -> weekly commit totals.
     c. GET /repos/{o}/{n}/releases?per_page=30 -> releases per day.
     d. GET /repos/{o}/{n}/stats/contributors -> active contributor count.
  3. Backfills the trailing 28 days (commits + releases only).
  4. Writes today's full snapshot (levels + deltas + activity).
  5. Advances next_sync_after: 1 h if changes detected, 6 h otherwise.

    uv run python -m workers.github.sync_metrics --budget 800
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from internetweather.config import get_settings
from internetweather.models import Repository, RepositoryMetricDaily
from workers._runtime import (
    QuotaExhausted,
    RunStats,
    configure_logging,
    require_database,
    tracked_run,
)
from workers.github.resolve import (
    RepositoryInaccessible,
    TransientGitHubFailure,
    github_headers,
)

log = logging.getLogger("github.sync_metrics")
GITHUB_API = "https://api.github.com"
BACKFILL_DAYS = 28


@dataclass
class MetricResult:
    """Collected metrics for one repository on one observation date."""

    stars: int | None = None
    forks: int | None = None
    watchers: int | None = None
    open_issues: int | None = None
    commits: int | None = None
    releases: int | None = None
    contributors_active: int | None = None


UNCONDITIONAL_CALLS_PER_REPO = 3  # commit_activity, releases, contributors


class GitHubMetricClient:
    """Authenticated, retrying client for GitHub metric endpoints."""

    def __init__(self, client: httpx.Client, stats: RunStats, *, budget: int = 800):
        self.client = client
        self.stats = stats
        self.budget = budget

    def _track_rate(self, headers: httpx.Headers) -> None:
        try:
            remaining = headers.get("x-ratelimit-remaining")
            if remaining is not None:
                self.stats.rate_limit_remaining = int(remaining)
            reset = headers.get("x-ratelimit-reset")
            if reset is not None:
                self.stats.rate_limit_reset_at = datetime.fromtimestamp(int(reset), tz=UTC)
        except (OSError, OverflowError, ValueError):
            log.warning("GitHub returned invalid rate-limit headers")

    def check_rate_budget(self, repos_remaining: int) -> None:
        """Proactively stop before exhausting the GitHub API quota.

        Called before each unconditional request.  Estimates the cost of
        finishing the remaining repos and raises QuotaExhausted if the
        remaining budget is insufficient with a 20% safety margin.
        """
        if self.stats.rate_limit_remaining is None or self.stats.rate_limit_remaining == 0:
            return
        needed = repos_remaining * UNCONDITIONAL_CALLS_PER_REPO
        safety = int(needed * 0.20)
        if self.stats.rate_limit_remaining < needed + safety:
            raise QuotaExhausted(
                f"rate-limit safety threshold: {self.stats.rate_limit_remaining} remaining "
                f"< {needed} needed + {safety} margin for {repos_remaining} repos"
            )

    def _request(
        self, url: str, *, etag: str | None = None, label: str = "api"
    ) -> httpx.Response | None:
        """Single request with retry on transient failures.

        Returns None for 304 Not Modified (caller treats as "no change").
        Raises QuotaExhausted on 403/429 with empty rate-limit budget.
        """
        send_headers: dict[str, str] = {}
        if etag:
            send_headers["If-None-Match"] = etag

        def _do() -> httpx.Response:
            try:
                resp = self.client.get(url, headers=send_headers)
            except httpx.TransportError as exc:
                raise TransientGitHubFailure(f"{label}: network error: {exc}") from exc

            self.stats.api_calls += 1
            self._track_rate(resp.headers)

            if resp.status_code == 304:
                self.stats.api_calls_saved += 1
                return resp

            if resp.status_code in {403, 429} and self.stats.rate_limit_remaining == 0:
                raise QuotaExhausted(f"{label}: GitHub rate limit exhausted")

            if resp.status_code in {401, 403}:
                raise RepositoryInaccessible(f"{label}: forbidden or inaccessible")

            if 500 <= resp.status_code <= 599:
                raise TransientGitHubFailure(f"{label}: HTTP {resp.status_code}")

            return resp

        response = Retrying(
            retry=retry_if_exception_type(TransientGitHubFailure),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.1, min=0.1, max=1),
            reraise=True,
        )(_do)

        if response.status_code == 304:
            return None

        return response

    def fetch_repo(self, full_name: str, etag: str | None = None) -> dict | None:
        """GET /repos/{owner}/{name}. Returns None on 304 or 404."""
        response = self._request(f"/repos/{full_name}", etag=etag, label=full_name)
        if response is None:
            return None
        if response.status_code == 404:
            return None
        self.stats.records_read += 1
        data = response.json()
        if isinstance(data, dict):
            data["_etag"] = response.headers.get("etag")
        return data

    def fetch_commit_activity(self, full_name: str) -> list[dict]:
        """GET /repos/{o}/{n}/stats/commit_activity -> last year of weekly totals."""
        response = self._request(
            f"/repos/{full_name}/stats/commit_activity", label=full_name
        )
        if response is None:
            return []
        try:
            data = response.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def fetch_releases(self, full_name: str) -> list[str]:
        """GET /repos/{o}/{n}/releases -> list of creation date strings."""
        response = self._request(
            f"/repos/{full_name}/releases?per_page=30", label=full_name
        )
        if response is None:
            return []
        try:
            data = response.json()
            if isinstance(data, list):
                return [r.get("created_at", "") for r in data if isinstance(r, dict)]
            return []
        except Exception:
            return []

    def fetch_contributors(self, full_name: str) -> int:
        """GET /repos/{o}/{n}/stats/contributors -> unique contributor count."""
        response = self._request(
            f"/repos/{full_name}/stats/contributors", label=full_name
        )
        if response is None:
            return 0
        try:
            data = response.json()
            if isinstance(data, list):
                return len(data)
            return 0
        except Exception:
            return 0


def upsert_daily_metric(
    session,
    repository_id: int,
    day: date,
    metrics: MetricResult,
    *,
    is_backfilled: bool = False,
) -> bool:
    """Write one daily fact. Returns True if the row was created or changed."""
    existing = session.scalar(
        select(RepositoryMetricDaily).where(
            RepositoryMetricDaily.repository_id == repository_id,
            RepositoryMetricDaily.day == day,
        )
    )

    now = datetime.now(UTC)

    if existing is not None:
        changed = False
        fields: list[tuple[str, object]] = [
            ("stars", metrics.stars),
            ("forks", metrics.forks),
            ("watchers", metrics.watchers),
            ("open_issues", metrics.open_issues),
            ("commits", metrics.commits),
            ("releases", metrics.releases),
            ("contributors_active", metrics.contributors_active),
            ("collected_at", now),
        ]
        for attr, value in fields:
            if value is not None and getattr(existing, attr) != value:
                setattr(existing, attr, value)
                changed = True
        if changed:
            session.flush()
        return changed

    if is_backfilled:
        stars, forks, watchers, open_issues = None, None, None, None
    else:
        stars = metrics.stars
        forks = metrics.forks
        watchers = metrics.watchers
        open_issues = metrics.open_issues

    row = RepositoryMetricDaily(
        repository_id=repository_id,
        day=day,
        stars=stars,
        forks=forks,
        watchers=watchers,
        open_issues=open_issues,
        stars_delta=None,
        forks_delta=None,
        commits=metrics.commits,
        releases=metrics.releases,
        issues_opened=None,
        prs_merged=None,
        contributors_active=metrics.contributors_active,
        is_backfilled=is_backfilled,
        collected_at=now,
    )
    session.add(row)
    session.flush()
    return True


def _compute_next_sync(*, changes_detected: bool) -> datetime:
    """Advance next_sync_after based on repository activity."""
    now = datetime.now(UTC)
    return now + timedelta(hours=1) if changes_detected else now + timedelta(hours=6)


def _get_or_none(data: dict | None, key: str) -> int | None:
    if data is None:
        return None
    value = data.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _parse_date(date_str: str) -> date | None:
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


def _day_to_week_ts(d: date) -> int:
    """Convert a date to the POSIX timestamp of the start of its ISO week (Sunday)."""
    # GitHub's stats/commit_activity uses Sunday-start weeks.
    # The 'w' field is the POSIX timestamp of the Sunday that starts the week.
    days_since_sunday = d.weekday() - 6  # weekday(): Mon=0 .. Sun=6
    if days_since_sunday < 0:
        days_since_sunday += 7
    sunday = d - timedelta(days=days_since_sunday)
    return int(datetime(sunday.year, sunday.month, sunday.day, tzinfo=UTC).timestamp())


def _extract_weekly_commits(
    commit_activity: list[dict], target_day: date
) -> int | None:
    """Extract commit count for a specific day from weekly stats.

    The stats/commit_activity endpoint returns one entry per ISO week with a
    'total' for the week and 'days' array (Sun..Sat).  We distribute the
    weekly total evenly across days; Sunday gets the remainder.
    """
    if not commit_activity:
        return None
    ts = _day_to_week_ts(target_day)
    for week in commit_activity:
        if isinstance(week, dict) and week.get("week") == ts:
            total = week.get("total", 0)
            if target_day.weekday() == 6:
                return total
            return total // 7
    return None


def _build_daily_metrics(
    repo,
    repo_data: dict | None,
    commit_activity: list[dict],
    release_dates: list[str],
    contributors: int,
    today: date,
    backfill_days: int,
    all_metrics: dict,
) -> dict[date, MetricResult]:
    """Build MetricResult for each day in the backfill window + today."""
    daily: dict[date, MetricResult] = {}

    # Backfill: commits + releases only (no level reconstruction)
    for day_offset in range(backfill_days, 0, -1):
        day = today - timedelta(days=day_offset)
        if (repo.id, day) in all_metrics:
            continue

        commits = _extract_weekly_commits(commit_activity, day)
        rel_count = sum(1 for d in release_dates if _parse_date(d) == day)
        daily[day] = MetricResult(commits=commits, releases=rel_count or None)

    # Today: full snapshot with levels.
    # When repo_data is None (HTTP 304 — repo unchanged since last fetch),
    # fall back to the repository table's current values.  The resolve step
    # or a prior sync already populated repo.stars / forks / watchers /
    # open_issues, so these are the best-known snapshot levels.
    if repo_data is not None:
        today_stars = _get_or_none(repo_data, "stargazers_count")
        today_forks = _get_or_none(repo_data, "forks_count")
        today_watchers = _get_or_none(repo_data, "subscribers_count")
        today_open_issues = _get_or_none(repo_data, "open_issues_count")
    else:
        today_stars = repo.stars
        today_forks = repo.forks
        today_watchers = repo.watchers
        today_open_issues = repo.open_issues

    today_metrics = MetricResult(
        stars=today_stars,
        forks=today_forks,
        watchers=today_watchers,
        open_issues=today_open_issues,
        commits=_extract_weekly_commits(commit_activity, today),
        releases=sum(1 for d in release_dates if _parse_date(d) == today) or None,
        contributors_active=contributors if contributors > 0 else None,
    )
    daily[today] = today_metrics

    return daily


def _apply_deltas(
    session,
    repo_id: int,
    today: date,
    today_metrics: MetricResult,
    all_metrics: dict,
) -> None:
    """Compute and store stars_delta / forks_delta for today's row."""
    prev_day = today - timedelta(days=1)
    prev_metric = all_metrics.get((repo_id, prev_day))
    if prev_metric is None or today_metrics.stars is None:
        return

    today_row = session.scalar(
        select(RepositoryMetricDaily).where(
            RepositoryMetricDaily.repository_id == repo_id,
            RepositoryMetricDaily.day == today,
        )
    )
    if today_row is None:
        return

    if today_metrics.stars is not None and prev_metric.stars is not None:
        today_row.stars_delta = today_metrics.stars - prev_metric.stars
    if today_metrics.forks is not None and prev_metric.forks is not None:
        today_row.forks_delta = today_metrics.forks - prev_metric.forks
    session.flush()


def sync_metrics(
    stats: RunStats,
    *,
    budget: int = 800,
    backfill_days: int = BACKFILL_DAYS,
) -> None:
    """Core sync logic. Raises QuotaExhausted when budget exhausted."""
    settings = get_settings()
    headers = github_headers(settings.github_token)
    client_kw = dict(base_url=GITHUB_API, headers=headers, timeout=20, follow_redirects=True)

    # Pre-flight: fetch current rate limit using a one-shot request (not the
    # main httpx.Client, which may be mocked in tests).  This is best-effort;
    # failure does not block the sync.
    try:
        rl_resp = httpx.get(f"{GITHUB_API}/rate_limit", headers=headers, timeout=10)
        if rl_resp.status_code == 200:
            rl_data = rl_resp.json().get("resources", {}).get("core", {})
            remaining = rl_data.get("remaining", 0)
            reset_ts = rl_data.get("reset", 0)
            stats.rate_limit_remaining = remaining
            stats.rate_limit_reset_at = datetime.fromtimestamp(reset_ts, tz=UTC)
            log.info(
                "github rate limit: %d remaining, resets at %s",
                remaining,
                stats.rate_limit_reset_at.isoformat(),
            )
    except Exception:
        log.debug("pre-flight rate limit check skipped")

    with httpx.Client(**client_kw) as http_client:
        gh = GitHubMetricClient(http_client, stats, budget=budget)

        with tracked_run("github", "sync_metrics") as (session, run_stats):
            repositories = list(
                session.scalars(
                    select(Repository)
                    .where(
                        Repository.tracking_state == "active",
                        (Repository.next_sync_after.is_(None))
                        | (Repository.next_sync_after <= datetime.now(UTC)),
                    )
                    .order_by(Repository.next_sync_after)
                    .limit(budget * 2)
                )
            )

            today = datetime.now(UTC).date()

            all_metrics = {
                (m.repository_id, m.day): m
                for m in session.scalars(select(RepositoryMetricDaily)).all()
            }

            attempted = succeeded = failed = backfilled = incremental = 0
            for _idx, repo in enumerate(repositories):
                if attempted >= budget:
                    break

                # Proactive rate-limit safety: stop before exhausting quota.
                repos_remaining = budget - attempted
                gh.check_rate_budget(repos_remaining)

                attempted += 1
                full_name = repo.full_name

                try:
                    repo_data = gh.fetch_repo(full_name, etag=repo.etag)

                    if repo_data is not None:
                        for attr, key in [
                            ("stars", "stargazers_count"),
                            ("forks", "forks_count"),
                            ("watchers", "subscribers_count"),
                            ("open_issues", "open_issues_count"),
                        ]:
                            value = repo_data.get(key)
                            if isinstance(value, int) and not isinstance(value, bool):
                                setattr(repo, attr, value)

                        new_etag = repo_data.get("_etag")
                        if new_etag is not None:
                            repo.etag = new_etag
                        repo.last_synced_at = datetime.now(UTC)

                    commit_activity = gh.fetch_commit_activity(full_name)
                    release_dates = gh.fetch_releases(full_name)
                    contributors = gh.fetch_contributors(full_name)

                    daily_metrics = _build_daily_metrics(
                        repo, repo_data, commit_activity, release_dates,
                        contributors, today, backfill_days, all_metrics,
                    )

                    changes_detected = False
                    for day, metrics in daily_metrics.items():
                        is_backfill = day < today
                        created = upsert_daily_metric(
                            session, repo.id, day, metrics, is_backfilled=is_backfill,
                        )
                        if created:
                            changes_detected = True
                            if is_backfill:
                                backfilled += 1
                            else:
                                incremental += 1

                    today_metrics = daily_metrics.get(today)
                    if today_metrics:
                        _apply_deltas(session, repo.id, today, today_metrics, all_metrics)

                    repo.next_sync_after = _compute_next_sync(
                        changes_detected=changes_detected,
                    )
                    succeeded += 1

                except QuotaExhausted:
                    stats.cursor = {
                        "attempted": attempted,
                        "succeeded": succeeded,
                        "failed": failed,
                        "last_repo": full_name,
                    }
                    raise

                except Exception as exc:
                    failed += 1
                    log.error("failed to sync %s: %s", full_name, exc)

            run_stats.records_read = stats.records_read
            run_stats.records_written = backfilled + incremental
            run_stats.cursor = {
                "attempted": attempted,
                "succeeded": succeeded,
                "failed": failed,
                "backfilled_days": backfilled,
                "incremental_writes": incremental,
            }

            log.info(
                "sync_metrics done: attempted=%d succeeded=%d failed=%d "
                "backfilled=%d incremental=%d",
                attempted, succeeded, failed, backfilled, incremental,
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--budget",
        type=int,
        default=800,
        help="Maximum repositories to process in this run (default: 800)",
    )
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=BACKFILL_DAYS,
        help=f"Days of historical backfill (default: {BACKFILL_DAYS})",
    )
    args = parser.parse_args(argv)
    configure_logging()

    if not get_settings().github_token:
        log.error("GITHUB_TOKEN is required for GitHub metric sync")
        return 2

    if not require_database("github.sync_metrics"):
        return 2

    stats = RunStats()
    quota_exhausted = False

    try:
        sync_metrics(stats, budget=args.budget, backfill_days=args.backfill_days)
    except QuotaExhausted:
        quota_exhausted = True

    return 1 if quota_exhausted else 0


if __name__ == "__main__":
    sys.exit(main())
