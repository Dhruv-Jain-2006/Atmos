"""Discover repositories the curated universe does not yet know about.

Scaffolded, not implemented in this slice.

    uv run python -m workers.github.discover
"""

from __future__ import annotations

import sys

from workers._runtime import pending

PLAN = """
Input: the `discovery` block on each technology in technology_universe.yml
(topics, orgs, queries). Discovery is bounded by editorial intent — it does not
crawl GitHub.

  GET /search/repositories?q=topic:{topic}+stars:>{floor}&sort=updated
    → the search endpoint has its own 30 requests/minute limit, separate from
      the core 5,000/hour, so it is paced independently.

A candidate is proposed, not adopted: written with source=DISCOVERED and
tracking_state=PAUSED (attached, but not yet polled), and linked at
relation=ECOSYSTEM (weight 0.25) so it cannot move a technology's weather before
a human confirms it. Promotion to ACTIVE, and to IMPLEMENTATION or INTEGRATION,
is an edit to the YAML.

That asymmetry is the point — automated discovery widens what we watch; it does
not get to redefine what a technology is.
"""


def main(argv: list[str] | None = None) -> int:
    return pending("github.discover", PLAN)


if __name__ == "__main__":
    sys.exit(main())
