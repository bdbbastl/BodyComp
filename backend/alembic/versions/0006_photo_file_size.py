"""file_size_bytes on photos

Revision ID: 0006_photo_file_size
Revises: 0005_admin_fields
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_photo_file_size"
down_revision = "0005_admin_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "photos",
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("photos", "file_size_bytes")
