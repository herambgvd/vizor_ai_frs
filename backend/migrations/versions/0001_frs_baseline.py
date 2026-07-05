"""frs baseline — create the edge base tables (+ FRS tables as they're added)

Revision ID: 0001_frs_baseline
Revises:
Create Date: 2026-07-03
"""

from alembic import op

revision = "0001_frs_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _metadata():
    from edge.db.base import Base
    import edge.auth.models  # noqa: F401
    import edge.core.audit  # noqa: F401
    import edge.messaging  # noqa: F401
    import edge.branding.models  # noqa: F401
    import edge.reports.models  # noqa: F401

    # import app.domain  # noqa: F401  (FRS tables, when built)
    return Base.metadata


def upgrade() -> None:
    _metadata().create_all(op.get_bind())


def downgrade() -> None:
    _metadata().drop_all(op.get_bind())
