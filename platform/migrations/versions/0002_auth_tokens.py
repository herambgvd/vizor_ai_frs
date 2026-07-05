"""auth token tables — refresh_tokens + password_reset_tokens

Revision ID: 0002_auth_tokens
Revises: 0001_baseline
Create Date: 2026-07-03

Adds the two tables backing refresh-token revocation and the forgot-password flow.
Uses create_all (checkfirst) so it only creates the new tables and leaves existing
ones untouched.
"""

from alembic import op

revision = "0002_auth_tokens"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _new_tables():
    from edge.auth.models import PasswordResetToken, RefreshToken

    return [RefreshToken.__table__, PasswordResetToken.__table__]


def upgrade() -> None:
    bind = op.get_bind()
    for table in _new_tables():
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_new_tables()):
        table.drop(bind, checkfirst=True)
