"""Shared worker runtime.

Workers are where all the expensive work lives (locked decision #6): ingestion,
statistics, retention. They run under GitHub Actions on a schedule, not inside a
request.

Everything a worker does is recorded in ``ingestion_run``. That is not
housekeeping — it is how the next run knows what quota was already spent and
where the previous one stopped.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from internetweather.config import get_settings
from internetweather.db import worker_session
from internetweather.enums import IngestionStatus
from internetweather.models import IngestionRun


def configure_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        stream=sys.stderr,
    )


@dataclass
class RunStats:
    """Mutable counters a worker updates as it goes."""

    api_calls: int = 0
    #: Requests avoided by a 304 or an unexpired backoff. Free-tier hygiene is
    #: only measurable if the savings are counted too.
    api_calls_saved: int = 0
    records_read: int = 0
    records_written: int = 0
    rate_limit_remaining: int | None = None
    rate_limit_reset_at: datetime | None = None
    cursor: dict = field(default_factory=dict)
    outcome: IngestionStatus | None = None


class RunFailed(RuntimeError):
    """A completed worker run whose partial output is safe to commit.

    Some ingestion jobs can make useful, idempotent progress before one or
    more inputs fail. Raising an ordinary exception would roll back both that
    progress and the ``ingestion_run`` record, making the failure invisible to
    operators. Workers use this after recording their cursor and failure
    summary; ``tracked_run`` commits those facts with FAILED status.
    """


@contextmanager
def tracked_run(source: str, job: str) -> Iterator[tuple[Session, RunStats]]:
    """Run a worker job inside a recorded, committed transaction.

    On success the run is SUCCEEDED. On ``QuotaExhausted`` it is
    QUOTA_EXHAUSTED with its cursor preserved, so the next scheduled run resumes
    instead of restarting and re-spending quota. On any other exception it is
    FAILED with the error, and the exception propagates so CI goes red.
    """
    stats = RunStats()
    with worker_session() as session:
        run = IngestionRun(source=source, job=job, status=IngestionStatus.RUNNING)
        session.add(run)
        session.flush()

        try:
            yield session, stats
        except QuotaExhausted as exc:
            run.status = IngestionStatus.QUOTA_EXHAUSTED
            stats.outcome = run.status
            run.error = str(exc)
        except RunFailed as exc:
            run.status = IngestionStatus.FAILED
            stats.outcome = run.status
            run.error = str(exc)
        except Exception as exc:
            run.status = IngestionStatus.FAILED
            stats.outcome = run.status
            run.error = f"{type(exc).__name__}: {exc}"
            _finalise(run, stats)
            raise
        else:
            run.status = IngestionStatus.SUCCEEDED
            stats.outcome = run.status

        _finalise(run, stats)


def _finalise(run: IngestionRun, stats: RunStats) -> None:
    run.finished_at = datetime.now(UTC)
    run.api_calls = stats.api_calls
    run.api_calls_saved = stats.api_calls_saved
    run.records_read = stats.records_read
    run.records_written = stats.records_written
    run.rate_limit_remaining = stats.rate_limit_remaining
    run.rate_limit_reset_at = stats.rate_limit_reset_at
    run.cursor = stats.cursor


class QuotaExhausted(RuntimeError):
    """Raised when a worker stops early to stay inside a free-tier limit.

    Not an error condition. Stopping deliberately at a budget and resuming next
    run is the designed behaviour; exhausting the hour's requests and getting
    throttled is not.
    """


def pending(job: str, plan: str) -> int:
    """Exit cleanly from a worker that is scaffolded but not yet implemented.

    Prints the intended behaviour rather than a bare NotImplementedError, so the
    scheduled workflow is self-documenting about what is missing.
    """
    configure_logging()
    logging.getLogger(job).warning("not implemented in this slice\n\nPlanned: %s", plan)
    return os.EX_OK if hasattr(os, "EX_OK") else 0


def require_database(job: str) -> bool:
    """Report an unconfigured database as a one-line message, not a traceback.

    A worker with no DATABASE_URL has nothing to do. That is an operator
    condition, not a crash, and a stack trace in the Actions log obscures the one
    fact that matters.
    """
    if get_settings().database_configured:
        return True
    configure_logging()
    logging.getLogger(job).error(
        "no database configured; set DATABASE_URL_DIRECT or DATABASE_URL "
        "(see .env.example). Nothing to do."
    )
    return False
