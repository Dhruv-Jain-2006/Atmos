"""Column helpers shared by the ORM models."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import mapped_column


def enum_column(enum_cls: type[StrEnum], **kwargs):
    """A StrEnum column stored as VARCHAR with a CHECK constraint.

    ``native_enum=False`` is deliberate. Native PostgreSQL enum types require
    ``ALTER TYPE`` to add a value, which is awkward in migrations and cannot run
    inside some transaction contexts. A checked VARCHAR gives the same integrity
    guarantee and lets us add vocabulary with an ordinary constraint change.
    """
    return mapped_column(
        SAEnum(
            enum_cls,
            native_enum=False,
            # SQLAlchemy defaults this to False, which would silently give a
            # plain VARCHAR with no integrity guarantee at all.
            create_constraint=True,
            length=32,
            # Named explicitly rather than derived, so the CHECK constraint name
            # is stable across SQLAlchemy versions and matches the migration.
            name=enum_cls.__name__.lower(),
            values_callable=lambda e: [member.value for member in e],
        ),
        **kwargs,
    )
