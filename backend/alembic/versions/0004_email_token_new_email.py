"""new_email on email_tokens

Revision ID: 0004_email_token_new_email
Revises: 0003_onboarding_field
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_email_token_new_email"
down_revision = "0003_onboarding_field"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_tokens", sa.Column("new_email", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("email_tokens", "new_email")
