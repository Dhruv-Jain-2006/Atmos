"""initial schema: technology universe, repository facts, derived signals

Revision ID: 0001
Revises:
Create Date: 2026-08-26

Eight tables covering the first vertical slice:

    technology, repository, technology_repository, technology_relationship
    repository_metric_daily
    technology_signal_daily, ecosystem_event
    ingestion_run

Enum vocabularies are spelled out literally rather than imported from
``internetweather.enums``. A migration is a frozen snapshot: if it imported the
live enums, adding a vocabulary value later would retroactively change the DDL
this revision produces for anyone who has already applied it.
``backend/tests/test_schema.py`` asserts this revision still matches the models,
so the two cannot drift silently.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(*values: str, name: str) -> sa.Enum:
    """A vocabulary column: VARCHAR(32) plus a CHECK constraint.

    ``create_constraint`` must be explicit — SQLAlchemy defaults it to False,
    which yields an unconstrained VARCHAR.
    """
    return sa.Enum(
        *values, native_enum=False, create_constraint=True, length=32, name=name
    )


SUBDOMAIN = (
    "agentic_ai",
    "llm_ecosystem",
    "rag",
    "ai_infra",
    "multimodal",
    "mlops",
    "ai_security",
)
WEATHER_STATE = ("hot", "emerging", "stable", "cooling", "breaking", "storm")
REPO_RELATION = ("canonical", "implementation", "integration", "ecosystem")
RELATIONSHIP_TYPE = ("depends_on", "alternative_to", "complements", "co_occurs")
EVENT_TYPE = ("release", "star_spike", "anomaly", "new_repository", "archived", "renamed")
RECORD_SOURCE = ("curated", "discovered", "inferred")
TRACKING_STATE = ("active", "paused", "dropped")
EPISTEMIC_STATUS = ("observation", "inference", "hypothesis", "unknown")
INGESTION_STATUS = ("running", "succeeded", "failed", "quota_exhausted")


def upgrade() -> None:
    # ------------------------------------------------------------------
    # The universe
    # ------------------------------------------------------------------
    op.create_table(
        "technology",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("subdomain", _enum(*SUBDOMAIN, name="subdomain"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("source", _enum(*RECORD_SOURCE, name="recordsource"), nullable=False),
        sa.Column("headline", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(
        "ix_technology_subdomain_active", "technology", ["subdomain", "is_active"]
    )

    op.create_table(
        "repository",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("homepage", sa.Text(), nullable=True),
        sa.Column("primary_language", sa.String(length=60), nullable=True),
        sa.Column(
            "topics", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("license_spdx", sa.String(length=40), nullable=True),
        sa.Column("default_branch", sa.String(length=120), nullable=True),
        sa.Column("is_fork", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at_github", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pushed_at_github", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("forks", sa.Integer(), nullable=False),
        sa.Column("watchers", sa.Integer(), nullable=False),
        sa.Column("open_issues", sa.Integer(), nullable=False),
        sa.Column("etag", sa.String(length=120), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_sync_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "tracking_state", _enum(*TRACKING_STATE, name="trackingstate"), nullable=False
        ),
        sa.Column("source", _enum(*RECORD_SOURCE, name="recordsource"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_id"),
        sa.UniqueConstraint("full_name"),
    )
    op.create_index(
        "ix_repository_tracking_state_next_sync_after",
        "repository",
        ["tracking_state", "next_sync_after"],
    )

    op.create_table(
        "technology_repository",
        sa.Column("technology_id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("relation", _enum(*REPO_RELATION, name="reporelation"), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("source", _enum(*RECORD_SOURCE, name="recordsource"), nullable=False),
        sa.CheckConstraint("weight > 0 AND weight <= 1", name="weight_range"),
        sa.ForeignKeyConstraint(["technology_id"], ["technology.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repository.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("technology_id", "repository_id"),
    )
    op.create_index(
        "ix_technology_repository_repository_id", "technology_repository", ["repository_id"]
    )

    op.create_table(
        "technology_relationship",
        sa.Column("source_technology_id", sa.Integer(), nullable=False),
        sa.Column("target_technology_id", sa.Integer(), nullable=False),
        sa.Column(
            "relation_type",
            _enum(*RELATIONSHIP_TYPE, name="relationshiptype"),
            nullable=False,
        ),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("basis", _enum(*RECORD_SOURCE, name="recordsource"), nullable=False),
        sa.Column("computed_on", sa.Date(), nullable=True),
        sa.CheckConstraint("strength >= 0 AND strength <= 1", name="strength_range"),
        sa.CheckConstraint(
            "source_technology_id <> target_technology_id", name="no_self_edge"
        ),
        sa.ForeignKeyConstraint(
            ["source_technology_id"], ["technology.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_technology_id"], ["technology.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "source_technology_id", "target_technology_id", "relation_type"
        ),
    )
    op.create_index(
        "ix_technology_relationship_target_technology_id",
        "technology_relationship",
        ["target_technology_id"],
    )

    # ------------------------------------------------------------------
    # Ingested facts
    # ------------------------------------------------------------------
    op.create_table(
        "repository_metric_daily",
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=True),
        sa.Column("forks", sa.Integer(), nullable=True),
        sa.Column("watchers", sa.Integer(), nullable=True),
        sa.Column("open_issues", sa.Integer(), nullable=True),
        sa.Column("stars_delta", sa.Integer(), nullable=True),
        sa.Column("forks_delta", sa.Integer(), nullable=True),
        sa.Column("commits", sa.Integer(), nullable=True),
        sa.Column("releases", sa.Integer(), nullable=True),
        sa.Column("issues_opened", sa.Integer(), nullable=True),
        sa.Column("prs_merged", sa.Integer(), nullable=True),
        sa.Column("contributors_active", sa.Integer(), nullable=True),
        sa.Column("is_backfilled", sa.Boolean(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(stars IS NULL OR stars >= 0) AND (forks IS NULL OR forks >= 0)",
            name="non_negative_levels",
        ),
        sa.ForeignKeyConstraint(["repository_id"], ["repository.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("repository_id", "day"),
    )
    op.create_index("ix_repository_metric_daily_day", "repository_metric_daily", ["day"])

    # ------------------------------------------------------------------
    # Derived signals
    # ------------------------------------------------------------------
    op.create_table(
        "technology_signal_daily",
        sa.Column("technology_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "weather_state", _enum(*WEATHER_STATE, name="weatherstate"), nullable=False
        ),
        sa.Column("momentum", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("stars_total", sa.Integer(), nullable=False),
        sa.Column("stars_delta_1d", sa.Integer(), nullable=True),
        sa.Column("stars_delta_7d", sa.Integer(), nullable=True),
        sa.Column("stars_delta_28d", sa.Integer(), nullable=True),
        sa.Column("star_velocity_7d", sa.Float(), nullable=True),
        sa.Column("star_velocity_28d", sa.Float(), nullable=True),
        sa.Column("star_acceleration", sa.Float(), nullable=True),
        sa.Column("activity_score", sa.Float(), nullable=True),
        sa.Column("commit_velocity_7d", sa.Float(), nullable=True),
        sa.Column("release_count_28d", sa.Integer(), nullable=True),
        sa.Column("contributor_count_28d", sa.Integer(), nullable=True),
        sa.Column("repo_count", sa.Integer(), nullable=False),
        sa.Column("active_repo_count", sa.Integer(), nullable=False),
        sa.Column("anomaly_z", sa.Float(), nullable=True),
        sa.Column("sample_days", sa.Integer(), nullable=False),
        sa.Column("rank_overall", sa.Integer(), nullable=True),
        sa.Column("rank_subdomain", sa.Integer(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.CheckConstraint("momentum >= -1 AND momentum <= 1", name="momentum_range"),
        sa.ForeignKeyConstraint(["technology_id"], ["technology.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("technology_id", "day"),
    )
    op.create_index(
        "ix_technology_signal_daily_day_momentum",
        "technology_signal_daily",
        ["day", "momentum"],
    )
    op.create_index(
        "ix_technology_signal_daily_day_rank_overall",
        "technology_signal_daily",
        ["day", "rank_overall"],
    )

    op.create_table(
        "ecosystem_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("technology_id", sa.Integer(), nullable=True),
        sa.Column("repository_id", sa.Integer(), nullable=True),
        sa.Column("event_type", _enum(*EVENT_TYPE, name="eventtype"), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.String(length=280), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("magnitude", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "epistemic_status",
            _enum(*EPISTEMIC_STATUS, name="epistemicstatus"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("magnitude >= 0 AND magnitude <= 1", name="magnitude_range"),
        sa.ForeignKeyConstraint(["technology_id"], ["technology.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repository.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        "ix_ecosystem_event_occurred_on_magnitude",
        "ecosystem_event",
        ["occurred_on", "magnitude"],
    )
    op.create_index(
        "ix_ecosystem_event_technology_id_occurred_on",
        "ecosystem_event",
        ["technology_id", "occurred_on"],
    )

    # ------------------------------------------------------------------
    # Operational bookkeeping
    # ------------------------------------------------------------------
    op.create_table(
        "ingestion_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("job", sa.String(length=60), nullable=False),
        sa.Column("status", _enum(*INGESTION_STATUS, name="ingestionstatus"), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("api_calls", sa.Integer(), nullable=False),
        sa.Column("api_calls_saved", sa.Integer(), nullable=False),
        sa.Column("rate_limit_remaining", sa.Integer(), nullable=True),
        sa.Column("rate_limit_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_read", sa.Integer(), nullable=False),
        sa.Column("records_written", sa.Integer(), nullable=False),
        sa.Column(
            "cursor",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ingestion_run_source_job_started_at",
        "ingestion_run",
        ["source", "job", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("ingestion_run")
    op.drop_table("ecosystem_event")
    op.drop_table("technology_signal_daily")
    op.drop_table("repository_metric_daily")
    op.drop_table("technology_relationship")
    op.drop_table("technology_repository")
    op.drop_table("repository")
    op.drop_table("technology")
