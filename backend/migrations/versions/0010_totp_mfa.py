"""Two-factor auth: TOTP secret + enabled flag + recovery codes.

Revision ID: 0010_totp_mfa
Revises: 0009_account_security
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_totp_mfa"
down_revision = "0009_account_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("mfa_recovery_codes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_recovery_codes")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
