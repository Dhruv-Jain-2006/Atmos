"""Load ``db/seed/technology_universe.yml`` into the ``technology`` table.

Technologies only. Repository rows are deliberately NOT created here, because a
repository's identity is its immutable GitHub numeric id and this file only knows
``owner/name``. Inventing a placeholder id would put a fake identity into the one
column the whole ingestion path trusts. ``workers.github.resolve`` reads the same
YAML, asks GitHub for the real ids, and writes the repository and link rows.

Idempotent: re-running updates editorial fields in place and never duplicates or
renames a slug.

    uv run python -m workers.seed.load_universe --dry-run   # no database needed
    uv run python -m workers.seed.load_universe
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import select

from internetweather.enums import RecordSource
from internetweather.models import Technology
from internetweather.universe import SeedTechnology, load_universe
from workers._runtime import configure_logging, require_database, tracked_run

log = logging.getLogger("seed.universe")


def _apply(row: Technology, seed: SeedTechnology) -> bool:
    """Copy editorial fields onto an existing row. Returns True if anything changed.

    ``slug`` is never written — it is the identity, and a published URL.
    """
    changes = {
        "name": seed.name,
        "subdomain": seed.subdomain,
        "summary": seed.summary,
        "aliases": list(seed.aliases),
        "headline": seed.headline,
    }
    changed = False
    for field, value in changes.items():
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed = True
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the universe file and print the plan without touching the database",
    )
    args = parser.parse_args(argv)

    configure_logging()
    universe = load_universe()

    log.info(
        "universe v%s (%s, updated %s): %d technologies, %d repositories, %d headline",
        universe.version,
        universe.domain,
        universe.updated,
        len(universe.technologies),
        len(universe.repository_full_names),
        len(universe.headline_slugs),
    )

    if args.dry_run:
        for subdomain, meta in universe.subdomains.items():
            members = [t.slug for t in universe.technologies if t.subdomain is subdomain]
            log.info("  %-14s %2d  %s", subdomain.value, len(members), meta.name)
        log.info("dry run: no rows written")
        return 0

    if not require_database("seed.universe"):
        return 2

    with tracked_run(source="seed", job="load_universe") as (session, stats):
        existing = {
            row.slug: row for row in session.scalars(select(Technology)).all()
        }
        stats.records_read = len(universe.technologies)

        created = updated = 0
        for seed in universe.technologies:
            row = existing.get(seed.slug)
            if row is None:
                row = Technology(slug=seed.slug, source=RecordSource.CURATED)
                _apply(row, seed)
                session.add(row)
                created += 1
            elif _apply(row, seed):
                updated += 1

        # A technology removed from the YAML is retired, not deleted: its
        # historical signals and events stay valid observations.
        seeded = {t.slug for t in universe.technologies}
        retired = 0
        for slug, row in existing.items():
            if slug not in seeded and row.is_active:
                row.is_active = False
                retired += 1

        stats.records_written = created + updated + retired
        log.info(
            "created=%d updated=%d retired=%d unchanged=%d",
            created,
            updated,
            retired,
            len(universe.technologies) - created - updated,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
