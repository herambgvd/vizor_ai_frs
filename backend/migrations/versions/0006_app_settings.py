"""System settings key/value store.

Revision ID: 0006_app_settings
Revises: 0005_account_prefs_sessions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_app_settings"
down_revision = "0005_account_prefs_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
