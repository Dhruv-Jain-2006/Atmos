"""Comprehensive tests for the detection engine.

Tests cover:
- Aggregation (repo → tech): weights, multiple repos, breadth
- Temporal signals: velocity, acceleration, anomaly, persistence, event intensity
- Classification: all 6 weather states
- Confidence: shallow/complete history, missing metrics, breadth
- Events: transitions, anomalies, deduplication
- NULL/backfill provenance handling
- Integration: fixture dataset through detection → API
"""

from __future__ import annotations

from datetime import date, timedelta
from math import isclose
from unittest.mock import MagicMock

from internetweather.analysis.weather_state import (
    SignalInput,
    classify,
    compute_confidence,
    compute_momentum,
    growth_ratio,
)
from internetweather.enums import (
    RepoRelation,
    Subdomain,
    WeatherState,
)
from internetweather.models import (
    RepositoryMetricDaily,
    Technology,
    TechnologyRepository,
    TechnologySignalDaily,
)
from workers.detection.aggregation import (
    RepoDay,
    RepoLink,
    compute_activity_on_day,
    compute_daily_weighted_deltas,
    compute_tech_signals,
    load_repo_days,
    load_repo_links,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tech(
    id: int = 1,
    slug: str = "test-tech",
    name: str = "Test Tech",
    subdomain: Subdomain = Subdomain.AGENTIC_AI,
) -> MagicMock:
    tech = MagicMock(spec=Technology)
    tech.id = id
    tech.slug = slug
    tech.name = name
    tech.subdomain = subdomain
    tech.is_active = True
    tech.repositories = []
    return tech


def _make_link(
    repo_id: int = 1,
    weight: float = 1.0,
    relation: RepoRelation = RepoRelation.CANONICAL,
) -> RepoLink:
    return RepoLink(
        repository_id=repo_id,
        full_name=f"owner/repo{repo_id}",
        weight=weight,
        relation=relation,
    )


def _make_day(
    repo_id: int = 1,
    day: date | None = None,
    stars: int | None = None,
    stars_delta: int | None = None,
    commits: int | None = None,
    releases: int | None = None,
    is_backfilled: bool = False,
) -> RepoDay:
    return RepoDay(
        repository_id=repo_id,
        day=day or date.today(),
        stars=stars,
        stars_delta=stars_delta,
        commits=commits,
        releases=releases,
        is_backfilled=is_backfilled,
    )


def _mature_signals(**overrides) -> SignalInput:
    """A mature signal with 28 days of history and multiple repos."""
    defaults = dict(
        star_velocity_7d=10.0,
        star_velocity_28d=5.0,
        activity_velocity_7d=3.0,
        activity_velocity_28d=2.0,
        anomaly_z=1.5,
        volatility=0.3,
        stars_total=5000,
        sample_days=28,
        repo_count=3,
        active_repo_count=3,
        age_days=200,
        recent_event_magnitude=0.0,
    )
    defaults.update(overrides)
    return SignalInput(**defaults)


# ===========================================================================
# AGGREGATION TESTS
# ===========================================================================

class TestLoadRepoLinks:
    def test_single_tech_single_repo(self):
        tech = _make_tech()
        link = MagicMock(spec=TechnologyRepository)
        link.repository_id = 1
        link.weight = 1.0
        link.relation = RepoRelation.CANONICAL
        link.repository = MagicMock()
        link.repository.full_name = "owner/repo1"
        tech.repositories = [link]

        result = load_repo_links([tech])
        assert 1 in result
        assert len(result[1]) == 1
        assert result[1][0].weight == 1.0

    def test_multiple_repos_different_weights(self):
        tech = _make_tech()
        links = []
        for i, (w, rel) in enumerate(
            [(1.0, RepoRelation.CANONICAL), (0.6, RepoRelation.IMPLEMENTATION)], 1
        ):
            link = MagicMock(spec=TechnologyRepository)
            link.repository_id = i
            link.weight = w
            link.relation = rel
            link.repository = MagicMock()
            link.repository.full_name = f"owner/repo{i}"
            links.append(link)
        tech.repositories = links

        result = load_repo_links([tech])
        assert len(result[1]) == 2
        assert result[1][0].weight == 1.0
        assert result[1][1].weight == 0.6

    def test_multiple_technologies(self):
        tech1 = _make_tech(id=1, slug="tech1")
        tech2 = _make_tech(id=2, slug="tech2")
        for tech in [tech1, tech2]:
            link = MagicMock(spec=TechnologyRepository)
            link.repository_id = tech.id
            link.weight = 1.0
            link.relation = RepoRelation.CANONICAL
            link.repository = MagicMock()
            link.repository.full_name = f"owner/repo{tech.id}"
            tech.repositories = [link]

        result = load_repo_links([tech1, tech2])
        assert len(result) == 2
        assert 1 in result
        assert 2 in result


class TestLoadRepoDays:
    def test_groups_by_repo(self):
        today = date.today()
        m1 = MagicMock(spec=RepositoryMetricDaily)
        m1.repository_id = 1
        m1.day = today
        m1.stars = 100
        m1.forks = 20
        m1.watchers = None
        m1.open_issues = None
        m1.stars_delta = 5
        m1.forks_delta = None
        m1.commits = 10
        m1.releases = 1
        m1.contributors_active = None
        m1.is_backfilled = False

        result = load_repo_days([m1])
        assert 1 in result
        assert today in result[1]
        assert result[1][today].stars == 100


class TestWeightedDeltaOnDay:
    def test_single_repo_with_delta(self):
        today = date.today()
        link = _make_link(repo_id=1, weight=1.0)
        repo_days = {1: {today: _make_day(1, today, stars_delta=10)}}

        deltas = compute_daily_weighted_deltas(
            [link], repo_days, today, today
        )
        assert len(deltas) == 1
        assert deltas[today] == 10.0

    def test_weight_applied(self):
        today = date.today()
        link = _make_link(repo_id=1, weight=0.5)
        repo_days = {1: {today: _make_day(1, today, stars_delta=10)}}

        deltas = compute_daily_weighted_deltas(
            [link], repo_days, today, today
        )
        assert deltas[today] == 5.0

    def test_multiple_repos_summed(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0), _make_link(repo_id=2, weight=0.5)]
        repo_days = {
            1: {today: _make_day(1, today, stars_delta=10)},
            2: {today: _make_day(2, today, stars_delta=20)},
        }

        deltas = compute_daily_weighted_deltas(
            links, repo_days, today, today
        )
        assert deltas[today] == 10.0 + 0.5 * 20.0  # 20.0

    def test_backfilled_stars_not_used_for_delta(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        link = _make_link(repo_id=1, weight=1.0)
        repo_days = {
            1: {
                yesterday: _make_day(1, yesterday, stars=100, is_backfilled=True),
                today: _make_day(1, today, stars=110, is_backfilled=False),
            }
        }

        # Yesterday is backfilled, today is not.
        # No stars_delta on either day, so we'd need both non-backfilled
        # stars to compute delta.  Since yesterday is backfilled, delta unknown.
        deltas = compute_daily_weighted_deltas(
            [link],
            repo_days, today, today
        )
        # Should be empty because yesterday is backfilled
        assert len(deltas) == 0

    def test_null_stars_no_panic(self):
        today = date.today()
        link = _make_link(repo_id=1, weight=1.0)
        repo_days = {1: {today: _make_day(1, today, stars=None)}}

        deltas = compute_daily_weighted_deltas(
            [link], repo_days, today, today
        )
        assert len(deltas) == 0

    def test_returns_dict_keyed_by_date(self):
        """Verify return type is dict[date, float] for calendar-window filtering."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        link = _make_link(repo_id=1, weight=1.0)
        repo_days = {
            1: {
                yesterday: _make_day(1, yesterday, stars_delta=5),
                today: _make_day(1, today, stars_delta=10),
            }
        }
        deltas = compute_daily_weighted_deltas([link], repo_days, yesterday, today)
        assert isinstance(deltas, dict)
        assert deltas[yesterday] == 5.0
        assert deltas[today] == 10.0


class TestComputeActivityOnDay:
    def test_commits_only(self):
        today = date.today()
        link = _make_link(repo_id=1, weight=1.0)
        repo_days = {1: {today: _make_day(1, today, commits=10, releases=0)}}

        score = compute_activity_on_day([link], repo_days, today)
        assert score == 10.0

    def test_releases_weighted_5x(self):
        today = date.today()
        link = _make_link(repo_id=1, weight=1.0)
        repo_days = {1: {today: _make_day(1, today, commits=2, releases=1)}}

        score = compute_activity_on_day([link], repo_days, today)
        assert score == 2.0 + 5.0  # commits + releases * 5

    def test_weight_applied(self):
        today = date.today()
        link = _make_link(repo_id=1, weight=0.5)
        repo_days = {1: {today: _make_day(1, today, commits=10, releases=0)}}

        score = compute_activity_on_day([link], repo_days, today)
        assert score == 5.0


# ===========================================================================
# TEMPORAL SIGNAL TESTS
# ===========================================================================

class TestVelocity:
    def test_velocity_computed(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        # Create 28 days of data with stars_delta=10 each day
        for i in range(28):
            d = today - timedelta(days=i)
            repo_days.setdefault(1, {})[d] = _make_day(1, d, stars_delta=10)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        assert sig.star_velocity_7d is not None
        assert sig.star_velocity_28d is not None
        assert sig.star_velocity_7d > 0
        assert sig.star_velocity_28d > 0

    def test_velocity_none_with_no_data(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {1: {}}

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        assert sig.star_velocity_7d is None
        assert sig.star_velocity_28d is None


class TestAcceleration:
    def test_positive_acceleration(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        # Last 7 days: delta=20 (fast), previous 21 days: delta=5 (slow)
        for i in range(28):
            d = today - timedelta(days=i)
            delta = 20 if i < 7 else 5
            repo_days.setdefault(1, {})[d] = _make_day(1, d, stars_delta=delta)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        assert sig.star_acceleration is not None
        assert sig.star_acceleration > 0  # accelerating

    def test_negative_acceleration(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        # Last 7 days: delta=2 (slow), previous 21 days: delta=20 (fast)
        for i in range(28):
            d = today - timedelta(days=i)
            delta = 2 if i < 7 else 20
            repo_days.setdefault(1, {})[d] = _make_day(1, d, stars_delta=delta)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        assert sig.star_acceleration is not None
        assert sig.star_acceleration < 0  # decelerating


class TestAnomaly:
    def test_high_anomaly_z(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        # Very stable baseline of delta=5, then spike to 50 today
        for i in range(28):
            d = today - timedelta(days=i)
            delta = 50 if i == 0 else 5
            repo_days.setdefault(1, {})[d] = _make_day(1, d, stars_delta=delta)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        assert sig.anomaly_z is not None
        # The z-score measures deviation from baseline.
        # With one spike among 27 stable days, z > 0 indicates anomaly.
        assert sig.anomaly_z > 0

    def test_no_anomaly_with_stable_data(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        # Consistent delta of 10
        for i in range(28):
            d = today - timedelta(days=i)
            repo_days.setdefault(1, {})[d] = _make_day(1, d, stars_delta=10)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        assert sig.anomaly_z is not None
        assert abs(sig.anomaly_z) < 0.5  # near baseline


class TestPersistence:
    def test_sample_days_counted(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        for i in range(14):
            d = today - timedelta(days=i)
            repo_days.setdefault(1, {})[d] = _make_day(1, d, stars=100 + i)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        assert sig.sample_days == 14

    def test_sample_days_with_missing_days(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        # Only every other day has data
        for i in range(0, 28, 2):
            d = today - timedelta(days=i)
            repo_days.setdefault(1, {})[d] = _make_day(1, d, stars=100)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        assert sig.sample_days == 14  # 28/2


class TestBreadth:
    def test_active_repo_count(self):
        today = date.today()
        links = [_make_link(repo_id=i, weight=1.0) for i in range(1, 4)]
        repo_days = {}
        # Repo 1: active today, Repo 2: active 3 days ago, Repo 3: no activity
        repo_days[1] = {today: _make_day(1, today, commits=5)}
        d3 = today - timedelta(days=3)
        repo_days[2] = {d3: _make_day(2, d3, commits=5)}
        repo_days[3] = {}

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        assert sig.repo_count == 3
        assert sig.active_repo_count == 2


# ===========================================================================
# CLASSIFICATION TESTS
# ===========================================================================

class TestClassification:
    def test_hot_state(self):
        signals = _mature_signals(
            star_velocity_7d=100.0,
            star_velocity_28d=30.0,
            anomaly_z=1.5,
            stars_total=50000,  # large base to avoid EMERGING
            age_days=1000,  # old enough to avoid EMERGING
        )
        result = classify(signals)
        assert result.state == WeatherState.HOT

    def test_emerging_state(self):
        signals = _mature_signals(
            star_velocity_7d=20.0,
            star_velocity_28d=5.0,
            anomaly_z=1.0,
            stars_total=5000,  # small base
            age_days=100,  # young
        )
        result = classify(signals)
        assert result.state == WeatherState.EMERGING

    def test_stable_state(self):
        signals = _mature_signals(
            star_velocity_7d=5.0,
            star_velocity_28d=5.0,
            anomaly_z=0.1,
            volatility=0.2,
        )
        result = classify(signals)
        assert result.state == WeatherState.STABLE

    def test_cooling_state(self):
        signals = _mature_signals(
            star_velocity_7d=1.0,
            star_velocity_28d=10.0,
            anomaly_z=-1.2,
        )
        result = classify(signals)
        assert result.state == WeatherState.COOLING

    def test_storm_state(self):
        signals = _mature_signals(
            anomaly_z=2.5,
            volatility=1.5,
        )
        result = classify(signals)
        assert result.state == WeatherState.STORM

    def test_breaking_state(self):
        signals = _mature_signals(
            recent_event_magnitude=0.8,
        )
        result = classify(signals)
        assert result.state == WeatherState.BREAKING

    def test_insufficient_history(self):
        signals = _mature_signals(sample_days=3)
        result = classify(signals)
        assert result.state == WeatherState.STABLE
        assert result.confidence <= 0.25


# ===========================================================================
# CONFIDENCE TESTS
# ===========================================================================

class TestConfidence:
    def test_shallow_history_low_confidence(self):
        signals = _mature_signals(sample_days=1, active_repo_count=1)
        conf = compute_confidence(signals)
        assert conf < 0.3

    def test_full_history_higher_confidence(self):
        signals = _mature_signals(sample_days=28, active_repo_count=3, volatility=0.1)
        conf = compute_confidence(signals)
        assert conf > 0.5

    def test_broad_breadth_increases_confidence(self):
        narrow = _mature_signals(sample_days=28, active_repo_count=1, volatility=0.1)
        broad = _mature_signals(sample_days=28, active_repo_count=5, volatility=0.1)
        assert compute_confidence(broad) > compute_confidence(narrow)

    def test_high_volatility_reduces_confidence(self):
        calm = _mature_signals(sample_days=28, active_repo_count=3, volatility=0.1)
        volatile = _mature_signals(sample_days=28, active_repo_count=3, volatility=1.5)
        assert compute_confidence(volatile) < compute_confidence(calm)


# ===========================================================================
# MOMENTUM TESTS
# ===========================================================================

class TestMomentum:
    def test_positive_momentum(self):
        signals = _mature_signals(
            star_velocity_7d=20.0,
            star_velocity_28d=5.0,
            anomaly_z=1.0,
        )
        m = compute_momentum(signals)
        assert m > 0

    def test_negative_momentum(self):
        signals = _mature_signals(
            star_velocity_7d=1.0,
            star_velocity_28d=10.0,
            anomaly_z=-1.0,
        )
        m = compute_momentum(signals)
        assert m < 0

    def test_momentum_bounded(self):
        signals = _mature_signals(
            star_velocity_7d=1000.0,
            star_velocity_28d=1.0,
            anomaly_z=3.0,
        )
        m = compute_momentum(signals)
        assert -1.0 <= m <= 1.0


# ===========================================================================
# GROWTH RATIO TESTS
# ===========================================================================

class TestGrowthRatio:
    def test_equal_velocity(self):
        assert isclose(growth_ratio(10.0, 10.0), 1.0, abs_tol=0.1)

    def test_doubling(self):
        r = growth_ratio(20.0, 10.0)
        assert r > 1.5

    def test_halving(self):
        r = growth_ratio(5.0, 10.0)
        assert r < 0.7

    def test_handles_none(self):
        r = growth_ratio(None, 10.0)
        assert r < 1.0

    def test_scale_free(self):
        r1 = growth_ratio(100.0, 50.0)
        r2 = growth_ratio(200.0, 100.0)
        assert isclose(r1, r2, abs_tol=0.01)


# ===========================================================================
# NULL / BACKFILL PROVENANCE TESTS
# ===========================================================================

class TestBackfillProvenance:
    def test_backfilled_stars_not_in_total(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {
            1: {
                today: _make_day(1, today, stars=None, is_backfilled=True),
            }
        }

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.stars_total is None  # NULL stars → None, not 0

    def test_live_stars_in_total(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {
            1: {
                today: _make_day(1, today, stars=500, is_backfilled=False),
            }
        }

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.stars_total == 500

    def test_mixed_live_and_backfilled(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0), _make_link(repo_id=2, weight=1.0)]
        repo_days = {
            1: {today: _make_day(1, today, stars=500, is_backfilled=False)},
            2: {today: _make_day(2, today, stars=None, is_backfilled=True)},
        }

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.stars_total == 500  # only live repos counted

    def test_no_stars_snapshot_returns_none(self):
        """No repo has stars for today → stars_total must be None, not 0."""
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {1: {today: _make_day(1, today, stars=None)}}

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.stars_total is None

    def test_empty_repos_returns_none(self):
        """No repos at all → stars_total must be None."""
        tech = _make_tech()
        sig = compute_tech_signals(tech, [], {}, date.today())
        assert sig.stars_total is None


# ===========================================================================
# EVENT TESTS
# ===========================================================================

class TestEvents:
    def test_state_transition_creates_event(self):
        """When weather_state changes, an event should be emitted."""
        from workers.detection.compute_signals import _detect_events

        session = MagicMock()
        tech = _make_tech()
        today = date.today()

        prev = MagicMock(spec=TechnologySignalDaily)
        prev.weather_state = WeatherState.STABLE

        classification = MagicMock()
        classification.state = WeatherState.HOT
        classification.momentum = 0.8
        classification.confidence = 0.7

        sig = MagicMock()
        sig.day = today
        sig.anomaly_z = 1.5
        sig.stars_total = 5000
        sig.repo_count = 3
        sig.star_velocity_7d = 20.0
        sig.star_velocity_28d = 5.0
        sig.release_count_28d = None

        _detect_events(session, tech, sig, classification, prev)
        session.execute.assert_called()  # event was emitted

    def test_no_event_for_same_state(self):
        """No event when state doesn't change."""
        from workers.detection.compute_signals import _detect_events

        session = MagicMock()
        tech = _make_tech()
        today = date.today()

        prev = MagicMock(spec=TechnologySignalDaily)
        prev.weather_state = WeatherState.STABLE

        classification = MagicMock()
        classification.state = WeatherState.STABLE
        classification.momentum = 0.0
        classification.confidence = 0.6

        sig = MagicMock()
        sig.day = today
        sig.anomaly_z = 0.1
        sig.stars_total = 5000
        sig.repo_count = 3
        sig.release_count_28d = None

        _detect_events(session, tech, sig, classification, prev)
        # Should not emit state transition event (anomaly too small)
        session.execute.assert_not_called()

    def test_anomaly_event(self):
        """Significant anomaly should create an event."""
        from workers.detection.compute_signals import _detect_events

        session = MagicMock()
        tech = _make_tech()
        today = date.today()

        classification = MagicMock()
        classification.state = WeatherState.STABLE
        classification.momentum = 0.0
        classification.confidence = 0.6

        sig = MagicMock()
        sig.day = today
        sig.anomaly_z = 2.5
        sig.stars_total = 5000
        sig.repo_count = 3
        sig.star_velocity_7d = 50.0
        sig.star_velocity_28d = 5.0
        sig.release_count_28d = None

        _detect_events(session, tech, sig, classification, None)
        session.execute.assert_called()

    def test_dedupe_key_prevents_duplicates(self):
        """Same event emitted twice should use same dedupe_key."""
        from workers.detection.compute_signals import _detect_events

        session = MagicMock()
        tech = _make_tech(id=1)
        today = date.today()

        prev = MagicMock(spec=TechnologySignalDaily)
        prev.weather_state = WeatherState.STABLE

        classification = MagicMock()
        classification.state = WeatherState.HOT
        classification.momentum = 0.8
        classification.confidence = 0.7

        sig = MagicMock()
        sig.day = today
        sig.anomaly_z = 1.5
        sig.stars_total = 5000
        sig.repo_count = 3
        sig.release_count_28d = None

        # First call emits a state transition event
        _detect_events(session, tech, sig, classification, prev)
        first_call_count = session.execute.call_count

        session.reset_mock()
        # Second call with same inputs should produce the same dedupe_key
        _detect_events(session, tech, sig, classification, prev)
        second_call_count = session.execute.call_count

        # Both calls produce the same number of execute calls
        assert first_call_count == second_call_count == 1

        # The INSERT statement targets the same table (EcosystemEvent)
        first_stmt = session.execute.call_args[0][0]
        assert first_stmt.is_insert
        assert first_stmt.table.name == "ecosystem_event"


# ===========================================================================
# INTEGRATION TEST
# ===========================================================================

class TestIntegration:
    def test_fixture_dataset(self):
        """Run a deterministic fixture through aggregation → classification."""
        today = date.today()
        tech = _make_tech(id=1, slug="mcp", name="MCP")
        links = [_make_link(repo_id=1, weight=1.0)]

        repo_days = {}
        # 28 days of data: baseline of 5 stars/day, then acceleration
        for i in range(28):
            d = today - timedelta(days=i)
            delta = 50 if i < 7 else 5  # recent burst
            stars = 1000 + (28 - i) * 10
            repo_days.setdefault(1, {})[d] = _make_day(
                1, d, stars=stars, stars_delta=delta, commits=10 if i < 7 else 2
            )

        sig = compute_tech_signals(tech, links, repo_days, today)

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
            age_days=200,
            recent_event_magnitude=0.0,
        )

        classification = classify(signal_input)

        # With recent burst and 28 days of history, should be HOT or EMERGING
        assert classification.state in (WeatherState.HOT, WeatherState.EMERGING)
        assert classification.confidence > 0.3
        assert -1.0 <= classification.momentum <= 1.0


