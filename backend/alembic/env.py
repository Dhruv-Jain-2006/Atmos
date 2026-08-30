"""Alembic environment.

Two properties matter here:

* The URL comes from ``Settings``, not ``alembic.ini`` — one place reads secrets.
* Offline mode works with no database at all. ``alembic upgrade head --sql``
  renders the full schema as PostgreSQL DDL, which is how the schema is reviewed
  and tested before a Neon project exists.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Ensure `backend/` is importable when Alembic is invoked from the repo root.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from internetweather.config import get_settings  # noqa: E402
from internetweather.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate diffs against this, and op.create_table inherits its
# naming_convention so hand-written migrations get the same constraint names.
target_metadata = Base.metadata

#: Used only for `--sql` rendering. Offline mode never opens a connection; the
#: URL exists solely to select the PostgreSQL dialect.
OFFLINE_PLACEHOLDER_URL = "postgresql+psycopg://render@localhost:5432/internetweather"


def _database_url(*, required: bool) -> str:
    url = get_settings().worker_database_url
    if url:
        return url
    if required:
        raise RuntimeError(
            "Alembic needs a database URL. Set DATABASE_URL_DIRECT (preferred) "
            "or DATABASE_URL in .env — see .env.example. To inspect the schema "
            "without a database, run: alembic upgrade head --sql"
        )
    return OFFLINE_PLACEHOLDER_URL


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(required=False),
        target_metadata=target_metadata,
        # Route rendered DDL through the Alembic config so callers (notably
        # backend/tests/test_schema.py) can capture it instead of stdout.
        output_buffer=config.stdout,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        _database_url(required=True),
        # Migrations are a one-shot process; a pool would just hold Neon awake.
        poolclass=pool.NullPool,
        future=True,
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
