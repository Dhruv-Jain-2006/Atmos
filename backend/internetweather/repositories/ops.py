"""Operational queries: is the observatory actually observing?"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from internetweather.models import IngestionRun


def latest_runs(session: Session, *, limit: int = 10) -> list[IngestionRun]:
    """Most recent run per (source, job).

    A window function rather than a query per job, so this stays one round trip
    as the number of data sources grows.
    """
    ranked = (
        select(
            IngestionRun,
            func.row_number()
            .over(
                partition_by=(IngestionRun.source, IngestionRun.job),
                order_by=IngestionRun.started_at.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    stmt = (
        select(IngestionRun)
        .join(ranked, ranked.c.id == IngestionRun.id)
        .where(ranked.c.rn == 1)
        .order_by(IngestionRun.started_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))
