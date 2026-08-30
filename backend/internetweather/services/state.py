"""Read orchestration for the API.

Services own two responsibilities routers must not:

* Composing repository queries into a page payload in a bounded number of
  round trips.
* Degradation. Every service accepts ``Session | None`` and returns a valid,
  honest payload when there is no database. That is what makes "no data yet" a
  product state instead of a 500.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from internetweather.config import get_settings
from internetweather.repositories import signals as signal_repo
from internetweather.schemas.common import DataFreshness

#: Shown before the first ingestion run has produced anything.
NO_DATA_YET = "No signals computed yet — awaiting the first ingestion run."


def degraded() -> DataFreshness:
    """Freshness for a request served without a database."""
    settings = get_settings()
    reason = (
        "DATABASE_URL is not configured; the API is serving contracts only."
        if not settings.database_configured
        else "The database is configured but unreachable."
    )
    return DataFreshness(as_of=None, observed_days=0, has_data=False, degraded_reason=reason)


def freshness(session: Session, day: date | None) -> DataFreshness:
    observed = signal_repo.observed_day_count(session)
    if day is None:
        return DataFreshness(
            as_of=None, observed_days=observed, has_data=False, degraded_reason=NO_DATA_YET
        )
    return DataFreshness(
        as_of=day.isoformat(), observed_days=observed, has_data=True, degraded_reason=None
    )
