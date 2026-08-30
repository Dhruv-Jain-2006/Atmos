"""Tests for GitHub daily metric ingestion; all HTTP and DB interactions are mocked."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest

from internetweather.models import Repository, RepositoryMetricDaily
from workers._runtime import QuotaExhausted, RunStats
from workers.github.resolve import TransientGitHubFailure
from workers.github.sync_metrics import (
    GitHubMetricClient,
    MetricResult,
    _compute_next_sync,
    _day_to_week_ts,
    _extract_weekly_commits,
    _get_or_none,
    _parse_date,
    sync_metrics,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _response(status: int, body=None, headers=None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers or {})


def _repo_payload(**overrides):
    base = {
        "stargazers_count": 100,
        "forks_count": 20,
        "subscribers_count": 5,
        "open_issues_count": 12,
    }
    return base | overrides


class FakeHTTPClient:
    """Mock httpx.Client that returns pre-configured responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self._idx = 0
        self.calls: list[str] = []

    def get(self, url, headers=None):
        self.calls.append(url)
        if self._idx >= len(self._responses):
            return _response(404)
        resp = self._responses[self._idx]
        self._idx += 1
        return resp


class FakeSession:
    """Minimal SQLAlchemy-like session for unit tests.

    Tracks repositories and metrics separately so ``scalars()`` returns the
    right type for both ``select(Repository)`` and ``select(RepositoryMetricDaily)``.
    """

    def __init__(self):
        self.repos: list = []
        self.metrics: list = []
        self._next_id = 1

    @property
    def _rows(self):
        return self.repos + self.metrics

    def add(self, row):
        if isinstance(row, RepositoryMetricDaily):
            self.metrics.append(row)
        else:
            self.repos.append(row)
        if getattr(row, "id", None) is None:
            row.id = self._next_id
            self._next_id += 1

    def flush(self):
        pass

    def scalars(self, stmt):
        # Determine which model the query selects by inspecting the columns.
        # Use selected_columns (not .columns) to avoid SA deprecation.
        col_names = (
            [c.name for c in stmt.selected_columns]
            if hasattr(stmt, "selected_columns")
            else []
        )
        rows = self.metrics if ("repository_id" in col_names and "day" in col_names) else self.repos
        return MagicMock(all=lambda: rows, __iter__=lambda s: iter(rows))

    def scalar(self, stmt):
        return None


def _make_repo(
    id=1,
    full_name="acme/widget",
    stars=100,
    forks=20,
    watchers=5,
    open_issues=12,
    etag=None,
    next_sync_after=None,
):
    repo = MagicMock(spec=Repository)
    repo.id = id
    repo.full_name = full_name
    repo.stars = stars
    repo.forks = forks
    repo.watchers = watchers
    repo.open_issues = open_issues
    repo.etag = etag
    repo.next_sync_after = next_sync_after
    repo.last_synced_at = None
    return repo


def _make_metric(repository_id=1, day=None, stars=100, forks=20):
    m = MagicMock(spec=RepositoryMetricDaily)
    m.repository_id = repository_id
    m.day = day or date.today()
    m.stars = stars
    m.forks = forks
    m.watchers = 5
    m.open_issues = 12
    return m


def _patch_for_sync(session, stats, http_client):
    """Return context-manager mocks for tracked_run and httpx.Client."""
    tracked_ctx = MagicMock()
    tracked_ctx.__enter__ = MagicMock(return_value=(session, stats))
    tracked_ctx.__exit__ = MagicMock(return_value=False)

    return tracked_ctx


# ---------------------------------------------------------------------------
# Unit tests -- helpers
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_valid_iso(self):
        assert _parse_date("2025-06-15T10:30:00Z") == date(2025, 6, 15)

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_none(self):
        assert _parse_date(None) is None


class TestGetOrNull:
    def test_valid_int(self):
        assert _get_or_none({"stars": 42}, "stars") == 42

    def test_missing_key(self):
        assert _get_or_none({"stars": 42}, "forks") is None

    def test_none_data(self):
        assert _get_or_none(None, "stars") is None

    def test_bool_excluded(self):
        assert _get_or_none({"flag": True}, "flag") is None


