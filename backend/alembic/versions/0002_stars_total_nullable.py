"""Make stars_total nullable in technology_signal_daily

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03

When no repository has a live stars snapshot for today, stars_total must be
NULL (distinct from 0 stars).  The aggregation layer now produces None
instead of 0 when stars data is unavailable, and the UI renders NULL as
an em dash via compact().
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "technology_signal_daily",
        "stars_total",
        existing_type=sa.Integer(),
        nullable=True,
        existing_server_default="0",
    )


def downgrade() -> None:
    op.alter_column(
        "technology_signal_daily",
        "stars_total",
        existing_type=sa.Integer(),
        nullable=False,
        existing_server_default="0",
    )
