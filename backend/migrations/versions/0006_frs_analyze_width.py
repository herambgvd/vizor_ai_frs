"""add per-camera ``analyze_width`` (GPU/CPU downscale cap for analysis frames).

High-MP cameras (e.g. 2880x1620) waste CPU copying + resizing every full-res frame
even though the detector runs at 640x640. This column lets each camera cap the
analysis resolution; with ``hw_accel=nvdec`` the resize runs on the GPU (scale_cuda)
so the CPU never touches the full frame. Default 0 = native (no behaviour change on
existing rows). Idempotent: guards on column existence.
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_frs_analyze_width"
down_revision = "0005_frs_transit_attendance"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if "analyze_width" not in _cols("frs_cameras"):
        op.add_column(
            "frs_cameras",
            sa.Column("analyze_width", sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column("frs_cameras", "analyze_width", server_default=None)


def downgrade() -> None:
    if "analyze_width" in _cols("frs_cameras"):
        op.drop_column("frs_cameras", "analyze_width")
