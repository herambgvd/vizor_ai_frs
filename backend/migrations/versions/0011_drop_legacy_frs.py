"""Drop the legacy FRS domain tables (POI/Watchlist/Camera/Appearance).

The FRS module is being re-implemented from the vizor_nvr FRS design with a new
schema (frs_groups, frs_persons, frs_photos, …), created by later per-feature
migrations. This migration removes the old tables. Irreversible by design.

Revision ID: 0011_drop_legacy_frs
Revises: 0010_totp_mfa
"""

from __future__ import annotations

from alembic import op

revision = "0011_drop_legacy_frs"
down_revision = "0010_totp_mfa"
branch_labels = None
depends_on = None

# Children first so foreign keys don't block the drop; CASCADE is a belt-and-braces.
_LEGACY_TABLES = [
    "frs_poi_face",
    "frs_poi_watchlist",
    "frs_appearance",
    "frs_poi",
    "frs_camera",
    "frs_watchlist",
]


def upgrade() -> None:
    for table in _LEGACY_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


def downgrade() -> None:
    # The legacy schema is intentionally not recreated.
    pass
