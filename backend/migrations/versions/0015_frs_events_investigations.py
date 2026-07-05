"""FRS events (recognition sightings) + investigations (forensic search jobs).

Revision ID: 0015_frs_events_investigations
Revises: 0014_frs_photos
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_frs_events_investigations"
down_revision = "0014_frs_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("camera_id", sa.Uuid(), nullable=True),
        sa.Column("camera_name", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("frs_persons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("person_name", sa.String(), nullable=True),
        sa.Column("track_id", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("snapshot_key", sa.String(), nullable=True),
        sa.Column("liveness_score", sa.Float(), nullable=True),
        sa.Column("age", sa.String(), nullable=True),
        sa.Column("age_range", sa.String(), nullable=True),
        sa.Column("gender", sa.String(), nullable=True),
        sa.Column("gender_confidence", sa.Float(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_frs_events_camera_id", "frs_events", ["camera_id"])
    op.create_index("ix_frs_events_event_type", "frs_events", ["event_type"])
    op.create_index("ix_frs_events_person_id", "frs_events", ["person_id"])
    op.create_index("ix_frs_events_triggered_at", "frs_events", ["triggered_at"])

    op.create_table(
        "frs_investigations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="done"),
        sa.Column("similarity_threshold", sa.Float(), nullable=False, server_default="0.45"),
        sa.Column("max_results", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("results", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("frs_investigations")
    for idx in ("ix_frs_events_triggered_at", "ix_frs_events_person_id", "ix_frs_events_event_type", "ix_frs_events_camera_id"):
        op.drop_index(idx, table_name="frs_events")
    op.drop_table("frs_events")
