"""API contract tests.

These run with no database on purpose. Degraded mode is a declared product
state, so every read endpoint must return a valid, contract-shaped response
that says plainly that it has no data — not a 500, and not a fabricated zero
presented as a measurement.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from internetweather.api.app import create_app
from internetweather.db import check_db, get_session
from internetweather.enums import EpistemicStatus, Subdomain, WeatherState

#: Read endpoints that must survive having no database.
READ_PATHS = [
    "/health",
    "/api/status",
    "/api/vocabulary",
    "/api/weather",
    "/api/trends",
    "/api/technologies",
    "/api/events",
]


@pytest.fixture(scope="module")
def client():
    """Client with the session dependency forced to None.

    Overriding the dependency rather than relying on an absent .env keeps the
    test deterministic on a machine that has a real DATABASE_URL configured.
    """
    app = create_app()

    async def no_database():
        yield None

    def no_connectivity():
        return False, "DATABASE_URL not configured"

    app.dependency_overrides[get_session] = no_database
    app.dependency_overrides[check_db] = no_connectivity
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("path", READ_PATHS)
def test_read_endpoints_never_fail_without_a_database(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text


def test_health_reports_degraded_rather_than_erroring(client):
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["database"]["reachable"] is False
    assert body["version"]


@pytest.mark.parametrize(
    "path", ["/api/weather", "/api/trends", "/api/technologies", "/api/events"]
)
def test_data_endpoints_declare_their_own_emptiness(client, path):
    freshness = client.get(path).json()["freshness"]
    assert freshness["has_data"] is False
    assert freshness["as_of"] is None
    assert freshness["degraded_reason"], "an empty response must say why it is empty"


def test_trends_bands_are_present_but_empty(client):
    body = client.get("/api/trends").json()
    for band in ("heating", "cooling", "emerging", "anomalies", "events"):
        assert body[band] == [], f"{band} should be an empty list, not missing"
    assert body["as_of"] is None


def test_vocabulary_is_complete(client):
    """The frontend must never hardcode a weather state or a subdomain label."""
    body = client.get("/api/vocabulary").json()

    states = {item["state"] for item in body["weather_states"]}
    assert states == {member.value for member in WeatherState}
    for item in body["weather_states"]:
        assert item["glyph"] and item["label"] and item["meaning"]

    subdomains = {item["key"] for item in body["subdomains"]}
    assert subdomains == {member.value for member in Subdomain}
    assert all(item["label"] for item in body["subdomains"])

    assert set(body["epistemic_statuses"]) == {member.value for member in EpistemicStatus}


def test_single_record_lookup_without_a_database_is_503_not_404(client):
    """Absence we never checked must not be reported as absence.

    With no database the API cannot know whether a slug is tracked, so the
    single-record routes decline (503). Returning 404 would let the frontend
    render "this technology is not tracked", which is a claim, not an observation.
    """
    for path in (
        "/api/technologies/does-not-exist",
        "/api/technologies/mcp/history",
        "/api/technologies/mcp/relationships",
        "/api/events/1",
    ):
        response = client.get(path)
        assert response.status_code == 503, path
        assert "no database" in response.json()["detail"].lower()


def test_list_routes_stay_200_when_single_record_routes_decline(client):
    """The distinction is deliberate: a list of nothing is a valid observation."""
    body = client.get("/api/events", params={"technology": "mcp"}).json()
    assert body["items"] == []
    assert body["freshness"]["has_data"] is False


def test_malformed_slug_is_rejected_before_reaching_the_database(client):
    assert client.get("/api/technologies/Not_A_Slug").status_code == 422


def test_ordering_is_an_allow_list(client):
    """An ORDER BY assembled from raw client input would be an injection surface."""
    assert client.get("/api/technologies", params={"order": "name"}).status_code == 200
    assert client.get("/api/technologies", params={"order": "stars; DROP"}).status_code == 422


def test_research_contract_exists_and_is_honest(client):
    """Declared, documented, and explicitly not implemented yet."""
    created = client.post("/api/research", json={"technology_slug": "mcp"})
    assert created.status_code == 501
    assert "not implemented" in created.json()["detail"].lower()

    assert client.get("/api/research/abc").status_code == 501
    assert client.post("/api/research/abc/chat", json={"message": "why?"}).status_code == 501


def test_openapi_document_is_complete(client):
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "Internet Weather API"
    expected = {
        "/health",
        "/api/status",
        "/api/vocabulary",
        "/api/weather",
        "/api/trends",
        "/api/technologies",
        "/api/technologies/{slug}",
        "/api/technologies/{slug}/history",
        "/api/technologies/{slug}/relationships",
        "/api/events",
        "/api/events/{event_id}",
        "/api/research",
        "/api/research/{research_id}",
        "/api/research/{research_id}/chat",
    }
    assert expected <= set(spec["paths"])


# ---------------------------------------------------------------------------
# Tests: health endpoint with configured database
# ---------------------------------------------------------------------------


def test_health_reports_ok_when_database_is_reachable():
    """When check_db returns reachable=True, /health must report status 'ok'."""

    def reachable_db():
        return True, None

    app = create_app()
    app.dependency_overrides[check_db] = reachable_db
    with TestClient(app) as c:
        body = c.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"]["reachable"] is True
    assert body["database"]["error"] is None


def test_health_reports_degraded_when_database_fails():
    """When check_db returns an error, /health must report degraded with the error."""

    def failing_db():
        return False, "Connection refused"

    app = create_app()
    app.dependency_overrides[check_db] = failing_db
    with TestClient(app) as c:
        body = c.get("/health").json()
    assert body["status"] == "degraded"
    assert body["database"]["reachable"] is False
    assert body["database"]["error"] == "Connection refused"


def test_health_reports_degraded_when_database_not_configured():
    """When check_db returns not-configured, /health must report degraded."""

    def unconfigured_db():
        return False, "DATABASE_URL not configured"

    app = create_app()
    app.dependency_overrides[check_db] = unconfigured_db
    with TestClient(app) as c:
        body = c.get("/health").json()
    assert body["status"] == "degraded"
    assert body["database"]["reachable"] is False
