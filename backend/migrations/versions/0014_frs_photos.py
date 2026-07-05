"""FRS Photos (enrolled face samples).

Revision ID: 0014_frs_photos
Revises: 0013_frs_persons
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_frs_photos"
down_revision = "0013_frs_persons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_photos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("frs_persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("thumbnail_key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("embedding_id", sa.String(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("liveness_score", sa.Float(), nullable=True),
        sa.Column("sharpness_score", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_frs_photos_person_id", "frs_photos", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_frs_photos_person_id", table_name="frs_photos")
    op.drop_table("frs_photos")
