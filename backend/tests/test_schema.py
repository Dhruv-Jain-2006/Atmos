"""Guards that the hand-written migration still matches the ORM models.

The initial migration was written by hand because there is no database to
autogenerate against yet. That is only safe if something checks it. Both sides
are rendered to PostgreSQL DDL through the same compiler and compared, so a
column added to a model without a migration fails here rather than in
production. Neither side needs a database.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from internetweather.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]


def _statements(sql: str) -> dict[str, str]:
    """Split DDL into {statement key: normalised body}, order-insensitively."""
    # Drop SQL comments: Alembic prefixes each revision's DDL with a
    # `-- Running upgrade` line that would otherwise hide the first statement.
    sql = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )

    out: dict[str, str] = {}
    for raw in sql.split(";"):
        stmt = " ".join(raw.split())
        if not stmt.upper().startswith(("CREATE TABLE", "CREATE INDEX")):
            continue
        if "alembic_version" in stmt:
            continue

        if stmt.upper().startswith("CREATE INDEX"):
            key = stmt.split()[2]
            out[f"index:{key}"] = stmt
            continue

        # CREATE TABLE name ( a, b, c ) -> sort the inner clauses, because
        # column and constraint ordering is not a correctness property.
        match = re.match(r"CREATE TABLE (\w+) \((.*)\)$", stmt)
        assert match, f"unparsed statement: {stmt}"
        name, body = match.group(1), match.group(2)
        clauses = sorted(part.strip() for part in _split_top_level(body))
        out[f"table:{name}"] = " | ".join(clauses)
    return out


def _split_top_level(body: str) -> list[str]:
    """Split on commas that are not inside parentheses."""
    parts, depth, current = [], 0, []
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _from_models() -> dict[str, str]:
    dialect = postgresql.dialect()
    chunks = []
    for table in Base.metadata.sorted_tables:
        chunks.append(str(CreateTable(table).compile(dialect=dialect)) + ";")
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            chunks.append(str(CreateIndex(index).compile(dialect=dialect)) + ";")
    return _statements("\n".join(chunks))


def _from_migrations() -> dict[str, str]:
    buffer = io.StringIO()
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.stdout = buffer
    # sql=True is offline mode: renders DDL without connecting to anything.
    command.upgrade(config, "head", sql=True)
    return _statements(buffer.getvalue())


@pytest.fixture(scope="module")
def rendered() -> tuple[dict[str, str], dict[str, str]]:
    return _from_models(), _from_migrations()


def test_same_objects(rendered):
    models, migrations = rendered
    assert set(models) == set(migrations), (
        "Schema objects differ between models and migrations.\n"
        f"  only in models:     {sorted(set(models) - set(migrations))}\n"
        f"  only in migrations: {sorted(set(migrations) - set(models))}"
    )


def test_same_definitions(rendered):
    models, migrations = rendered
    for key in sorted(models):
        assert models[key] == migrations[key], f"definition drift in {key}"


def test_every_table_has_named_primary_key():
    for table in Base.metadata.sorted_tables:
        assert table.primary_key.columns, f"{table.name} has no primary key"
        assert table.primary_key.name == f"pk_{table.name}"


def test_enum_columns_are_checked_varchar():
    """No native PostgreSQL enums, and no unconstrained vocabulary columns."""
    checks = {
        constraint.name
        for table in Base.metadata.sorted_tables
        for constraint in table.constraints
        if type(constraint).__name__ == "CheckConstraint"
    }
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            enum_type = getattr(column.type, "enums", None)
            if enum_type is None:
                continue
            assert column.type.native_enum is False, (
                f"{table.name}.{column.name} uses a native PostgreSQL enum; "
                "ALTER TYPE migrations are the thing we are avoiding"
            )
            expected = f"ck_{table.name}_{column.type.name}"
            assert expected in checks, (
                f"{table.name}.{column.name} has no CHECK constraint "
                f"(expected {expected})"
            )
