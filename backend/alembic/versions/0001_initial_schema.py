"""initial schema

Hand-written baseline migration (no Docker/Postgres available locally to
run `alembic revision --autogenerate` against) - translated 1:1 from the
`Mapped[...]` column definitions in backend/app/models/*.py, i.e. exactly
what `Base.metadata.create_all()` produces for each table.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users ---------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column(
            "account_type",
            sa.Enum("SINGLE", "COACH", name="accounttype"),
            nullable=False,
        ),
        sa.Column("google_id", sa.String(255), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("privacy_accepted_at", sa.DateTime(), nullable=True),
        sa.Column("sessions_invalidated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)

    # --- clients ---------------------------------------------------------
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(50), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("checkin_token", sa.String(64), nullable=False),
        sa.Column("coach_private_note", sa.Text(), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("checkin_reminder_days", sa.Integer(), nullable=True),
        sa.Column("last_reminder_sent_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_clients_owner_id", "clients", ["owner_id"])

    # --- email_tokens ------------------------------------------------
    op.create_table(
        "email_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum("VERIFY_EMAIL", "RESET_PASSWORD", name="emailtokenpurpose"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"])
    op.create_index("ix_email_tokens_token_hash", "email_tokens", ["token_hash"])

    # --- app_settings ---------------------------------------------------
    op.create_table(
        "app_settings",
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.String(2000), nullable=True),
    )

    # --- poses ---------------------------------------------------------
    op.create_table(
        "poses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("client_id", "name", name="uq_pose_client_name"),
    )
    op.create_index("ix_poses_client_id", "poses", ["client_id"])

    # --- day_logs ---------------------------------------------------------
    op.create_table(
        "day_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("client_id", "date", name="uq_daylog_client_date"),
    )
    op.create_index("ix_day_logs_client_id", "day_logs", ["client_id"])
    op.create_index("ix_day_logs_date", "day_logs", ["date"])

    # --- checkin_submissions --------------------------------------------
    op.create_table(
        "checkin_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("client_note", sa.String(500), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "REVIEWED", name="checkinstatus"),
            nullable=False,
        ),
        sa.Column("coach_feedback_text", sa.String(1000), nullable=True),
        sa.Column("coach_feedback_video_url", sa.String(1000), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_checkin_submissions_client_id", "checkin_submissions", ["client_id"])
    op.create_index("ix_checkin_submissions_status", "checkin_submissions", ["status"])

    # --- photos ---------------------------------------------------------
    op.create_table(
        "photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("original_path", sa.String(1000), nullable=False),
        sa.Column("normalized_path", sa.String(1000), nullable=True),
        sa.Column("preview_path", sa.String(1000), nullable=True),
        sa.Column("thumbnail_path", sa.String(1000), nullable=True),
        sa.Column("taken_at", sa.DateTime(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "UNPROCESSED",
                "PROCESSED",
                "NORMALIZATION_FAILED",
                name="processingstatus",
            ),
            nullable=False,
        ),
        sa.Column(
            "pose_id",
            sa.Integer(),
            sa.ForeignKey("poses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "day_log_id",
            sa.Integer(),
            sa.ForeignKey("day_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "checkin_submission_id",
            sa.Integer(),
            sa.ForeignKey("checkin_submissions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("landmarks_json", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("original_path"),
    )
    op.create_index("ix_photos_client_id", "photos", ["client_id"])
    op.create_index("ix_photos_taken_at", "photos", ["taken_at"])
    op.create_index("ix_photos_status", "photos", ["status"])
    op.create_index("ix_photos_pose_id", "photos", ["pose_id"])
    op.create_index("ix_photos_day_log_id", "photos", ["day_log_id"])
    op.create_index(
        "ix_photos_checkin_submission_id", "photos", ["checkin_submission_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_photos_checkin_submission_id", table_name="photos")
    op.drop_index("ix_photos_day_log_id", table_name="photos")
    op.drop_index("ix_photos_pose_id", table_name="photos")
    op.drop_index("ix_photos_status", table_name="photos")
    op.drop_index("ix_photos_taken_at", table_name="photos")
    op.drop_index("ix_photos_client_id", table_name="photos")
    op.drop_table("photos")

    op.drop_index("ix_checkin_submissions_status", table_name="checkin_submissions")
    op.drop_index("ix_checkin_submissions_client_id", table_name="checkin_submissions")
    op.drop_table("checkin_submissions")

    op.drop_index("ix_day_logs_date", table_name="day_logs")
    op.drop_index("ix_day_logs_client_id", table_name="day_logs")
    op.drop_table("day_logs")

    op.drop_index("ix_poses_client_id", table_name="poses")
    op.drop_table("poses")

    op.drop_table("app_settings")

    op.drop_index("ix_email_tokens_token_hash", table_name="email_tokens")
    op.drop_index("ix_email_tokens_user_id", table_name="email_tokens")
    op.drop_table("email_tokens")

    op.drop_index("ix_clients_owner_id", table_name="clients")
    op.drop_table("clients")

    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