class TestExtractWeeklyCommits:
    def test_sunday_gets_total(self):
        activity = [{"week": _day_to_week_ts(date(2025, 6, 15)), "total": 42, "days": [0] * 7}]
        result = _extract_weekly_commits(activity, date(2025, 6, 15))
        assert result == 42

    def test_no_activity(self):
        assert _extract_weekly_commits([], date(2025, 6, 15)) is None

    def test_non_dict_week_skipped(self):
        result = _extract_weekly_commits(["bad"], date(2025, 6, 15))
        assert result is None


class TestComputeNextSync:
    def test_changes_detected(self):
        result = _compute_next_sync(changes_detected=True)
        now = datetime.now(UTC)
        assert result > now
        assert result <= now + timedelta(hours=2)

    def test_no_changes(self):
        result = _compute_next_sync(changes_detected=False)
        now = datetime.now(UTC)
        assert result > now + timedelta(hours=5)
        assert result <= now + timedelta(hours=7)


# ---------------------------------------------------------------------------
# Unit tests -- MetricResult
# ---------------------------------------------------------------------------


class TestMetricResult:
    def test_defaults(self):
        m = MetricResult()
        assert m.stars is None
        assert m.forks is None
        assert m.commits is None
        assert m.releases is None

    def test_with_values(self):
        m = MetricResult(stars=10, forks=2, commits=5, releases=1)
        assert m.stars == 10
        assert m.commits == 5


# ---------------------------------------------------------------------------
# Unit tests -- GitHubMetricClient
# ---------------------------------------------------------------------------


class TestGitHubMetricClient:
    def test_fetch_repo_success(self):
        stats = RunStats()
        client = FakeHTTPClient(
            [_response(200, _repo_payload(), {"etag": '"v1"'})]
        )
        gh = GitHubMetricClient(client, stats)
        data = gh.fetch_repo("acme/widget")
        assert data is not None
        assert data["stargazers_count"] == 100
        assert data["_etag"] == '"v1"'
        assert stats.api_calls == 1

    def test_fetch_repo_304(self):
        stats = RunStats()
        client = FakeHTTPClient([_response(304)])
        gh = GitHubMetricClient(client, stats)
        data = gh.fetch_repo("acme/widget", etag='"v1"')
        assert data is None
        assert stats.api_calls_saved == 1

    def test_fetch_repo_404(self):
        stats = RunStats()
        client = FakeHTTPClient([_response(404)])
        gh = GitHubMetricClient(client, stats)
        data = gh.fetch_repo("acme/missing")
        assert data is None

    def test_fetch_commit_activity_success(self):
        stats = RunStats()
        week_data = [{"week": 1719792000, "total": 42, "days": [5, 6, 7, 8, 9, 3, 4]}]
        client = FakeHTTPClient([_response(200, week_data)])
        gh = GitHubMetricClient(client, stats)
        result = gh.fetch_commit_activity("acme/widget")
        assert len(result) == 1
        assert result[0]["total"] == 42

    def test_fetch_commit_activity_empty(self):
        stats = RunStats()
        client = FakeHTTPClient([_response(200, [])])
        gh = GitHubMetricClient(client, stats)
        assert gh.fetch_commit_activity("acme/widget") == []

    def test_fetch_releases_success(self):
        stats = RunStats()
        releases = [
            {"created_at": "2025-06-15T10:00:00Z"},
            {"created_at": "2025-06-10T08:00:00Z"},
        ]
        client = FakeHTTPClient([_response(200, releases)])
        gh = GitHubMetricClient(client, stats)
        dates = gh.fetch_releases("acme/widget")
        assert len(dates) == 2

    def test_fetch_contributors_success(self):
        stats = RunStats()
        contributors = [{"author": {"login": "a"}}, {"author": {"login": "b"}}]
        client = FakeHTTPClient([_response(200, contributors)])
        gh = GitHubMetricClient(client, stats)
        assert gh.fetch_contributors("acme/widget") == 2

    def test_rate_limit_exhausted(self):
        stats = RunStats(rate_limit_remaining=0)
        client = FakeHTTPClient(
            [_response(429, {"message": "rate limit"}, {"x-ratelimit-remaining": "0"})]
        )
        gh = GitHubMetricClient(client, stats)
        with pytest.raises(QuotaExhausted):
            gh.fetch_repo("acme/widget")

    def test_transient_failure_retries(self):
        stats = RunStats()
        client = FakeHTTPClient(
            [_response(502), _response(200, _repo_payload())]
        )
        gh = GitHubMetricClient(client, stats)
        data = gh.fetch_repo("acme/widget")
        assert data is not None
        assert data["stargazers_count"] == 100
        assert len(client.calls) == 2

    def test_all_retries_exhausted_raises(self):
        stats = RunStats()
        client = FakeHTTPClient(
            [_response(502), _response(502), _response(502), _response(502)]
        )
        gh = GitHubMetricClient(client, stats)
        with pytest.raises(TransientGitHubFailure):
            gh.fetch_repo("acme/widget")

    def test_rate_headers_tracked(self):
        stats = RunStats()
        client = FakeHTTPClient(
            [
                _response(
                    200,
                    _repo_payload(),
                    {
                        "x-ratelimit-remaining": "4999",
                        "x-ratelimit-reset": str(
                            int(datetime.now(UTC).timestamp()) + 3600
                        ),
                    },
                )
            ]
        )
        gh = GitHubMetricClient(client, stats)
        gh.fetch_repo("acme/widget")
        assert stats.rate_limit_remaining == 4999
        assert stats.rate_limit_reset_at is not None

    def test_etag_passed_in_header(self):
        stats = RunStats()
        client = FakeHTTPClient([_response(304)])
        gh = GitHubMetricClient(client, stats)
        gh.fetch_repo("acme/widget", etag='"abc123"')
        assert len(client.calls) == 1


