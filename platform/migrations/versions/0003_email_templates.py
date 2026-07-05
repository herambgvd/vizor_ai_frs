"""email template overrides table

Revision ID: 0003_email_templates
Revises: 0002_auth_tokens
Create Date: 2026-07-03

Adds the email_templates table (admin overrides of the built-in Jinja templates).
"""

from alembic import op

revision = "0003_email_templates"
down_revision = "0002_auth_tokens"
branch_labels = None
depends_on = None


def _tables():
    from edge.messaging.template_store import EmailTemplate

    return [EmailTemplate.__table__]


def upgrade() -> None:
    bind = op.get_bind()
    for table in _tables():
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in _tables():
        table.drop(bind, checkfirst=True)
