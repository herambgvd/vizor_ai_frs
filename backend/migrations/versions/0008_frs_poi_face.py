"""FRS: multiple enrolled faces per POI.

Revision ID: 0008_frs_poi_face
Revises: 0007_frs_domain
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_frs_poi_face"
down_revision = "0007_frs_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_poi_face",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("poi_id", sa.Uuid(), sa.ForeignKey("frs_poi.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("img_key", sa.String(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("face_score", sa.Float(), nullable=True),
        sa.Column("forced_reason", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("qdrant_point_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("frs_poi_face")
