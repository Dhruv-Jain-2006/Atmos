"""Database engine and session management.

Design constraint (locked decision #5): the API layer is STATELESS and
SUB-SECOND. That drives two choices here:

1. ``NullPool`` for the API. Neon's PgBouncer endpoint already pools, and the
   API may run as short-lived serverless invocations where a per-process pool
   is dead weight that also holds Neon compute awake.
2. Lazy engine creation. Importing this module must not open a socket, so the
   app boots with no ``DATABASE_URL`` and reports degraded mode instead of
   failing.

Workers use ``worker_engine()`` — they are long-running, do bulk writes, and
should use the direct (non-pooled) endpoint.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from internetweather.config import get_settings

_api_engine: Engine | None = None
_worker_engine: Engine | None = None


def api_engine() -> Engine | None:
    """Engine for read endpoints, or None when no database is configured."""
    global _api_engine
    if _api_engine is not None:
        return _api_engine

    url = get_settings().api_database_url
    if not url:
        return None

    _api_engine = create_engine(
        url,
        poolclass=NullPool,
        pool_pre_ping=True,
        # Fail fast rather than hanging a request while Neon wakes from
        # scale-to-zero; the endpoint degrades instead.
        connect_args={"connect_timeout": 10},
    )
    return _api_engine


def worker_engine() -> Engine:
    """Engine for workers and migrations. Raises if unconfigured."""
    global _worker_engine
    if _worker_engine is not None:
        return _worker_engine

    url = get_settings().worker_database_url
    if not url:
        raise RuntimeError(
            "No database configured. Set DATABASE_URL_DIRECT (preferred) or "
            "DATABASE_URL in your .env - see .env.example."
        )

    _worker_engine = create_engine(url, pool_pre_ping=True, future=True)
    return _worker_engine


async def get_session() -> AsyncIterator[Session | None]:
    """FastAPI dependency yielding a session, or None in degraded mode.

    Routers must handle ``None`` explicitly — that is what makes degraded mode
    an intentional product state rather than a 500.
    """
    engine = api_engine()
    if engine is None:
        yield None
        return

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def worker_session() -> Iterator[Session]:
    """Transactional session for workers. Commits on success, rolls back on error."""
    factory = sessionmaker(bind=worker_engine(), expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connectivity() -> tuple[bool, str | None]:
    """Cheap liveness probe used by /health. Returns (ok, error_message)."""
    engine = api_engine()
    if engine is None:
        return False, "DATABASE_URL not configured"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


async def check_db() -> tuple[bool, str | None]:
    """FastAPI dependency wrapping :func:`check_connectivity`.

    Extracted so tests can override the database liveness check without needing
    a real connection — the same pattern used by :func:`get_session`.
    """
    return check_connectivity()
