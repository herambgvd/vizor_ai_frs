"""FRS attendance + report schedules + report runs.

Revision ID: 0017_frs_reports
Revises: 0016_frs_transit
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_frs_reports"
down_revision = "0016_frs_transit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frs_attendance",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("frs_persons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("person_name", sa.String(), nullable=True),
        sa.Column("camera_id", sa.Uuid(), nullable=True),
        sa.Column("day_key", sa.String(), nullable=False),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_in_snapshot", sa.String(), nullable=True),
        sa.Column("check_out_snapshot", sa.String(), nullable=True),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("person_id", "day_key", name="uq_frs_attendance_person_day"),
    )
    op.create_index("ix_frs_attendance_person_id", "frs_attendance", ["person_id"])
    op.create_index("ix_frs_attendance_day_key", "frs_attendance", ["day_key"])

    op.create_table(
        "frs_report_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("report", sa.String(), nullable=False),
        sa.Column("fmt", sa.String(), nullable=False, server_default="xlsx"),
        sa.Column("frequency", sa.String(), nullable=False, server_default="daily"),
        sa.Column("at_time", sa.String(), nullable=False, server_default="08:00"),
        sa.Column("range_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("recipients", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "frs_report_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("schedule_id", sa.Uuid(), sa.ForeignKey("frs_report_schedules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report", sa.String(), nullable=False),
        sa.Column("fmt", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("emailed_to", sa.String(), nullable=True),
        sa.Column("email_ok", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("frs_report_runs")
    op.drop_table("frs_report_schedules")
    op.drop_index("ix_frs_attendance_day_key", table_name="frs_attendance")
    op.drop_index("ix_frs_attendance_person_id", table_name="frs_attendance")
    op.drop_table("frs_attendance")