# ---------------------------------------------------------------------------
# Integration tests -- sync_metrics with mocked session
# ---------------------------------------------------------------------------


class TestSyncMetrics:
    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_successful_sync(self, mock_client, mock_settings, mock_tracked):
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo()
        session.repos = [repo]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                _response(200, _repo_payload(stargazers_count=105), {"etag": '"v2"'}),
                _response(200, [{"week": today_ts, "total": 14, "days": [2] * 7}]),
                _response(200, [{"created_at": today.isoformat() + "T12:00:00Z"}]),
                _response(200, [{"author": {"login": "a"}}]),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10)

        assert stats.records_written >= 1
        assert stats.cursor["succeeded"] == 1
        assert stats.cursor["failed"] == 0

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_idempotent_repeated_execution(
        self, mock_client, mock_settings, mock_tracked
    ):
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo()
        session.repos = [repo]

        stats1 = RunStats()
        tracked_ctx = _patch_for_sync(session, stats1, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                _response(200, _repo_payload(), {"etag": '"v1"'}),
                _response(200, [{"week": today_ts, "total": 7, "days": [1] * 7}]),
                _response(200, []),
                _response(200, []),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats1, budget=10)
        first_count = stats1.records_written

        stats2 = RunStats()
        tracked_ctx2 = _patch_for_sync(session, stats2, None)
        mock_tracked.return_value = tracked_ctx2

        http2 = FakeHTTPClient(
            [
                _response(200, _repo_payload(), {"etag": '"v1"'}),
                _response(200, [{"week": today_ts, "total": 7, "days": [1] * 7}]),
                _response(200, []),
                _response(200, []),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http2)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats2, budget=10)
        assert stats2.records_written <= first_count

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_partial_failure_isolation(
        self, mock_client, mock_settings, mock_tracked
    ):
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo1 = _make_repo(id=1, full_name="acme/good")
        repo2 = _make_repo(id=2, full_name="acme/bad")
        session.repos = [repo1, repo2]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                _response(200, _repo_payload(), {"etag": '"v1"'}),
                _response(200, [{"week": today_ts, "total": 5, "days": [1] * 7}]),
                _response(200, []),
                _response(200, []),
                _response(502),
                _response(502),
                _response(502),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10)

        assert stats.cursor["succeeded"] == 1
        assert stats.cursor["failed"] == 1

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_rate_limiting_stops_sync(
        self, mock_client, mock_settings, mock_tracked
    ):
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo()
        session.repos = [repo]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        http = FakeHTTPClient(
            [_response(429, {"message": "rate limit"}, {"x-ratelimit-remaining": "0"})]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(QuotaExhausted):
            sync_metrics(stats, budget=10)

        assert stats.cursor["succeeded"] == 0
        assert stats.cursor["attempted"] == 1

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_transient_retry_succeeds(
        self, mock_client, mock_settings, mock_tracked
    ):
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo()
        session.repos = [repo]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                _response(502),
                _response(200, _repo_payload(), {"etag": '"v1"'}),
                _response(200, [{"week": today_ts, "total": 10, "days": [1] * 7}]),
                _response(200, []),
                _response(200, []),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10)

        assert stats.cursor["succeeded"] == 1
        assert stats.cursor["failed"] == 0

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_etag_304_no_duplicate_writes(
        self, mock_client, mock_settings, mock_tracked
    ):
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo(etag='"v1"')
        session.repos = [repo]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                _response(304),
                _response(200, [{"week": today_ts, "total": 5, "days": [1] * 7}]),
                _response(200, []),
                _response(200, []),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10)

        assert stats.api_calls_saved >= 1
        assert stats.cursor["succeeded"] == 1

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_empty_no_activity_repository(
        self, mock_client, mock_settings, mock_tracked
    ):
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo(stars=0, forks=0, watchers=0, open_issues=0)
        session.repos = [repo]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        http = FakeHTTPClient(
            [
                _response(
                    200,
                    _repo_payload(
                        stargazers_count=0,
                        forks_count=0,
                        subscribers_count=0,
                        open_issues_count=0,
                    ),
                    {"etag": '"v1"'},
                ),
                _response(200, []),
                _response(200, []),
                _response(200, []),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10)
        assert stats.cursor["succeeded"] == 1

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_historical_backfill_creates_rows(
        self, mock_client, mock_settings, mock_tracked
    ):
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo()
        session.repos = [repo]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                _response(200, _repo_payload(), {"etag": '"v1"'}),
                _response(200, [{"week": today_ts, "total": 49, "days": [7] * 7}]),
                _response(
                    200,
                    [
                        {
                            "created_at": (today - timedelta(days=3)).isoformat()
                            + "T12:00:00Z"
                        },
                        {"created_at": today.isoformat() + "T12:00:00Z"},
                    ],
                ),
                _response(200, [{"author": {"login": "a"}}]),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10, backfill_days=7)

        created = [r for r in session.metrics if isinstance(r, RepositoryMetricDaily)]
        assert len(created) == 8

        backfilled = [r for r in created if r.is_backfilled]
        today_rows = [r for r in created if not r.is_backfilled]
        assert len(backfilled) == 7
        assert len(today_rows) == 1

        today_row = today_rows[0]
        assert today_row.stars == 100
        assert today_row.forks == 20
        assert today_row.releases == 1
        assert today_row.contributors_active == 1

        for bf in backfilled:
            assert bf.stars is None
            assert bf.forks is None
            assert bf.watchers is None
            assert bf.open_issues is None

    # -- data-quality tests ------------------------------------------------

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_backfilled_level_fields_are_null(
        self, mock_client, mock_settings, mock_tracked
    ):
        """Backfilled rows must have NULL stars/forks/watchers/open_issues."""
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo()
        session.repos = [repo]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                _response(200, _repo_payload(), {"etag": '"v1"'}),
                _response(200, [{"week": today_ts, "total": 7, "days": [1] * 7}]),
                _response(200, []),
                _response(200, [{"author": {"login": "a"}}]),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10, backfill_days=7)

        rows = [r for r in session.metrics if isinstance(r, RepositoryMetricDaily)]
        backfilled = [r for r in rows if r.is_backfilled]
        assert len(backfilled) == 7
        for bf in backfilled:
            assert bf.stars is None, "backfilled stars must be NULL, not 0"
            assert bf.forks is None, "backfilled forks must be NULL, not 0"
            assert bf.watchers is None, "backfilled watchers must be NULL, not 0"
            assert bf.open_issues is None, "backfilled open_issues must be NULL, not 0"

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_today_can_have_zero_stars(
        self, mock_client, mock_settings, mock_tracked
    ):
        """A live snapshot with zero stars is legitimate (empty repo)."""
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo(stars=0)
        session.repos = [repo]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        http = FakeHTTPClient(
            [
                _response(200, _repo_payload(stargazers_count=0), {"etag": '"v1"'}),
                _response(200, []),
                _response(200, []),
                _response(200, []),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10, backfill_days=1)

        rows = [r for r in session.metrics if isinstance(r, RepositoryMetricDaily)]
        today_row = next(r for r in rows if not r.is_backfilled)
        assert today_row.stars == 0

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_no_delta_across_backfilled_boundary(
        self, mock_client, mock_settings, mock_tracked
    ):
        """Delta is not computed when the previous day is backfilled (NULL stars)."""
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo(stars=100)
        yesterday = date.today() - timedelta(days=1)
        # Simulate a backfilled yesterday row (stars=NULL)
        prev_metric = MagicMock(spec=RepositoryMetricDaily)
        prev_metric.repository_id = repo.id
        prev_metric.day = yesterday
        prev_metric.stars = None  # backfilled → NULL
        prev_metric.forks = None  # backfilled → NULL
        prev_metric.is_backfilled = True

        session.repos = [repo]
        session.metrics = [prev_metric]

        def fake_scalar(stmt):
            today = date.today()
            for r in session.metrics:
                if isinstance(r, RepositoryMetricDaily) and r.day == today:
                    return r
            return None

        session.scalar = fake_scalar

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        http = FakeHTTPClient(
            [
                _response(
                    200, _repo_payload(stargazers_count=100), {"etag": '"v2"'}
                ),
                _response(200, []),
                _response(200, []),
                _response(200, []),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10)

        today_row = None
        for r in session.metrics:
            if isinstance(r, RepositoryMetricDaily) and r.day == today:
                today_row = r
                break

        assert today_row is not None
        assert today_row.stars_delta is None, (
            "delta must not be computed across a backfilled boundary"
        )
        assert today_row.forks_delta is None

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_budget_limits_repositories(
        self, mock_client, mock_settings, mock_tracked
    ):
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repos = [_make_repo(id=i, full_name=f"acme/repo{i}") for i in range(5)]
        session.repos = repos

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        responses = []
        for i in range(3):
            responses.extend(
                [
                    _response(200, _repo_payload(), {"etag": f'"v{i}"'}),
                    _response(200, [{"week": today_ts, "total": 7, "days": [1] * 7}]),
                    _response(200, []),
                    _response(200, []),
                ]
            )
        http = FakeHTTPClient(responses)
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=3)
        assert stats.cursor["attempted"] <= 3

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_delta_computed_for_today(
        self, mock_client, mock_settings, mock_tracked
    ):
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo(stars=105)
        yesterday = date.today() - timedelta(days=1)
        prev_metric = _make_metric(day=yesterday, stars=100, forks=20)

        session.repos = [repo]
        session.metrics = [prev_metric]

        def fake_scalar(stmt):
            today = date.today()
            for r in session.metrics:
                if isinstance(r, RepositoryMetricDaily) and r.day == today:
                    return r
            return None

        session.scalar = fake_scalar

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                _response(
                    200, _repo_payload(stargazers_count=105), {"etag": '"v2"'}
                ),
                _response(
                    200,
                    [{"week": today_ts, "total": 10, "days": [1, 2, 1, 1, 2, 2, 1]}],
                ),
                _response(200, []),
                _response(200, [{"author": {"login": "a"}}]),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10)

        today_row = None
        for r in session.metrics:
            if isinstance(r, RepositoryMetricDaily) and r.day == today:
                today_row = r
                break

        assert today_row is not None
        assert today_row.stars == 105
        assert today_row.stars_delta == 5

    # -- regression: 304 repo fallback (issue: NULL snapshot levels) -----------

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_304_repo_fallback_to_table_levels(
        self, mock_client, mock_settings, mock_tracked
    ):
        """When fetch_repo returns 304, today's row must use repo table levels.

        Regression: 76/144 repos had NULL stars/forks/watchers/open_issues in
        today's row because _build_daily_metrics created MetricResult with all
        NULL levels when repo_data was None (304), and upsert_daily_metric
        skipped the update.  The fix falls back to repo.stars/forks/etc.
        """
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        # Repo has stars from a prior resolve/sync, but no etag stored yet
        # (or etag doesn't match → GitHub returns 200 on first sync).
        # After first sync, etag is stored. On second sync, GitHub returns 304.
        repo = _make_repo(stars=5000, forks=400, watchers=120, open_issues=80)
        session.repos = [repo]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                # fetch_repo → 304 Not Modified (repo unchanged)
                _response(304),
                # fetch_commit_activity → 200 with data
                _response(200, [{"week": today_ts, "total": 21, "days": [3] * 7}]),
                # fetch_releases → 200 empty
                _response(200, []),
                # fetch_contributors → 200 with data
                _response(200, [{"author": {"login": "a"}}]),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10, backfill_days=1)

        rows = [r for r in session.metrics if isinstance(r, RepositoryMetricDaily)]
        today_row = next((r for r in rows if not r.is_backfilled), None)
        assert today_row is not None
        # Must fall back to repo table values, NOT be None
        assert today_row.stars == 5000, (
            "304 on fetch_repo must not cause NULL stars; "
            "should fall back to repo table"
        )
        assert today_row.forks == 400
        assert today_row.watchers == 120
        assert today_row.open_issues == 80

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_304_repo_update_existing_null_stars_row(
        self, mock_client, mock_settings, mock_tracked
    ):
        """UPDATE path: today's row exists with NULL stars → updated via repo fallback.

        Regression: if a previous run created today's row with NULL levels
        (because repo_data was None), a subsequent run with 304 must UPDATE
        the existing row using repo table fallback values.
        """
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        repo = _make_repo(stars=7500, forks=600, watchers=90, open_issues=50)
        session.repos = [repo]

        # Pre-populate today's row with NULL levels (simulates previous buggy run)
        existing_today = MagicMock(spec=RepositoryMetricDaily)
        existing_today.repository_id = repo.id
        existing_today.day = date.today()
        existing_today.stars = None
        existing_today.forks = None
        existing_today.watchers = None
        existing_today.open_issues = None
        existing_today.commits = None
        existing_today.releases = None
        existing_today.contributors_active = None
        existing_today.is_backfilled = False
        session.metrics = [existing_today]

        def fake_scalar(stmt):
            for r in session.metrics:
                if (
                    isinstance(r, RepositoryMetricDaily)
                    and r.repository_id == repo.id
                    and r.day == date.today()
                ):
                    return r
            return None

        session.scalar = fake_scalar

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                _response(304),
                _response(200, [{"week": today_ts, "total": 14, "days": [2] * 7}]),
                _response(200, []),
                _response(200, [{"author": {"login": "a"}}]),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10)

        # The existing row should be updated, NOT a new row created
        assert existing_today.stars == 7500, (
            "UPDATE path must set stars from repo table fallback"
        )
        assert existing_today.forks == 600
        assert existing_today.watchers == 90
        assert existing_today.open_issues == 50

    @patch("workers.github.sync_metrics.tracked_run")
    @patch("workers.github.sync_metrics.get_settings")
    @patch("workers.github.sync_metrics.httpx.Client")
    def test_200_overwrites_fallback_values(
        self, mock_client, mock_settings, mock_tracked
    ):
        """When fetch_repo returns 200, fresh API data must override repo table.

        Ensures that a successful fetch always uses the latest API values,
        not stale repo table values.
        """
        mock_settings.return_value = MagicMock(github_token="test-token")

        session = FakeSession()
        # Repo table has old values
        repo = _make_repo(stars=100, forks=20, watchers=5, open_issues=10)
        session.repos = [repo]

        stats = RunStats()
        tracked_ctx = _patch_for_sync(session, stats, None)
        mock_tracked.return_value = tracked_ctx

        today = date.today()
        today_ts = _day_to_week_ts(today)
        http = FakeHTTPClient(
            [
                # fetch_repo → 200 with NEWER values
                _response(
                    200,
                    _repo_payload(
                        stargazers_count=500, forks_count=50,
                        subscribers_count=15, open_issues_count=25,
                    ),
                    {"etag": '"v2"'},
                ),
                _response(200, [{"week": today_ts, "total": 7, "days": [1] * 7}]),
                _response(200, []),
                _response(200, []),
            ]
        )
        mock_client.return_value.__enter__ = MagicMock(return_value=http)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        sync_metrics(stats, budget=10, backfill_days=1)

        rows = [r for r in session.metrics if isinstance(r, RepositoryMetricDaily)]
        today_row = next((r for r in rows if not r.is_backfilled), None)
        assert today_row is not None
        # Must use fresh API data, not repo table
        assert today_row.stars == 500
        assert today_row.forks == 50
        assert today_row.watchers == 15
        assert today_row.open_issues == 25
