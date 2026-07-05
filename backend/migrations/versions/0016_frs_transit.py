"""FRS transit rules + sessions (cross-camera movement).

Revision ID: 0016_frs_transit
Revises: 0015_frs_events_investigations
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_frs_transit"
down_revision = "0015_frs_events_investigations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_transit_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "frs_transit_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_id", sa.Uuid(), sa.ForeignKey("frs_transit_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("frs_persons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_frs_transit_sessions_rule_id", "frs_transit_sessions", ["rule_id"])
    op.create_index("ix_frs_transit_sessions_person_id", "frs_transit_sessions", ["person_id"])
    op.create_index("ix_frs_transit_sessions_status", "frs_transit_sessions", ["status"])


def downgrade() -> None:
    for idx in ("ix_frs_transit_sessions_status", "ix_frs_transit_sessions_person_id", "ix_frs_transit_sessions_rule_id"):
        op.drop_index(idx, table_name="frs_transit_sessions")
    op.drop_table("frs_transit_sessions")
    op.drop_table("frs_transit_rules")
