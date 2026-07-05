"""Add users.avatar_key (profile picture storage key).

Revision ID: 0004_user_avatar
Revises: 0003_user_email_verified
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_user_avatar"
down_revision = "0003_user_email_verified"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_key", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_key")
