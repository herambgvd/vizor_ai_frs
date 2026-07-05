"""FRS Groups (watchlists) table.

Revision ID: 0012_frs_groups
Revises: 0011_drop_legacy_frs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_frs_groups"
down_revision = "0011_drop_legacy_frs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("group_type", sa.String(), nullable=False, server_default="watchlist"),
        sa.Column("color_code", sa.String(), nullable=False, server_default="#ef4444"),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("alert_sound", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_frs_groups_name", "frs_groups", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_frs_groups_name", table_name="frs_groups")
    op.drop_table("frs_groups")