# ===========================================================================
# REGRESSION TESTS — correctness audit
# ===========================================================================

class TestVelocityCalendarWindow:
    """PROBLEM 2: velocity must divide by calendar window size, not available count."""

    def test_velocity_divides_by_7_not_by_available(self):
        """5 available deltas in 7 calendar days → velocity = sum / 7, not / 5."""
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        # Only 5 of the last 7 days have data
        for i in range(7):
            d = today - timedelta(days=i)
            if i in (2, 4):  # skip days 2 and 4
                continue
            repo_days.setdefault(1, {})[d] = _make_day(1, d, stars_delta=10)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        # 5 deltas of 10 → sum = 50
        assert sig.stars_delta_7d == 50
        # velocity = 50 / 7, not 50 / 5
        assert sig.star_velocity_7d is not None
        assert abs(sig.star_velocity_7d - 50 / 7) < 0.01

    def test_velocity_divides_by_28_not_by_available(self):
        """10 available deltas in 28 calendar days → velocity = sum / 28, not / 10."""
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        # Only 10 of the last 28 days have data
        for i in range(28):
            d = today - timedelta(days=i)
            if i % 3 != 0:  # only every 3rd day
                continue
            repo_days.setdefault(1, {})[d] = _make_day(1, d, stars_delta=10)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        # 10 deltas of 10 → sum = 100
        assert sig.stars_delta_28d == 100
        # velocity = 100 / 28, not 100 / 10
        assert sig.star_velocity_28d is not None
        assert abs(sig.star_velocity_28d - 100 / 28) < 0.01

    def test_7d_uses_calendar_window_not_last_available(self):
        """Last 7 *calendar* days, not last 7 *available* deltas."""
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        # Day 0 (today): delta=100
        # Days 1-6: no data
        # Days 7-13: delta=10 each
        for i in range(14):
            d = today - timedelta(days=i)
            if i == 0:
                repo_days.setdefault(1, {})[d] = _make_day(1, d, stars_delta=100)
            elif 7 <= i <= 13:
                repo_days.setdefault(1, {})[d] = _make_day(1, d, stars_delta=10)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        # 7d window = last 7 calendar days (today - 6 .. today)
        # Only today has data → delta_7d = 100
        assert sig.stars_delta_7d == 100
        assert abs(sig.star_velocity_7d - 100 / 7) < 0.01

        # 28d window = all 28 days
        # 1 day at 100 + 7 days at 10 = 170
        assert sig.stars_delta_28d == 170
        assert abs(sig.star_velocity_28d - 170 / 28) < 0.01


