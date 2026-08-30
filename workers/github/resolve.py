"""Resolve curated GitHub repositories into immutable database identities.

The worker uses GitHub's exact repository endpoint (never search), updates
mutable metadata on repeat runs, and records partial failures in ingestion_run.

    uv run python -m workers.github.resolve
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from internetweather.config import get_settings
from internetweather.enums import RecordSource, TrackingState
from internetweather.models import Repository, Technology, TechnologyRepository
from internetweather.universe import SeedRepository, TechnologyUniverse, load_universe
from workers._runtime import (
    QuotaExhausted,
    RunFailed,
    RunStats,
    configure_logging,
    require_database,
    tracked_run,
)

log = logging.getLogger("github.resolve")
GITHUB_API = "https://api.github.com"
API_VERSION = "2022-11-28"


class ResolutionError(RuntimeError):
    """An expected failure resolving a single curated repository."""


class MissingGitHubToken(ResolutionError):
    pass


class RepositoryNotFound(ResolutionError):
    pass


class RepositoryInaccessible(ResolutionError):
    pass


class TransientGitHubFailure(ResolutionError):
    pass


class MalformedGitHubResponse(ResolutionError):
    pass


class MalformedUniverse(ResolutionError):
    pass


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    github_id: int
    full_name: str
    owner: str
    name: str
    description: str | None
    homepage: str | None
    primary_language: str | None
    topics: list[str]
    license_spdx: str | None
    default_branch: str | None
    is_fork: bool
    is_archived: bool
    created_at_github: datetime | None
    pushed_at_github: datetime | None
    stars: int
    forks: int
    watchers: int
    open_issues: int
    etag: str | None


@dataclass(frozen=True, slots=True)
class ResolutionFailure:
    full_name: str
    kind: str
    detail: str


def github_headers(token: str | None) -> dict[str, str]:
    if not token or not token.strip():
        raise MissingGitHubToken("GITHUB_TOKEN is required to resolve curated repositories")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token.strip()}",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "internet-weather-resolver",
    }


def _timestamp(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MalformedGitHubResponse(f"{field} is not an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MalformedGitHubResponse(f"{field} is not an ISO timestamp") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _string(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise MalformedGitHubResponse(f"response has no valid {field}")
    return value


def _count(data: dict[str, Any], field: str) -> int:
    value = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MalformedGitHubResponse(f"response has no valid {field}")
    return value


def repository_from_response(data: dict[str, Any], etag: str | None) -> GitHubRepository:
    """Validate GitHub data before it reaches the normalized schema."""
    owner = data.get("owner")
    topics = data.get("topics") or []
    if not isinstance(owner, dict):
        raise MalformedGitHubResponse("response has no owner object")
    if not isinstance(topics, list) or not all(isinstance(topic, str) for topic in topics):
        raise MalformedGitHubResponse("response has invalid topics")
    license_data = data.get("license")
    license_spdx = (
        license_data.get("spdx_id")
        if isinstance(license_data, dict) and isinstance(license_data.get("spdx_id"), str)
        else None
    )
    github_id = _count(data, "id")
    if github_id == 0:
        raise MalformedGitHubResponse("response has invalid id")
    def optional_string(field: str) -> str | None:
        value = data.get(field)
        return value if isinstance(value, str) else None
    return GitHubRepository(
        github_id=github_id,
        full_name=_string(data, "full_name"),
        owner=_string(owner, "login"),
        name=_string(data, "name"),
        description=optional_string("description"), homepage=optional_string("homepage"),
        primary_language=optional_string("language"), topics=topics, license_spdx=license_spdx,
        default_branch=optional_string("default_branch"), is_fork=bool(data.get("fork", False)),
        is_archived=bool(data.get("archived", False)),
        created_at_github=_timestamp(data.get("created_at"), "created_at"),
        pushed_at_github=_timestamp(data.get("pushed_at"), "pushed_at"),
        stars=_count(data, "stargazers_count"), forks=_count(data, "forks_count"),
        watchers=_count(data, "subscribers_count"), open_issues=_count(data, "open_issues_count"),
        etag=etag,
    )


def _rate_headers(headers: httpx.Headers, stats: RunStats) -> None:
    try:
        if (remaining := headers.get("x-ratelimit-remaining")) is not None:
            stats.rate_limit_remaining = int(remaining)
        if (reset := headers.get("x-ratelimit-reset")) is not None:
            stats.rate_limit_reset_at = datetime.fromtimestamp(int(reset), tz=UTC)
    except (OSError, OverflowError, ValueError):
        log.warning("GitHub returned invalid rate-limit headers")


class GitHubResolver:
    """Authenticated, retrying client for the exact /repos endpoint."""

    def __init__(self, client: httpx.Client, stats: RunStats):
        self.client, self.stats = client, stats

    def resolve(self, full_name: str) -> GitHubRepository:
        def request() -> GitHubRepository:
            try:
                response = self.client.get(f"/repos/{full_name}")
            except httpx.TransportError as exc:
                raise TransientGitHubFailure(f"{full_name}: network error: {exc}") from exc
            self.stats.api_calls += 1
            self.stats.records_read += 1
            _rate_headers(response.headers, self.stats)
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise MalformedGitHubResponse(f"{full_name}: invalid JSON") from exc
                if not isinstance(data, dict):
                    raise MalformedGitHubResponse(f"{full_name}: response is not an object")
                return repository_from_response(data, response.headers.get("etag"))
            if response.status_code == 404:
                raise RepositoryNotFound(f"{full_name}: repository not found")
            if response.status_code in {403, 429} and self.stats.rate_limit_remaining == 0:
                raise QuotaExhausted(f"{full_name}: GitHub rate limit exhausted")
            if response.status_code in {401, 403}:
                raise RepositoryInaccessible(f"{full_name}: forbidden, private, or inaccessible")
            if 500 <= response.status_code <= 599:
                raise TransientGitHubFailure(f"{full_name}: transient HTTP {response.status_code}")
            raise ResolutionError(f"{full_name}: GitHub returned HTTP {response.status_code}")

        return Retrying(
            retry=retry_if_exception_type(TransientGitHubFailure),
            stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.1, min=0.1, max=1),
            reraise=True,
        )(request)


def _apply(row: Repository, resolved: GitHubRepository) -> bool:
    values: dict[str, object] = {
        "github_id": resolved.github_id,
        "full_name": resolved.full_name,
        "owner": resolved.owner,
        "name": resolved.name,
        "description": resolved.description,
        "homepage": resolved.homepage,
        "primary_language": resolved.primary_language,
        "topics": list(resolved.topics),
        "license_spdx": resolved.license_spdx,
        "default_branch": resolved.default_branch,
        "is_fork": resolved.is_fork,
        "is_archived": resolved.is_archived,
        "created_at_github": resolved.created_at_github,
        "pushed_at_github": resolved.pushed_at_github,
        "stars": resolved.stars,
        "forks": resolved.forks,
        "watchers": resolved.watchers,
        "open_issues": resolved.open_issues,
        "etag": resolved.etag,
        "last_synced_at": datetime.now(UTC),
        "tracking_state": TrackingState.ACTIVE,
        "source": RecordSource.CURATED,
    }
    changed = False
    for field, value in values.items():
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed = True
    return changed


def upsert_repository(
    session: Session,
    resolved: GitHubRepository,
    by_id: dict[int, Repository],
    by_name: dict[str, Repository],
) -> tuple[Repository, bool]:
    row = by_id.get(resolved.github_id) or by_name.get(
        resolved.full_name.casefold()
    )
    created = row is None
    if row is None:
        row = Repository(
            github_id=resolved.github_id,
            full_name=resolved.full_name,
            owner=resolved.owner,
            name=resolved.name,
        )
        session.add(row)
        session.flush()
    changed = _apply(row, resolved)
    by_id[resolved.github_id] = row
    by_name[resolved.full_name.casefold()] = row
    return row, created or changed


def upsert_link(
    session: Session, technology: Technology, repository: Repository, seed: SeedRepository,
    links: dict[tuple[int, int], TechnologyRepository],
) -> bool:
    key = (technology.id, repository.id)
    row = links.get(key)
    if row is None:
        row = TechnologyRepository(
            technology_id=technology.id,
            repository_id=repository.id,
            relation=seed.relation,
            weight=seed.weight,
            source=RecordSource.CURATED,
        )
        session.add(row)
        links[key] = row
        return True
    changed = False
    updates = {
        "relation": seed.relation,
        "weight": seed.weight,
        "source": RecordSource.CURATED,
    }
    for field, value in updates.items():
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed = True
    return changed


def references(universe: TechnologyUniverse) -> list[tuple[str, str, SeedRepository]]:
    rows = []
    for technology in universe.technologies:
        for repository in technology.repositories:
            rows.append((repository.full_name, technology.slug, repository))
    return rows


def resolve_repositories(
    resolver: GitHubResolver,
    items: Iterable[tuple[str, str, SeedRepository]],
):
    resolved, failures = [], []
    cache: dict[str, GitHubRepository] = {}
    for full_name, slug, seed in items:
        try:
            key = full_name.casefold()
            repository = cache.get(key)
            if repository is None:
                repository = resolver.resolve(full_name)
                cache[key] = repository
            resolved.append((repository, slug, seed))
        except QuotaExhausted:
            raise
        except ResolutionError as exc:
            failures.append(ResolutionFailure(full_name, type(exc).__name__, str(exc)))
            log.error("could not resolve %s: %s", full_name, exc)
    return resolved, failures


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    configure_logging()
    try:
        headers = github_headers(get_settings().github_token)
    except MissingGitHubToken as exc:
        log.error("%s", exc)
        return 2
    if not require_database("github.resolve"):
        return 2
    outcome = None
    client_kw = dict(
        base_url=GITHUB_API, headers=headers,
        timeout=20, follow_redirects=True,
    )
    with httpx.Client(**client_kw) as client:
        with tracked_run("github", "resolve") as (session, stats):
            try:
                universe, items = load_universe(), None
                items = references(universe)
            except Exception as exc:
                raise RunFailed(f"malformed technology universe: {exc}") from exc
            technologies = {row.slug: row for row in session.scalars(select(Technology))}
            missing = sorted({slug for _, slug, _ in items} - set(technologies))
            if missing:
                raise RunFailed(
                    "run workers.seed.load_universe first; "
                    "missing: " + ", ".join(missing)
                )
            repository_rows = list(session.scalars(select(Repository)))
            by_id = {row.github_id: row for row in repository_rows}
            by_name = {row.full_name.casefold(): row for row in repository_rows}
            links = {
                (row.technology_id, row.repository_id): row
                for row in session.scalars(select(TechnologyRepository))
            }
            resolved, failures = resolve_repositories(GitHubResolver(client, stats), items)
            for repository, slug, seed in resolved:
                row, repository_changed = upsert_repository(session, repository, by_id, by_name)
                link_changed = upsert_link(session, technologies[slug], row, seed, links)
                stats.records_written += int(repository_changed) + int(link_changed)
            stats.cursor = {"requested": len(items), "resolved": len(resolved), "failures": [
                {"full_name": f.full_name, "kind": f.kind, "detail": f.detail} for f in failures
            ]}
            if failures:
                summary = "; ".join(f"{f.full_name} ({f.kind})" for f in failures[:10])
                raise RunFailed(f"{len(failures)} repository resolution failure(s): {summary}")
            log.info(
                "resolved %d repositories; wrote %d changes",
                len(resolved), stats.records_written,
            )
        outcome = stats.outcome
    return 0 if outcome and outcome.value == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
