"""Parse and validate the curated technology universe.

``db/seed/technology_universe.yml`` is the editorial spine of the product. It is
hand-maintained, so it is validated as a contract rather than trusted: a typo in
a subdomain or a weight outside 0..1 must fail loudly at load time, not produce a
technology that silently never appears on Trends.

Pure and dependency-free — no database, no network. The seed worker consumes the
result; tests consume it directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from internetweather.enums import RepoRelation, Subdomain

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UNIVERSE_PATH = REPO_ROOT / "db" / "seed" / "technology_universe.yml"

#: Slugs appear in URLs and are never renamed once published.
Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)]

#: "owner/name" exactly as GitHub spells it.
FullName = Annotated[str, Field(pattern=r"^[\w.-]+/[\w.-]+$", max_length=255)]

#: Default signal weight per relation kind. A technology's canonical repo should
#: move its weather; an awesome-list that mentions it should barely nudge it.
DEFAULT_WEIGHTS: dict[RepoRelation, float] = {
    RepoRelation.CANONICAL: 1.0,
    RepoRelation.IMPLEMENTATION: 0.6,
    RepoRelation.INTEGRATION: 0.4,
    RepoRelation.ECOSYSTEM: 0.25,
}


class Strict(BaseModel):
    """Unknown keys are errors — a misspelled field must not be ignored."""

    model_config = ConfigDict(extra="forbid")


class SeedRepository(Strict):
    full_name: FullName
    relation: RepoRelation
    weight: float = Field(gt=0, le=1)


class SeedDiscovery(Strict):
    """Queries the discovery worker uses to find repositories we do not know yet."""

    topics: list[str] = Field(default_factory=list)
    orgs: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)


class SeedTechnology(Strict):
    slug: Slug
    name: str = Field(max_length=160)
    subdomain: Subdomain
    summary: str | None = None
    aliases: list[str] = Field(default_factory=list)
    headline: bool = False
    discovery: SeedDiscovery = Field(default_factory=SeedDiscovery)
    repositories: list[SeedRepository] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_duplicate_repositories(self) -> Self:
        seen: set[str] = set()
        for repo in self.repositories:
            key = repo.full_name.lower()
            if key in seen:
                raise ValueError(f"{self.slug}: repository listed twice: {repo.full_name}")
            seen.add(key)
        return self

    @model_validator(mode="after")
    def _has_a_centre(self) -> Self:
        """Every technology needs at least one canonical repository.

        Without one, its weather would be computed entirely from peripheral
        repos, which is how a technology ends up reflecting its ecosystem's mood
        rather than its own.
        """
        if not any(r.relation is RepoRelation.CANONICAL for r in self.repositories):
            raise ValueError(f"{self.slug}: no canonical repository")
        return self


class SubdomainMeta(Strict):
    name: str
    description: str


class TechnologyUniverse(Strict):
    version: int
    domain: str
    updated: str
    subdomains: dict[Subdomain, SubdomainMeta]
    technologies: list[SeedTechnology] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_slugs(self) -> Self:
        seen: set[str] = set()
        for tech in self.technologies:
            if tech.slug in seen:
                raise ValueError(f"duplicate technology slug: {tech.slug}")
            seen.add(tech.slug)
        return self

    @model_validator(mode="after")
    def _subdomains_declared(self) -> Self:
        for tech in self.technologies:
            if tech.subdomain not in self.subdomains:
                raise ValueError(
                    f"{tech.slug}: subdomain {tech.subdomain} is not declared in "
                    "the subdomains map"
                )
        return self

    @property
    def repository_full_names(self) -> list[str]:
        """Every distinct repository in the universe, sorted.

        Repositories may legitimately belong to several technologies, so this
        deduplicates before the ingestion worker plans its quota.
        """
        names = {r.full_name for t in self.technologies for r in t.repositories}
        return sorted(names)

    @property
    def headline_slugs(self) -> list[str]:
        """Technologies that receive the curated star-history backfill."""
        return [t.slug for t in self.technologies if t.headline]


def load_universe(path: Path | None = None) -> TechnologyUniverse:
    """Read and validate the universe file. Raises on any inconsistency."""
    target = path or DEFAULT_UNIVERSE_PATH
    if not target.exists():
        raise FileNotFoundError(f"technology universe not found at {target}")
    with target.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return TechnologyUniverse.model_validate(raw)
