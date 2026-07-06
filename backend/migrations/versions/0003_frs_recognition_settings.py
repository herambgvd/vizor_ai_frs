"""add dynamic recognition tunables to the ``frs_settings`` singleton.

Moves the previously-hardcoded recognition params (enroll/live/supervisor
constants) into the DB so they're editable from the Recognition Settings UI.
Each column ships with a ``server_default`` (vizor_nvr's proven value) so the
existing singleton row backfills without a data migration; the server_default is
then dropped so the ORM's client-side default owns future inserts. Idempotent:
skips a column that already exists (safe to re-run).
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_frs_recognition_settings"
down_revision = "0002_edge_settings"
branch_labels = None
depends_on = None


# name : (SQLAlchemy type, server_default literal) — defaults are vizor_nvr parity.
_COLUMNS = [
    ("similarity_threshold", sa.Float(), "0.6"),
    ("det_conf", sa.Float(), "0.5"),
    ("duplicate_cosine", sa.Float(), "0.62"),
    ("enroll_min_face_px", sa.Integer(), "80"),
    ("enroll_max_pose_deg", sa.Float(), "45"),
    ("enroll_min_sharpness", sa.Float(), "50"),
    ("live_det_conf", sa.Float(), "0.5"),
    ("live_min_face_px", sa.Integer(), "80"),
    ("live_max_pose_deg", sa.Float(), "40"),
    ("live_min_sharpness", sa.Float(), "60"),
    ("live_unknown_min_det_conf", sa.Float(), "0.65"),
    ("live_vote_min_frames", sa.Integer(), "5"),
    ("live_high_conf_score", sa.Float(), "0.75"),
    ("live_motion_blur_ratio", sa.Float(), "0.35"),
    ("pad_enabled", sa.Boolean(), sa.text("false")),
    ("liveness_threshold", sa.Float(), "0.5"),
    ("alert_cooldown_seconds", sa.Integer(), "300"),
    ("live_fps", sa.Integer(), "10"),
    ("retention_event_days", sa.Integer(), "90"),
]


def _existing() -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns("frs_settings")}


def upgrade() -> None:
    have = _existing()
    for name, coltype, default in _COLUMNS:
        if name in have:
            continue
        sd = default if isinstance(default, sa.sql.elements.TextClause) else sa.text(str(default))
        op.add_column(
            "frs_settings",
            sa.Column(name, coltype, nullable=False, server_default=sd),
        )
        # Drop the server_default now that the singleton row is backfilled; the ORM
        # client-side default owns future inserts.
        op.alter_column("frs_settings", name, server_default=None)


def downgrade() -> None:
    have = _existing()
    for name, _coltype, _default in reversed(_COLUMNS):
        if name in have:
            op.drop_column("frs_settings", name)
