"""FRS Persons (gallery identity records + profile).

Revision ID: 0013_frs_persons
Revises: 0012_frs_groups
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_frs_persons"
down_revision = "0012_frs_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_persons",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("frs_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enrollment_status", sa.String(), nullable=False, server_default="unenrolled"),
        sa.Column("photo_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enrolled_photo_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("thumbnail_key", sa.String(), nullable=True),
        sa.Column("department", sa.String(), nullable=True),
        sa.Column("designation", sa.String(), nullable=True),
        sa.Column("contact_number", sa.String(), nullable=True),
        sa.Column("date_of_joining", sa.Date(), nullable=True),
        sa.Column("id_type", sa.String(), nullable=True),
        sa.Column("id_number", sa.String(), nullable=True),
        sa.Column("id_file_key", sa.String(), nullable=True),
        sa.Column("validity_start", sa.Date(), nullable=True),
        sa.Column("validity_end", sa.Date(), nullable=True),
        sa.Column("auto_remove", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_frs_persons_full_name", "frs_persons", ["full_name"])
    op.create_index("ix_frs_persons_external_id", "frs_persons", ["external_id"], unique=True)
    op.create_index("ix_frs_persons_group_id", "frs_persons", ["group_id"])
    op.create_index("ix_frs_persons_category", "frs_persons", ["category"])


def downgrade() -> None:
    for idx in ("ix_frs_persons_category", "ix_frs_persons_group_id", "ix_frs_persons_external_id", "ix_frs_persons_full_name"):
        op.drop_index(idx, table_name="frs_persons")
    op.drop_table("frs_persons")
