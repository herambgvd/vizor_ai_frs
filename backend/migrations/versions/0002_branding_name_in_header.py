"""Add branding.name_in_header (show app name as header wordmark).

Revision ID: 0002_branding_name_in_header
Revises: 0001_frs_baseline
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_branding_name_in_header"
down_revision = "0001_frs_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "branding",
        sa.Column("name_in_header", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("branding", "name_in_header")