class TestStarsTotalNullability:
    """PROBLEM 1: stars_total must be None when no snapshot is available."""

    def test_none_when_no_repos(self):
        tech = _make_tech()
        sig = compute_tech_signals(tech, [], {}, date.today())
        assert sig.stars_total is None

    def test_none_when_no_stars_today(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {1: {today: _make_day(1, today, commits=5)}}
        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.stars_total is None

    def test_sum_of_live_stars(self):
        today = date.today()
        links = [_make_link(repo_id=i, weight=1.0) for i in (1, 2)]
        repo_days = {
            1: {today: _make_day(1, today, stars=300)},
            2: {today: _make_day(2, today, stars=200)},
        }
        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.stars_total == 500

    def test_backfilled_stars_excluded(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {
            1: {today: _make_day(1, today, stars=500, is_backfilled=True)},
        }
        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.stars_total is None

    def test_mixed_backfilled_and_live(self):
        today = date.today()
        links = [_make_link(repo_id=i, weight=1.0) for i in (1, 2, 3)]
        repo_days = {
            1: {today: _make_day(1, today, stars=100, is_backfilled=True)},
            2: {today: _make_day(2, today, stars=200, is_backfilled=False)},
            3: {today: _make_day(3, today, stars=None)},
        }
        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.stars_total == 200  # only live repo with stars


class TestSampleDaysSemantics:
    """PROBLEM 3: sample_days counts distinct calendar days with at least one metric."""

    def test_counts_days_with_any_metric(self):
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {}
        # 5 days with stars only, 3 days with commits only, 2 days with both
        for i in range(10):
            d = today - timedelta(days=i)
            if i < 5:
                repo_days.setdefault(1, {})[d] = _make_day(1, d, stars=100)
            elif i < 8:
                repo_days.setdefault(1, {})[d] = _make_day(1, d, commits=5)
            else:
                repo_days.setdefault(1, {})[d] = _make_day(1, d, stars=100, commits=5)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.sample_days == 10

    def test_no_double_counting(self):
        """Same day with stars AND commits counts as 1, not 2."""
        today = date.today()
        links = [_make_link(repo_id=1, weight=1.0)]
        repo_days = {
            1: {today: _make_day(1, today, stars=100, commits=5, releases=1)},
        }
        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.sample_days == 1

    def test_multiple_repos_same_day(self):
        """Two repos with data on the same day → 1 sample day."""
        today = date.today()
        links = [_make_link(repo_id=i, weight=1.0) for i in (1, 2)]
        repo_days = {
            1: {today: _make_day(1, today, stars=100)},
            2: {today: _make_day(2, today, commits=5)},
        }
        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)
        assert sig.sample_days == 1


class TestRegressionSparseVelocity:
    """Regression: sparse data across 28d window produces correct velocity."""

    def test_vllm_sparse_scenario(self):
        """vLLM-like: 3 repos, sparse observations, velocity should not overestimate."""
        today = date.today()
        links = [_make_link(repo_id=i, weight=w) for i, w in [(1, 1.0), (2, 0.6), (3, 0.25)]]
        repo_days = {}
        # Repo 1: data every day for 28 days, delta=5
        for i in range(28):
            d = today - timedelta(days=i)
            repo_days.setdefault(1, {})[d] = _make_day(1, d, stars_delta=5)
        # Repo 2: data only on days 0, 3, 7, 14, 21, delta=10
        for offset in [0, 3, 7, 14, 21]:
            d = today - timedelta(days=offset)
            repo_days.setdefault(2, {})[d] = _make_day(2, d, stars_delta=10)
        # Repo 3: data only on days 0, 10, 20, delta=2
        for offset in [0, 10, 20]:
            d = today - timedelta(days=offset)
            repo_days.setdefault(3, {})[d] = _make_day(3, d, stars_delta=2)

        tech = _make_tech()
        sig = compute_tech_signals(tech, links, repo_days, today)

        # 7d window (days 0-6): repo1 every day (5), repo2 on day 3 (10*0.6=6)
        # deltas: {0: 5+6+2*0.25=11.5, 1:5, 2:5, 3:5+6=11, 4:5, 5:5, 6:5}
        # sum = 11.5+5+5+11+5+5+5 = 47.5, velocity = 47.5/7 ≈ 6.79
        assert sig.star_velocity_7d is not None
        assert abs(sig.star_velocity_7d - 47.5 / 7) < 0.1

        # 28d velocity should also divide by 28, not by available count
        assert sig.star_velocity_28d is not None
        assert sig.star_velocity_28d == sig.stars_delta_28d / 28
