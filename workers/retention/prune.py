"""Prune data that has outlived its analytical usefulness.

Neon's free tier caps storage at 0.5 GB. At the current scale (144 repositories,
45 technologies) the daily fact tables add roughly 10 MB per year, so this is not
yet load-bearing — it exists now because retention is much easier to get right
before there is data than after the cap is hit, and because repository count is
the thing most likely to grow tenfold.

What is kept and why:

* ``repository_metric_daily`` — 400 days. Slightly over a year so a
  year-over-year comparison always has a counterpart day.
* ``ingestion_run`` — 60 days. Operational telemetry, not evidence.
* ``technology_signal_daily`` — never pruned. ~45 rows a day; this is the
  product's history and the Research page reads it.
* ``ecosystem_event`` — never pruned. Events are observations with evidence.

    uv run python -m workers.retention.prune --dry-run
    uv run python -m workers.retention.prune
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text

from internetweather.models import IngestionRun, RepositoryMetricDaily
from workers._runtime import configure_logging, require_database, tracked_run

log = logging.getLogger("retention.prune")

METRIC_RETENTION_DAYS = 400
RUN_RETENTION_DAYS = 60


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be deleted without deleting it",
    )
    args = parser.parse_args(argv)
    configure_logging()

    if not require_database("retention.prune"):
        return 2

    today = datetime.now(UTC).date()
    metric_cutoff = today - timedelta(days=METRIC_RETENTION_DAYS)
    run_cutoff = datetime.now(UTC) - timedelta(days=RUN_RETENTION_DAYS)

    with tracked_run(source="internal", job="retention_prune") as (session, stats):
        stale_metrics = session.scalar(
            select(func.count())
            .select_from(RepositoryMetricDaily)
            .where(RepositoryMetricDaily.day < metric_cutoff)
        )
        stale_runs = session.scalar(
            select(func.count())
            .select_from(IngestionRun)
            .where(IngestionRun.started_at < run_cutoff)
        )
        stats.records_read = (stale_metrics or 0) + (stale_runs or 0)

        log.info(
            "metrics before %s: %d rows | runs before %s: %d rows",
            metric_cutoff,
            stale_metrics or 0,
            run_cutoff.date(),
            stale_runs or 0,
        )
        _report_sizes(session)

        if args.dry_run:
            log.info("dry run: nothing deleted")
            return 0

        session.execute(
            delete(RepositoryMetricDaily).where(RepositoryMetricDaily.day < metric_cutoff)
        )
        # Never delete the row describing this run.
        session.execute(
            delete(IngestionRun).where(IngestionRun.started_at < run_cutoff)
        )
        stats.records_written = stats.records_read
        stats.cursor = {"metric_cutoff": metric_cutoff.isoformat()}

    return 0


def _report_sizes(session) -> None:
    """Log per-table size so the storage budget is observable, not guessed."""
    rows = session.execute(
        text(
            """
            SELECT relname,
                   pg_total_relation_size(c.oid) AS bytes
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            ORDER BY bytes DESC
            """
        )
    ).all()
    total = sum(row.bytes for row in rows)
    for row in rows:
        log.info("  %-28s %8.1f KB", row.relname, row.bytes / 1024)
    log.info("total %.1f MB of the 512 MB free-tier budget", total / 1024 / 1024)


if __name__ == "__main__":
    sys.exit(main())
