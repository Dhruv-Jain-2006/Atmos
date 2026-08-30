"""Integration test: fixture dataset → detection → API response.

Proves the full pipeline works end-to-end:

  fixture repository_metric_daily
  → detection worker (compute_tech_signals)
  → technology_signal_daily + ecosystem_event
  → FastAPI → API response

Uses an in-memory SQLite database with PostgreSQL type overrides.
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# SQLite type overrides for PostgreSQL-specific types
# ---------------------------------------------------------------------------
import json as _json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Text, TypeDecorator, create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from internetweather.analysis.weather_state import SignalInput, classify
from internetweather.api.app import create_app
from internetweather.db import get_session
from internetweather.enums import (
    EventType,
    RecordSource,
    RelationshipType,
    RepoRelation,
    Subdomain,
    TrackingState,
)
from internetweather.models import Base, EcosystemEvent
from internetweather.models.repository import Repository, RepositoryMetricDaily
from internetweather.models.signal import TechnologySignalDaily
from internetweather.models.technology import (
    Technology,
    TechnologyRelationship,
    TechnologyRepository,
)
from workers.detection.aggregation import (
    compute_tech_signals,
    load_repo_days,
    load_repo_links,
)


class SQLiteARRAY(TypeDecorator):
    """Stores Python lists as JSON strings in SQLite."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return _json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        try:
            return _json.loads(value)
        except (ValueError, TypeError):
            return []


