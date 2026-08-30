"""One-off historical star backfill for headline technologies (locked decision #13).

Scaffolded, not implemented in this slice.

    uv run python -m workers.github.backfill_stars
"""

from __future__ import annotations

import sys

from workers._runtime import pending

PLAN = """
Why this exists: activity-first signals work from day one, but a trend line needs
a past. Without a backfill, every technology reads "insufficient history" for the
first four weeks and the Trends page has nothing honest to show.

Scope is deliberately small — the 9 headline technologies only, because the
stargazer API costs one request per 100 stars. A 60,000-star repository is 600
requests; the whole 144-repo universe would be six figures.

Per headline technology's canonical repository:
  GET /repos/{o}/{n}/stargazers with Accept: application/vnd.github.star+json
    → paginate, bucket starred_at by day, emit cumulative daily totals.
    → binary-search the page space instead of walking it: we need ~400 daily
      boundary points, not every individual star.

Written to repository_metric_daily with is_backfilled=TRUE. That flag is not
cosmetic — a reconstructed level must never be mistaken for direct observation,
and the confidence term in the classifier reads it.

Runs once (guarded by an ingestion_run lookup), and never in the hourly schedule.
"""


def main(argv: list[str] | None = None) -> int:
    return pending("github.backfill_stars", PLAN)


if __name__ == "__main__":
    sys.exit(main())
