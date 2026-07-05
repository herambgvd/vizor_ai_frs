"""FRS domain: watchlists, POIs, POI-watchlist, cameras, appearances.

Revision ID: 0007_frs_domain
Revises: 0006_app_settings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_frs_domain"
down_revision = "0006_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_watchlist",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, index=True),
        sa.Column("type", sa.String(), nullable=False, server_default="blacklist"),
        sa.Column("color", sa.String(), nullable=False, server_default="#ef4444"),
        sa.Column("severity", sa.String(), nullable=False, server_default="medium"),
        sa.Column("threshold_delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("repeated_alert", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "frs_poi",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False, index=True),
        sa.Column("display_img_key", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("consent_state", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "frs_poi_watchlist",
        sa.Column("poi_id", sa.Uuid(), sa.ForeignKey("frs_poi.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("watchlist_id", sa.Uuid(), sa.ForeignKey("frs_watchlist.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "frs_camera",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, index=True),
        sa.Column("rtsp_url_enc", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("mode", sa.String(), nullable=False, server_default="recognition"),
        sa.Column("base_threshold", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("detection_confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("min_face_size", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("frame_skip", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("roi_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("roi_polygon", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("age_gender_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("watchlist_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(), nullable=False, server_default="offline"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "frs_appearance",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tracker_id", sa.String(), nullable=True),
        sa.Column("camera_id", sa.Uuid(), sa.ForeignKey("frs_camera.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("poi_id", sa.Uuid(), sa.ForeignKey("frs_poi.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("best_face_crop_key", sa.String(), nullable=True),
        sa.Column("best_confidence", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("match_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("face_attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_table("frs_appearance")
    op.drop_table("frs_camera")
    op.drop_table("frs_poi_watchlist")
    op.drop_table("frs_poi")
    op.drop_table("frs_watchlist")
