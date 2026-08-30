"""Technology universe: technologies, their repository sensors, and edges."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from internetweather.enums import (
    RecordSource,
    RelationshipType,
    RepoRelation,
    Subdomain,
)
from internetweather.models._columns import enum_column
from internetweather.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from internetweather.models.repository import Repository


class Technology(Base, TimestampMixin):
    """A technology we observe. The unit of analysis for the whole product."""

    __tablename__ = "technology"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    #: Stable public identifier used in URLs. Never reused, never renamed.
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    subdomain: Mapped[Subdomain] = enum_column(Subdomain, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    #: Alternate spellings used for mention matching in READMEs and papers.
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )

    source: Mapped[RecordSource] = enum_column(
        RecordSource, nullable=False, default=RecordSource.CURATED
    )
    #: Receives the curated star-history backfill so it has a day-one trend line.
    headline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    repositories: Mapped[list[TechnologyRepository]] = relationship(
        back_populates="technology", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_technology_subdomain_active", "subdomain", "is_active"),
    )


class TechnologyRepository(Base):
    """Weighted link from a technology to a repository that senses it.

    ``weight`` stops a huge ecosystem repo (an awesome-list) from dominating the
    aggregate signal of a technology whose real centre is its spec repo.
    """

    __tablename__ = "technology_repository"

    technology_id: Mapped[int] = mapped_column(
        ForeignKey("technology.id", ondelete="CASCADE"), primary_key=True
    )
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repository.id", ondelete="CASCADE"), primary_key=True
    )

    relation: Mapped[RepoRelation] = enum_column(RepoRelation, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[RecordSource] = enum_column(
        RecordSource, nullable=False, default=RecordSource.CURATED
    )

    technology: Mapped[Technology] = relationship(back_populates="repositories")
    repository: Mapped[Repository] = relationship(back_populates="technologies")

    __table_args__ = (
        CheckConstraint("weight > 0 AND weight <= 1", name="weight_range"),
        # Reverse lookup: "which technologies does this repo sense?"
        Index("ix_technology_repository_repository_id", "repository_id"),
    )


class TechnologyRelationship(Base):
    """Directed, weighted edge between two technologies.

    Powers "related technologies" on the Research page and, later, the Explore
    graph. Edges are computed (co-occurrence, dependencies) or curated — never
    invented by an LLM.
    """

    __tablename__ = "technology_relationship"

    source_technology_id: Mapped[int] = mapped_column(
        ForeignKey("technology.id", ondelete="CASCADE"), primary_key=True
    )
    target_technology_id: Mapped[int] = mapped_column(
        ForeignKey("technology.id", ondelete="CASCADE"), primary_key=True
    )
    relation_type: Mapped[RelationshipType] = enum_column(
        RelationshipType, primary_key=True
    )

    strength: Mapped[float] = mapped_column(Float, nullable=False)
    basis: Mapped[RecordSource] = enum_column(RecordSource, nullable=False)
    computed_on: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        CheckConstraint("strength >= 0 AND strength <= 1", name="strength_range"),
        CheckConstraint(
            "source_technology_id <> target_technology_id", name="no_self_edge"
        ),
        Index("ix_technology_relationship_target_technology_id", "target_technology_id"),
    )
