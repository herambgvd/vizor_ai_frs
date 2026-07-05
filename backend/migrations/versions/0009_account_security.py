"""Account security: lockout counters + password lifecycle columns.

Revision ID: 0009_account_security
Revises: 0008_frs_poi_face
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_account_security"
down_revision = "0008_frs_poi_face"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_history", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "password_history")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
