"""transit-session + direction-aware attendance parity with vizor_nvr FRS.

Adds the event-enrichment / alert columns the OLD FRS carries on ``frs_events``
(``severity`` / ``title`` / ``detection_type``) so a ``transit_overdue`` alert can
surface loudly, and the ``sighting_type`` column on ``frs_attendance`` used by the
direction-aware punch logic. ``severity`` is non-null (server_default "info", then
dropped so the ORM client-side default owns future inserts); the rest are nullable.
Idempotent: guards on column existence so it is safe to re-run.
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_frs_transit_attendance"
down_revision = "0004_frs_per_camera_params"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    have_events = _cols("frs_events")
    # severity: non-null with a server_default backfill, then drop the default so
    # the ORM client-side default ("info") owns future inserts.
    if "severity" not in have_events:
        op.add_column(
            "frs_events",
            sa.Column("severity", sa.String(), nullable=False, server_default="info"),
        )
        op.alter_column("frs_events", "severity", server_default=None)
    # title / detection_type: nullable, mirror OLD FRSEvent.
    if "title" not in have_events:
        op.add_column("frs_events", sa.Column("title", sa.String(), nullable=True))
    if "detection_type" not in have_events:
        op.add_column("frs_events", sa.Column("detection_type", sa.String(), nullable=True))

    have_att = _cols("frs_attendance")
    if "sighting_type" not in have_att:
        op.add_column("frs_attendance", sa.Column("sighting_type", sa.String(), nullable=True))


def downgrade() -> None:
    have_att = _cols("frs_attendance")
    if "sighting_type" in have_att:
        op.drop_column("frs_attendance", "sighting_type")

    have_events = _cols("frs_events")
    for name in ("detection_type", "title", "severity"):
        if name in have_events:
            op.drop_column("frs_events", name)