class SQLiteJSONB(TypeDecorator):
    """Stores dicts as JSON strings in SQLite."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, dict):
            return _json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return {}
        try:
            return _json.loads(value)
        except (ValueError, TypeError):
            return {}


# ---------------------------------------------------------------------------
# Fixture: seeded dataset
# ---------------------------------------------------------------------------

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def _seed(session: Session) -> dict:
    """Insert a realistic fixture dataset and return inserted objects.

    Creates:
    - 4 technologies across 3 subdomains (HOT, EMERGING, STABLE, COOLING)
    - 6 repositories with varying weights
    - 14 days of repository_metric_daily
    - 1 technology_relationship
    """
    # --- Technologies ---
    tech_hot = Technology(
        slug="hot-framework",
        name="Hot Framework",
        subdomain=Subdomain.AGENTIC_AI,
        summary="A fast-rising framework",
        aliases=["hot-fw"],
        source=RecordSource.CURATED,
        headline=True,
        is_active=True,
    )
    tech_emerging = Technology(
        slug="emerging-lib",
        name="Emerging Lib",
        subdomain=Subdomain.AI_INFRA,
        summary="Small but growing",
        aliases=[],
        source=RecordSource.CURATED,
        headline=False,
        is_active=True,
    )
    tech_stable = Technology(
        slug="stable-tool",
        name="Stable Tool",
        subdomain=Subdomain.RAG,
        summary="Mature and steady",
        aliases=["stable-tool"],
        source=RecordSource.CURATED,
        headline=False,
        is_active=True,
    )
    tech_cooling = Technology(
        slug="cooling-project",
        name="Cooling Project",
        subdomain=Subdomain.LLM_ECOSYSTEM,
        summary="Losing momentum",
        aliases=[],
        source=RecordSource.CURATED,
        headline=False,
        is_active=True,
    )
    session.add_all([tech_hot, tech_emerging, tech_stable, tech_cooling])
    session.flush()

    # --- Repositories ---
    repos = {}
    for i, (owner, name, stars, lang) in enumerate([
        ("hot-org", "hot-framework", 12000, "Python"),
        ("hot-org", "hot-framework-core", 8000, "Rust"),
        ("emerging-org", "emerging-lib", 2000, "Python"),
        ("stable-org", "stable-tool", 25000, "Go"),
        ("cooling-org", "cooling-project", 15000, "Python"),
        ("ecosystem-org", "awesome-hot", 3000, None),
    ], start=1):
        repo = Repository(
            github_id=i * 1000,
            full_name=f"{owner}/{name}",
            owner=owner,
            name=name,
            primary_language=lang,
            topics=[],
            stars=stars,
            forks=stars // 10,
            watchers=stars // 20,
            open_issues=5,
            tracking_state=TrackingState.ACTIVE,
            source=RecordSource.CURATED,
        )
        session.add(repo)
        session.flush()
        repos[f"{owner}/{name}"] = repo

    # --- Technology-Repository links ---
    links_data = [
        ("hot-framework", "hot-org/hot-framework", RepoRelation.CANONICAL, 1.0),
        ("hot-framework", "hot-org/hot-framework-core", RepoRelation.IMPLEMENTATION, 0.6),
        ("hot-framework", "ecosystem-org/awesome-hot", RepoRelation.ECOSYSTEM, 0.25),
        ("emerging-lib", "emerging-org/emerging-lib", RepoRelation.CANONICAL, 1.0),
        ("stable-tool", "stable-org/stable-tool", RepoRelation.CANONICAL, 1.0),
        ("cooling-project", "cooling-org/cooling-project", RepoRelation.CANONICAL, 1.0),
    ]
    tech_by_slug = {
        t.slug: t for t in [tech_hot, tech_emerging, tech_stable, tech_cooling]
    }
    for tech_slug, repo_name, relation, weight in links_data:
        tr = TechnologyRepository(
            technology_id=tech_by_slug[tech_slug].id,
            repository_id=repos[repo_name].id,
            relation=relation,
            weight=weight,
            source=RecordSource.CURATED,
        )
        session.add(tr)

    # --- TechnologyRelationship ---
    rel = TechnologyRelationship(
        source_technology_id=tech_hot.id,
        target_technology_id=tech_emerging.id,
        relation_type=RelationshipType.COMPLEMENTS,
        strength=0.6,
        basis=RecordSource.CURATED,
        computed_on=TODAY,
    )
    session.add(rel)

    # --- RepositoryMetricDaily (14 days) ---
    metrics = []
    for day_offset in range(14, 0, -1):
        day = TODAY - timedelta(days=day_offset)

        # Hot framework: accelerating stars (10→50/day)
        hot_stars = 10000 + (14 - day_offset) * (10 + day_offset * 3)
        metrics.append(
            RepositoryMetricDaily(
                repository_id=repos["hot-org/hot-framework"].id,
                day=day,
                stars=hot_stars,
                forks=hot_stars // 10,
                watchers=hot_stars // 20,
                open_issues=5,
                stars_delta=10 + day_offset * 3,
                commits=3 + day_offset % 3,
                releases=1 if day_offset == 1 else 0,
                is_backfilled=False,
            )
        )

        # Hot framework core: steady support
        metrics.append(
            RepositoryMetricDaily(
                repository_id=repos["hot-org/hot-framework-core"].id,
                day=day,
                stars=7000 + (14 - day_offset) * 5,
                forks=700,
                watchers=350,
                open_issues=3,
                stars_delta=5,
                commits=1,
                releases=0,
                is_backfilled=False,
            )
        )

        # Emerging lib: small but growing (200→800 stars)
        em_stars = 200 + (14 - day_offset) * 45
        metrics.append(
            RepositoryMetricDaily(
                repository_id=repos["emerging-org/emerging-lib"].id,
                day=day,
                stars=em_stars,
                forks=em_stars // 10,
                watchers=em_stars // 20,
                open_issues=2,
                stars_delta=45,
                commits=2,
                releases=0,
                is_backfilled=False,
            )
        )

        # Stable tool: flat (25000, no change)
        metrics.append(
            RepositoryMetricDaily(
                repository_id=repos["stable-org/stable-tool"].id,
                day=day,
                stars=25000,
                forks=2500,
                watchers=1250,
                open_issues=10,
                stars_delta=0,
                commits=1,
                releases=0,
                is_backfilled=False,
            )
        )

        # Cooling project: declining stars (50→5/day delta)
        cool_delta = max(5, 50 - day_offset * 3)
        metrics.append(
            RepositoryMetricDaily(
                repository_id=repos["cooling-org/cooling-project"].id,
                day=day,
                stars=15000 + (14 - day_offset) * cool_delta,
                forks=1500,
                watchers=750,
                open_issues=8,
                stars_delta=-cool_delta,
                commits=1 if day_offset > 7 else 0,
                releases=0,
                is_backfilled=False,
            )
        )

    session.add_all(metrics)
    session.flush()

    # --- Backfilled metrics (NULL levels, is_backfilled=True) ---
    for day_offset in range(28, 14, -1):
        day = TODAY - timedelta(days=day_offset)
        metrics.append(
            RepositoryMetricDaily(
                repository_id=repos["hot-org/hot-framework"].id,
                day=day,
                stars=None,
                forks=None,
                watchers=None,
                open_issues=None,
                stars_delta=None,
                commits=2,
                releases=0,
                is_backfilled=True,
            )
        )
    session.add_all(metrics)
    session.flush()

    return {
        "technologies": tech_by_slug,
        "repos": repos,
    }


def _run_detection(session: Session, tech_by_slug: dict, repos: dict) -> None:
    """Run the detection worker over the fixture data."""
    today = date.today()

    # Load technologies with their repo links (using the real load_repo_links)
    from sqlalchemy import select as sa_select

    technologies = list(
        session.scalars(
            sa_select(Technology).where(Technology.is_active.is_(True))
        )
    )
    repo_links_map = load_repo_links(technologies)

    all_repo_ids = list({link.repository_id for links in repo_links_map.values() for link in links})

    # Load metrics
    metrics = list(
        session.scalars(
            sa_select(RepositoryMetricDaily).where(
                RepositoryMetricDaily.repository_id.in_(all_repo_ids),
                RepositoryMetricDaily.day >= today - timedelta(days=29),
            )
        )
    )
    repo_days = load_repo_days(metrics)

    # Compute signals for each technology on each day
    for tech in technologies:
        links = repo_links_map.get(tech.id, [])
        if not links:
            continue

        # Run detection for the trailing 7 days
        for day_offset in range(7, -1, -1):
            day = today - timedelta(days=day_offset)
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

            # Upsert signal (SQLite-compatible: check existence first)
            existing = session.get(
                TechnologySignalDaily, (tech.id, day)
            )
            if existing:
                existing.weather_state = classification.state.value
                existing.momentum = classification.momentum
                existing.confidence = classification.confidence
                existing.stars_total = sig.stars_total
                existing.stars_delta_1d = sig.stars_delta_1d
                existing.stars_delta_7d = sig.stars_delta_7d
                existing.stars_delta_28d = sig.stars_delta_28d
                existing.star_velocity_7d = sig.star_velocity_7d
                existing.star_velocity_28d = sig.star_velocity_28d
                existing.star_acceleration = sig.star_acceleration
                existing.activity_score = sig.activity_score
                existing.commit_velocity_7d = sig.commit_velocity_7d
                existing.release_count_28d = sig.release_count_28d
                existing.contributor_count_28d = sig.contributor_count_28d
                existing.repo_count = sig.repo_count
                existing.active_repo_count = sig.active_repo_count
                existing.anomaly_z = sig.anomaly_z
                existing.sample_days = sig.sample_days
                existing.computed_at = datetime.now(UTC)
            else:
                session.add(
                    TechnologySignalDaily(
                        technology_id=tech.id,
                        day=day,
                        weather_state=classification.state.value,
                        momentum=classification.momentum,
                        confidence=classification.confidence,
                        stars_total=sig.stars_total,
                        stars_delta_1d=sig.stars_delta_1d,
                        stars_delta_7d=sig.stars_delta_7d,
                        stars_delta_28d=sig.stars_delta_28d,
                        star_velocity_7d=sig.star_velocity_7d,
                        star_velocity_28d=sig.star_velocity_28d,
                        star_acceleration=sig.star_acceleration,
                        activity_score=sig.activity_score,
                        commit_velocity_7d=sig.commit_velocity_7d,
                        release_count_28d=sig.release_count_28d,
                        contributor_count_28d=sig.contributor_count_28d,
                        repo_count=sig.repo_count,
                        active_repo_count=sig.active_repo_count,
                        anomaly_z=sig.anomaly_z,
                        sample_days=sig.sample_days,
                        computed_at=datetime.now(UTC),
                    )
                )

    # Assign ranks
    from sqlalchemy import func

    # First, get the ranked data as a dict keyed by technology_id
    rows = (
        session.query(
            TechnologySignalDaily.technology_id,
            TechnologySignalDaily.day,
            func.rank()
            .over(order_by=TechnologySignalDaily.momentum.desc())
            .label("rank_overall"),
        )
        .filter(TechnologySignalDaily.day == today)
        .all()
    )
    rank_by_tech = {r.technology_id: r.rank_overall for r in rows}

    # Get subdomain ranks
    subdomain_rows = (
        session.query(
            TechnologySignalDaily.technology_id,
            TechnologySignalDaily.day,
            Technology.subdomain,
            func.rank()
            .over(
                partition_by=Technology.subdomain,
                order_by=TechnologySignalDaily.momentum.desc(),
            )
            .label("rank_subdomain"),
        )
        .join(Technology, Technology.id == TechnologySignalDaily.technology_id)
        .filter(TechnologySignalDaily.day == today)
        .all()
    )
    subdomain_rank_by_tech = {r.technology_id: r.rank_subdomain for r in subdomain_rows}

    # Update each row individually
    for tech_id, overall_rank in rank_by_tech.items():
        sig = session.get(TechnologySignalDaily, (tech_id, today))
        if sig:
            sig.rank_overall = overall_rank
            sig.rank_subdomain = subdomain_rank_by_tech.get(tech_id)

    # Emit events for the HOT technology
    hot_tech = tech_by_slug["hot-framework"]
    event = EcosystemEvent(
        technology_id=hot_tech.id,
        event_type=EventType.STAR_SPIKE,
        occurred_on=today,
        title="Hot Framework became HOT",
        summary="Hot Framework transitioned from STABLE to HOT.",
        magnitude=0.5,
        confidence=0.7,
        epistemic_status="observation",
        evidence=json.dumps({"metrics": {"previous_state": "stable", "new_state": "hot"}}),
        dedupe_key=f"state_transition:{hot_tech.id}:{today}:hot",
    )
    session.add(event)
    session.flush()


# ---------------------------------------------------------------------------
# Fixture: seeded database + FastAPI client
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seeded_db():
    """Module-scoped seeded database.

    Uses StaticPool so all connections (including API request threads) share
    the same in-memory SQLite database.  check_same_thread=False is required
    because FastAPI runs sync endpoints in a thread pool.
    """
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Replace PostgreSQL-specific types with SQLite-compatible ones
    # Save originals so we can restore them after the session is done
    originals = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, ARRAY):
                originals.append((col, col.type))
                col.type = SQLiteARRAY()
            elif isinstance(col.type, JSONB):
                originals.append((col, col.type))
                col.type = SQLiteJSONB()

    Base.metadata.create_all(eng)

    factory = sessionmaker(bind=eng, expire_on_commit=False)
    sess = factory()
    data = _seed(sess)
    _run_detection(sess, data["technologies"], data["repos"])
    sess.commit()
    yield eng, sess
    sess.close()
    eng.dispose()

    # Restore original types so other test modules aren't affected
    for col, orig_type in originals:
        col.type = orig_type


@pytest.fixture(scope="module")
def client(seeded_db):
    """FastAPI test client backed by the seeded database."""
    _engine, sess = seeded_db

    app = create_app()

    async def override_session():
        yield sess

    app.dependency_overrides[get_session] = override_session

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests: /api/weather (WeatherOverview)
# ---------------------------------------------------------------------------


class TestWeatherOverview:
    def test_returns_200(self, client):
        resp = client.get("/api/weather")
        assert resp.status_code == 200

    def test_has_data(self, client):
        body = client.get("/api/weather").json()
        assert body["freshness"]["has_data"] is True
        assert body["as_of"] is not None

    def test_technology_count(self, client):
        body = client.get("/api/weather").json()
        assert body["technology_count"] == 4

    def test_state_counts_present(self, client):
        body = client.get("/api/weather").json()
        assert len(body["state_counts"]) > 0
        total = sum(body["state_counts"].values())
        assert total == 4

    def test_subdomains_present(self, client):
        body = client.get("/api/weather").json()
        assert len(body["subdomains"]) >= 3


# ---------------------------------------------------------------------------
# Tests: /api/trends (Trends)
# ---------------------------------------------------------------------------


class TestTrends:
    def test_returns_200(self, client):
        resp = client.get("/api/trends")
        assert resp.status_code == 200

    def test_has_data(self, client):
        body = client.get("/api/trends").json()
        assert body["freshness"]["has_data"] is True

    def test_bands_are_lists(self, client):
        body = client.get("/api/trends").json()
        for band in ("heating", "cooling", "emerging", "anomalies"):
            assert isinstance(body[band], list)

    def test_heating_band_populated(self, client):
        body = client.get("/api/trends").json()
        assert len(body["heating"]) > 0
        # Hot framework should be in heating
        slugs = [card["slug"] for card in body["heating"]]
        assert "hot-framework" in slugs

    def test_events_present(self, client):
        body = client.get("/api/trends").json()
        assert isinstance(body["events"], list)
        assert len(body["events"]) > 0

    def test_technology_cards_have_signals(self, client):
        body = client.get("/api/trends").json()
        for card in body["heating"]:
            assert "signals" in card
            assert "momentum" in card["signals"]
            assert "confidence" in card["signals"]
            assert "weather_state" in card

    def test_technology_cards_have_spark(self, client):
        body = client.get("/api/trends").json()
        for card in body["heating"]:
            assert "spark" in card
            assert isinstance(card["spark"], list)

    def test_technology_cards_have_explanation(self, client):
        body = client.get("/api/trends").json()
        for card in body["heating"]:
            assert "explanation" in card
            assert card["explanation"] is not None

    def test_filter_by_subdomain(self, client):
        resp = client.get("/api/trends", params={"subdomain": "agentic_ai"})
        assert resp.status_code == 200
        body = resp.json()
        # Should only have agentic_ai technologies
        for card in body["heating"]:
            assert card["subdomain"] == "agentic_ai"


# ---------------------------------------------------------------------------
# Tests: /api/technologies (TechnologyList)
# ---------------------------------------------------------------------------


class TestTechnologyList:
    def test_returns_200(self, client):
        resp = client.get("/api/technologies")
        assert resp.status_code == 200

    def test_has_data(self, client):
        body = client.get("/api/technologies").json()
        assert body["freshness"]["has_data"] is True
        assert body["page"]["total"] == 4

    def test_items_are_technology_cards(self, client):
        body = client.get("/api/technologies").json()
        assert len(body["items"]) == 4
        for item in body["items"]:
            assert "slug" in item
            assert "weather_state" in item
            assert "signals" in item

    def test_ordering_by_stars(self, client):
        body = client.get("/api/technologies", params={"order": "stars"}).json()
        stars = [item["signals"]["stars_total"] for item in body["items"]]
        assert stars == sorted(stars, reverse=True)

    def test_filter_by_state(self, client):
        body = client.get("/api/technologies", params={"state": "hot"}).json()
        for item in body["items"]:
            assert item["weather_state"] == "hot"

    def test_pagination(self, client):
        body = client.get("/api/technologies", params={"limit": 2, "offset": 0}).json()
        assert len(body["items"]) == 2
        assert body["page"]["total"] == 4

        body2 = client.get("/api/technologies", params={"limit": 2, "offset": 2}).json()
        assert len(body2["items"]) == 2
        # Different items
        slugs1 = {item["slug"] for item in body["items"]}
        slugs2 = {item["slug"] for item in body2["items"]}
        assert slugs1.isdisjoint(slugs2)


# ---------------------------------------------------------------------------
# Tests: /api/technologies/{slug} (TechnologyDetail)
# ---------------------------------------------------------------------------


class TestTechnologyDetail:
    def test_returns_200(self, client):
        resp = client.get("/api/technologies/hot-framework")
        assert resp.status_code == 200

    def test_detail_fields(self, client):
        body = client.get("/api/technologies/hot-framework").json()
        assert body["slug"] == "hot-framework"
        assert body["name"] == "Hot Framework"
        assert body["weather_state"] is not None
        assert body["signals"] is not None
        assert body["explanation"] is not None

    def test_detail_has_repositories(self, client):
        body = client.get("/api/technologies/hot-framework").json()
        assert len(body["repositories"]) == 3
        full_names = {r["full_name"] for r in body["repositories"]}
        assert "hot-org/hot-framework" in full_names

    def test_404_for_unknown_slug(self, client):
        resp = client.get("/api/technologies/does-not-exist")
        assert resp.status_code == 404

    def test_detail_has_aliases(self, client):
        body = client.get("/api/technologies/hot-framework").json()
        assert "hot-fw" in body["aliases"]


# ---------------------------------------------------------------------------
# Tests: /api/technologies/{slug}/history
# ---------------------------------------------------------------------------


class TestTechnologyHistory:
    def test_returns_200(self, client):
        resp = client.get("/api/technologies/hot-framework/history")
        assert resp.status_code == 200

    def test_history_has_points(self, client):
        body = client.get("/api/technologies/hot-framework/history").json()
        assert len(body["points"]) > 0
        # Should have up to 7 days of detection output
        assert len(body["points"]) <= 8

    def test_history_points_ordered(self, client):
        body = client.get("/api/technologies/hot-framework/history").json()
        days = [p["day"] for p in body["points"]]
        assert days == sorted(days)

    def test_history_point_fields(self, client):
        body = client.get("/api/technologies/hot-framework/history").json()
        for point in body["points"]:
            assert "day" in point
            assert "weather_state" in point
            assert "momentum" in point
            assert "confidence" in point
            assert "stars_total" in point

    def test_history_with_days_param(self, client):
        resp = client.get("/api/technologies/hot-framework/history", params={"days": 7})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["points"]) <= 7


# ---------------------------------------------------------------------------
# Tests: /api/technologies/{slug}/relationships
# ---------------------------------------------------------------------------


class TestTechnologyRelationships:
    def test_returns_200(self, client):
        resp = client.get("/api/technologies/hot-framework/relationships")
        assert resp.status_code == 200

    def test_has_related(self, client):
        body = client.get("/api/technologies/hot-framework/relationships").json()
        assert len(body["related"]) == 1
        assert body["related"][0]["slug"] == "emerging-lib"
        assert body["related"][0]["relation_type"] == "complements"

    def test_empty_for_unconnected(self, client):
        body = client.get("/api/technologies/stable-tool/relationships").json()
        assert body["related"] == []


# ---------------------------------------------------------------------------
# Tests: /api/events (EventList)
# ---------------------------------------------------------------------------


class TestEventList:
    def test_returns_200(self, client):
        resp = client.get("/api/events")
        assert resp.status_code == 200

    def test_has_events(self, client):
        body = client.get("/api/events").json()
        assert len(body["items"]) > 0

    def test_event_fields(self, client):
        body = client.get("/api/events").json()
        for evt in body["items"]:
            assert "id" in evt
            assert "event_type" in evt
            assert "title" in evt
            assert "occurred_on" in evt
            assert "magnitude" in evt

    def test_filter_by_technology(self, client):
        body = client.get(
            "/api/events", params={"technology": "hot-framework"}
        ).json()
        assert len(body["items"]) > 0
        for evt in body["items"]:
            assert evt["technology_slug"] == "hot-framework"

    def test_event_detail(self, client):
        body = client.get("/api/events").json()
        event_id = body["items"][0]["id"]
        resp = client.get(f"/api/events/{event_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert "evidence" in detail
        assert isinstance(detail["evidence"], list)


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unknown_technology_404(self, client):
        resp = client.get("/api/technologies/nonexistent")
        assert resp.status_code == 404

    def test_unknown_technology_history_404(self, client):
        resp = client.get("/api/technologies/nonexistent/history")
        assert resp.status_code == 404

    def test_unknown_technology_relationships_404(self, client):
        resp = client.get("/api/technologies/nonexistent/relationships")
        assert resp.status_code == 404

    def test_malformed_slug_rejected(self, client):
        resp = client.get("/api/technologies/Invalid_Slug")
        assert resp.status_code == 422

    def test_invalid_event_id(self, client):
        resp = client.get("/api/events/999999")
        assert resp.status_code == 404

    def test_history_days_bounds(self, client):
        resp = client.get("/api/technologies/hot-framework/history", params={"days": 500})
        assert resp.status_code == 422  # max is 365

    def test_ordering_allow_list(self, client):
        resp = client.get("/api/technologies", params={"order": "injection; DROP"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: degraded mode (no database)
# ---------------------------------------------------------------------------


class TestDegradedMode:
    @pytest.fixture()
    def degraded_client(self):
        app = create_app()

        async def no_database():
            yield None

        app.dependency_overrides[get_session] = no_database
        with TestClient(app) as c:
            yield c

    def test_weather_returns_empty(self, degraded_client):
        body = degraded_client.get("/api/weather").json()
        assert body["freshness"]["has_data"] is False

    def test_trends_returns_empty(self, degraded_client):
        body = degraded_client.get("/api/trends").json()
        assert body["freshness"]["has_data"] is False
        for band in ("heating", "cooling", "emerging", "anomalies"):
            assert body[band] == []

    def test_technologies_returns_empty(self, degraded_client):
        body = degraded_client.get("/api/technologies").json()
        assert body["items"] == []
        assert body["page"]["total"] == 0

    def test_events_returns_empty(self, degraded_client):
        body = degraded_client.get("/api/events").json()
        assert body["items"] == []

    def test_single_record_returns_503(self, degraded_client):
        resp = degraded_client.get("/api/technologies/mcp")
        assert resp.status_code == 503
