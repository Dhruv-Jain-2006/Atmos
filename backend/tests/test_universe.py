"""The curated universe is a product artifact, so it is tested like one."""

from __future__ import annotations

import pytest

from internetweather.enums import RepoRelation, Subdomain
from internetweather.universe import DEFAULT_WEIGHTS, load_universe


@pytest.fixture(scope="module")
def universe():
    return load_universe()


def test_loads_and_validates(universe):
    assert universe.version == 1
    assert universe.domain == "ai-engineering"


def test_covers_every_subdomain(universe):
    """A subdomain with no technologies would render as an empty Trends filter."""
    declared = set(universe.subdomains)
    assert declared == set(Subdomain), "subdomains map must match the Subdomain enum"

    populated = {t.subdomain for t in universe.technologies}
    assert declared == populated, f"subdomains with no technologies: {declared - populated}"


def test_scale_matches_the_agreed_slice(universe):
    """~40 technologies, ~150 repositories (locked decision #14).

    Bounds, not exact numbers: the point is to catch accidental drift into
    thousands of repositories, which would break the ingestion quota budget.
    """
    assert 35 <= len(universe.technologies) <= 55
    assert 120 <= len(universe.repository_full_names) <= 200


def test_headline_set_stays_small(universe):
    """Headline technologies get a star-history backfill, which is expensive.

    Stargazer history paginates at 100 per request, so one 140k-star repository
    costs ~1,400 of the 5,000 requests available per hour.
    """
    assert 5 <= len(universe.headline_slugs) <= 12


def test_weights_follow_relation_defaults(universe):
    """Weights should be deliberate, not arbitrary."""
    for tech in universe.technologies:
        for repo in tech.repositories:
            expected = DEFAULT_WEIGHTS[repo.relation]
            assert repo.weight <= expected + 1e-9, (
                f"{tech.slug}/{repo.full_name}: weight {repo.weight} exceeds the "
                f"{repo.relation} ceiling of {expected}"
            )


def test_every_technology_has_a_canonical_repository(universe):
    for tech in universe.technologies:
        canonical = [r for r in tech.repositories if r.relation is RepoRelation.CANONICAL]
        assert canonical, f"{tech.slug} has no canonical repository"


def test_every_technology_is_discoverable(universe):
    """Discovery hints are how the universe grows beyond what we hand-listed."""
    for tech in universe.technologies:
        hints = tech.discovery
        assert hints.topics or hints.orgs or hints.queries, (
            f"{tech.slug} has no discovery hints, so it can never gain new repositories"
        )


def test_aliases_do_not_collide_across_technologies(universe):
    """Colliding aliases would misattribute mentions during signal extraction."""
    owners: dict[str, str] = {}
    for tech in universe.technologies:
        for alias in [tech.name, *tech.aliases]:
            key = alias.strip().lower()
            if key in owners and owners[key] != tech.slug:
                pytest.fail(f"alias {alias!r} claimed by both {owners[key]} and {tech.slug}")
            owners[key] = tech.slug
