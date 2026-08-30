"""Tests for GitHub repository resolution; all HTTP responses are mocked."""

from __future__ import annotations

import httpx
import pytest

from internetweather.enums import RepoRelation
from internetweather.models import Technology
from internetweather.universe import SeedRepository
from workers._runtime import QuotaExhausted, RunStats
from workers.github.resolve import (
    GitHubResolver,
    MissingGitHubToken,
    RepositoryNotFound,
    github_headers,
    repository_from_response,
    resolve_repositories,
    upsert_link,
    upsert_repository,
)


def payload(**overrides):
    base = {
        "id": 123,
        "full_name": "acme/widget",
        "name": "widget",
        "owner": {"login": "acme"},
        "description": "A widget",
        "homepage": "https://example.test",
        "language": "Python",
        "topics": ["ai"],
        "license": {"spdx_id": "MIT"},
        "default_branch": "main",
        "fork": False,
        "archived": False,
        "created_at": "2025-01-02T03:04:05Z",
        "pushed_at": "2025-01-03T03:04:05Z",
        "stargazers_count": 10,
        "forks_count": 2,
        "subscribers_count": 3,
        "open_issues_count": 4,
    }
    return base | overrides


class Responses:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = 0

    def get(self, url):
        self.calls += 1
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value


class FakeSession:
    def __init__(self):
        self.added = []
        self.next_id = 1

    def add(self, row):
        self.added.append(row)
        if getattr(row, "id", None) is None:
            row.id = self.next_id
            self.next_id += 1

    def flush(self):
        return None


def response(status, body=None, headers=None):
    return httpx.Response(status, json=body, headers=headers or {})


def seed(full_name="acme/widget"):
    return SeedRepository(full_name=full_name, relation=RepoRelation.CANONICAL, weight=1.0)


def test_successful_resolution_and_relationship_preservation():
    stats = RunStats()
    headers = {"etag": '"abc"', "x-ratelimit-remaining": "4999"}
    client = Responses([response(200, payload(), headers)])
    resolved = GitHubResolver(client, stats).resolve("acme/widget")
    session, repositories, names, links = FakeSession(), {}, {}, {}
    technology = Technology(id=7, slug="widget", name="Widget", subdomain="agentic_ai")

    row, changed = upsert_repository(session, resolved, repositories, names)
    linked = upsert_link(session, technology, row, seed(), links)

    assert changed and linked
    assert row.github_id == 123 and row.full_name == "acme/widget"
    assert row.etag == '"abc"' and stats.rate_limit_remaining == 4999
    assert links[(7, row.id)].relation is RepoRelation.CANONICAL
    assert links[(7, row.id)].weight == 1.0


def test_not_found_is_distinguished():
    client = Responses([response(404, {"message": "Not Found"})])
    with pytest.raises(RepositoryNotFound):
        GitHubResolver(client, RunStats()).resolve("acme/missing")


def test_rate_limit_is_distinguished():
    stats = RunStats()
    client = Responses([response(429, {"message": "limit"}, {"x-ratelimit-remaining": "0"})])
    with pytest.raises(QuotaExhausted):
        GitHubResolver(client, stats).resolve("acme/widget")
    assert stats.rate_limit_remaining == 0


def test_transient_failure_retries():
    client = Responses([response(502), response(200, payload())])
    assert GitHubResolver(client, RunStats()).resolve("acme/widget").github_id == 123
    assert client.calls == 2


def test_second_upsert_is_idempotent_and_does_not_duplicate_a_link():
    session, repositories, names, links = FakeSession(), {}, {}, {}
    technology = Technology(id=7, slug="widget", name="Widget", subdomain="agentic_ai")
    row, _ = upsert_repository(
        session, repository_from_response(payload(), None),
        repositories, names,
    )
    upsert_link(session, technology, row, seed(), links)
    same, changed = upsert_repository(
        session, repository_from_response(payload(description="Updated"), None), repositories, names
    )
    link_changed = upsert_link(session, technology, same, seed(), links)

    assert same is row and changed and row.description == "Updated"
    assert len(repositories) == len(names) == len(links) == 1
    assert link_changed is False


def test_partial_failures_are_retained_for_ingestion_accounting():
    stats = RunStats()
    client = Responses([response(200, payload()), response(404, {"message": "Not Found"})])
    resolved, failures = resolve_repositories(
        GitHubResolver(client, stats),
        [("acme/widget", "widget", seed()), ("acme/missing", "missing", seed("acme/missing"))],
    )
    assert len(resolved) == 1
    assert failures[0].full_name == "acme/missing"
    assert failures[0].kind == "RepositoryNotFound"
    assert stats.api_calls == 2


def test_missing_token_fails_clearly():
    with pytest.raises(MissingGitHubToken):
        github_headers(None)
