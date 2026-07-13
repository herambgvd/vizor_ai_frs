"""create the edge ``app_settings`` table.

The 0001 baseline built its metadata without importing ``edge.settings.models``, so
the ``app_settings`` table (public settings / feature flags, read by
``GET /settings/public``) was never created — that endpoint 500'd with
``relation "app_settings" does not exist``. This revision creates it. Idempotent
(``checkfirst``) so it's a no-op on databases that already have the table.
"""

from alembic import op

revision = "0002_edge_settings"
down_revision = "0001_frs_baseline"
branch_labels = None
depends_on = None


def _table():
    from edge.db.base import Base
    import edge.settings.models  # noqa: F401 — registers app_settings on the metadata

    return Base.metadata.tables["app_settings"]


def upgrade() -> None:
    _table().create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    _table().drop(op.get_bind(), checkfirst=True)
