"""FRS cameras (face-recognition video sources).

Revision ID: 0019_frs_cameras
Revises: 0018_frs_settings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_frs_cameras"
down_revision = "0018_frs_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_cameras",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("rtsp_url", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("zone", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("recognition_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("min_confidence", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("fps", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("min_face_px", sa.Integer(), nullable=False, server_default=sa.text("40")),
        sa.Column("direction", sa.String(), nullable=False, server_default="both"),
        sa.Column("hw_accel", sa.String(), nullable=False, server_default="none"),
        sa.Column("roi", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(), nullable=False, server_default="offline"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("snapshot_key", sa.String(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_frs_cameras_name", "frs_cameras", ["name"])
    op.create_index("ix_frs_cameras_status", "frs_cameras", ["status"])


def downgrade() -> None:
    op.drop_index("ix_frs_cameras_status", table_name="frs_cameras")
    op.drop_index("ix_frs_cameras_name", table_name="frs_cameras")
    op.drop_table("frs_cameras")
