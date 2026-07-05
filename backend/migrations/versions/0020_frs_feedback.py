"""FRS operator feedback on recognition events.

Revision ID: 0020_frs_feedback
Revises: 0019_frs_cameras
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_frs_feedback"
down_revision = "0019_frs_cameras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("frs_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("matched_person_id", sa.Uuid(), nullable=True),
        sa.Column("actual_person_id", sa.Uuid(), sa.ForeignKey("frs_persons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("operator", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_frs_feedback_event_id", "frs_feedback", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_frs_feedback_event_id", table_name="frs_feedback")
    op.drop_table("frs_feedback")
