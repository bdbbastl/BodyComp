"""billing fields on users

Revision ID: 0002_billing_fields
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_billing_fields"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("subscription_status", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("subscription_tier", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("trial_ends_at", sa.DateTime(), nullable=True))
    op.add_column(
        "users",
        sa.Column("free_checkins_used", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "free_checkins_used")
    op.drop_column("users", "trial_ends_at")
    op.drop_column("users", "subscription_tier")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "stripe_customer_id")
