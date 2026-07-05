"""Account hub: user preferences + refresh-token session context.

Revision ID: 0005_account_prefs_sessions
Revises: 0004_user_avatar
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_account_prefs_sessions"
down_revision = "0004_user_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("preferences", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("refresh_tokens", sa.Column("user_agent", sa.String(), nullable=True))
    op.add_column("refresh_tokens", sa.Column("ip", sa.String(), nullable=True))
    op.add_column("refresh_tokens", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("refresh_tokens", "last_used_at")
    op.drop_column("refresh_tokens", "ip")
    op.drop_column("refresh_tokens", "user_agent")
    op.drop_column("users", "preferences")
