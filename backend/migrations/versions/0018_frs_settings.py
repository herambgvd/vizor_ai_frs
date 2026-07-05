"""FRS feature settings singleton (public dashboard + ingest API toggles).

Revision ID: 0018_frs_settings
Revises: 0017_frs_reports
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_frs_settings"
down_revision = "0017_frs_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_settings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("public_dashboard_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("public_show_names", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ingest_api_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ingest_api_key", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("frs_settings")
