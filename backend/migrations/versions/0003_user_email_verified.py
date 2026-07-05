"""Add users.email_verified.

Revision ID: 0003_user_email_verified
Revises: 0002_branding_name_in_header
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_user_email_verified"
down_revision = "0002_branding_name_in_header"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified")
