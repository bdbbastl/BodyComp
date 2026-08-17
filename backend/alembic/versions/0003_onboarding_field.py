"""onboarding_completed_at on users

Revision ID: 0003_onboarding_field
Revises: 0002_billing_fields
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_onboarding_field"
down_revision = "0002_billing_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarding_completed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
