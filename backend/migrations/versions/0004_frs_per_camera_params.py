"""move FRS recognition params from the global settings singleton to per-camera.

Reverts the mistaken global ``frs_settings`` recognition tunables (0003) and adds
the vizor_nvr per-camera recognition schema to ``frs_cameras``. The 8 new camera
columns ship with a ``server_default`` (vizor_nvr's proven value) so existing rows
backfill without a data migration; the server_default is then dropped so the ORM's
client-side default owns future inserts. ``min_face_px`` / ``fps`` column defaults
are aligned to vizor_nvr (28 / 10) without rewriting existing rows. Idempotent:
guards on column existence so it is safe to re-run.
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_frs_per_camera_params"
down_revision = "0003_frs_recognition_settings"
branch_labels = None
depends_on = None


# The 19 recognition columns wrongly added to the global settings singleton (0003).
_SETTINGS_COLUMNS = [
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

# The 8 new per-camera recognition columns (vizor_nvr camera_config_schema parity).
# name : (SQLAlchemy type, server_default literal).
_CAMERA_COLUMNS = [
    ("detection_enabled", sa.Boolean(), sa.text("false")),
    ("liveness_enabled", sa.Boolean(), sa.text("true")),
    ("liveness_threshold", sa.Float(), "0.7"),
    ("det_conf", sa.Float(), "0.5"),
    ("min_sharpness", sa.Integer(), "25"),
    ("max_pose_deg", sa.Integer(), "60"),
    ("dwell_min_frames", sa.Integer(), "3"),
    ("alert_suppress_seconds", sa.Integer(), "300"),
]


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(table)}


def _sd(default):
    return default if isinstance(default, sa.sql.elements.TextClause) else sa.text(str(default))


def upgrade() -> None:
    # 1) Drop the mistaken global recognition columns from frs_settings.
    have_settings = _cols("frs_settings")
    for name, _type, _default in reversed(_SETTINGS_COLUMNS):
        if name in have_settings:
            op.drop_column("frs_settings", name)

    # 2) Add the per-camera recognition columns (backfill existing rows, then drop
    #    the server_default so the ORM client-side default owns future inserts).
    have_cam = _cols("frs_cameras")
    for name, coltype, default in _CAMERA_COLUMNS:
        if name in have_cam:
            continue
        op.add_column(
            "frs_cameras",
            sa.Column(name, coltype, nullable=False, server_default=_sd(default)),
        )
        op.alter_column("frs_cameras", name, server_default=None)

    # 3) Align the existing min_face_px / fps column defaults to vizor_nvr (28 / 10)
    #    without rewriting existing rows.
    op.alter_column("frs_cameras", "min_face_px", server_default=sa.text("28"))
    op.alter_column("frs_cameras", "fps", server_default=sa.text("10"))


def downgrade() -> None:
    # Revert the min_face_px / fps column defaults.
    op.alter_column("frs_cameras", "min_face_px", server_default=sa.text("40"))
    op.alter_column("frs_cameras", "fps", server_default=sa.text("5"))

    # Drop the per-camera recognition columns.
    have_cam = _cols("frs_cameras")
    for name, _type, _default in reversed(_CAMERA_COLUMNS):
        if name in have_cam:
            op.drop_column("frs_cameras", name)

    # Restore the global recognition columns on frs_settings.
    have_settings = _cols("frs_settings")
    for name, coltype, default in _SETTINGS_COLUMNS:
        if name in have_settings:
            continue
        op.add_column(
            "frs_settings",
            sa.Column(name, coltype, nullable=False, server_default=_sd(default)),
        )
        op.alter_column("frs_settings", name, server_default=None)
