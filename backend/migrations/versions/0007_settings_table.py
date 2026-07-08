"""platform settings table — app_settings

Revision ID: 0007_settings_table
Revises: 0006_frs_analyze_width
Create Date: 2026-07-08

The baseline migration was generated before ``edge.settings.models`` was imported on
Base.metadata, so the platform ``app_settings`` table (backing GET /settings/public
and the Settings pages) was never created in this scenario's DB — every settings read
500s. This migration registers that model and create_all(checkfirst)s the missing
table, leaving all existing tables untouched.
"""

from alembic import op

revision = "0007_settings_table"
down_revision = "0006_frs_analyze_width"
branch_labels = None
depends_on = None


def _metadata():
    # Import inside the function so the model registers on Base.metadata at run time.
    from edge.db.base import Base
    import edge.settings.models  # noqa: F401 — registers app_settings

    return Base.metadata


def upgrade() -> None:
    # checkfirst=True (create_all default) → only creates app_settings if absent.
    _metadata().create_all(op.get_bind())


def downgrade() -> None:
    op.drop_table("app_settings")
