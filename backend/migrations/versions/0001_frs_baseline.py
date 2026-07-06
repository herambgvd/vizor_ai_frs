"""frs consolidated baseline — create all edge + FRS tables from ORM metadata.

Standalone-repo baseline: a single ``create_all`` of the current edge base + the FRS
domain models. The old incremental chain (0002–0020) is collapsed here so a FRESH
database builds the complete, correct schema in one step (the incremental chain
double-created columns the current edge models already declare). Future schema
changes add new revisions on top of this.
"""

from alembic import op

revision = "0001_frs_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _metadata():
    # Import inside the function so models register on Base.metadata at run time.
    from edge.db.base import Base
    import edge.auth.models  # noqa: F401
    import edge.core.audit  # noqa: F401
    import edge.messaging  # noqa: F401
    import edge.branding.models  # noqa: F401
    import edge.reports.models  # noqa: F401
    import edge.settings.models  # noqa: F401 — app_settings (public settings / flags)
    import app.domain.models  # noqa: F401 — FRS domain tables
    return Base.metadata


def upgrade() -> None:
    _metadata().create_all(op.get_bind())


def downgrade() -> None:
    _metadata().drop_all(op.get_bind())
