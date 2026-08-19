"""is_admin/is_active on users

Revision ID: 0005_admin_fields
Revises: 0004_email_token_new_email
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_admin_fields"
down_revision = "0004_email_token_new_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
    op.drop_column("users", "is_admin")
