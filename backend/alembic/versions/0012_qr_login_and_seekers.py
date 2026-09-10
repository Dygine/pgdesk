"""QR sign-in codes and seeker accounts

Two additions, both new tables - nothing existing is altered, so applying this
migration changes no behaviour until the new endpoints are called.

  login_codes      30-minute, single-use keys shown to a new resident as a QR
                   on the owner's screen. Scanning one on the login screen
                   signs the resident in and sends them to "set your password".
  pg_seekers       people looking for a PG, with a name, phone and an email
  seeker_sessions  proved by a code. Their session is a separate, low-power
                   credential accepted only by /public/seeker/*.

Revision ID: 0012_qr_login_and_seekers
Revises: 0011_email_provider
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = '0012_qr_login_and_seekers'
down_revision: str | None = '0011_email_provider'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    # ------------------------------------------------------------ login_codes
    op.create_table(
        "login_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("used_ip", sa.String(length=64), nullable=True),
        sa.Column("used_user_agent", sa.String(length=300), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_login_codes_organization_id", "login_codes", ["organization_id"])
    op.create_index("ix_login_codes_customer_id", "login_codes", ["customer_id"])
    op.create_index("ix_login_codes_token_hash", "login_codes", ["token_hash"], unique=True)

    # ------------------------------------------------------------- pg_seekers
    op.create_table(
        "pg_seekers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pg_seekers_email", "pg_seekers", ["email"], unique=True)

    # -------------------------------------------------------- seeker_sessions
    op.create_table(
        "seeker_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("seeker_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["seeker_id"], ["pg_seekers.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_seeker_sessions_seeker_id", "seeker_sessions", ["seeker_id"])
    op.create_index("ix_seeker_sessions_token_hash", "seeker_sessions", ["token_hash"],
                    unique=True)


def downgrade() -> None:
    op.drop_index("ix_seeker_sessions_token_hash", table_name="seeker_sessions")
    op.drop_index("ix_seeker_sessions_seeker_id", table_name="seeker_sessions")
    op.drop_table("seeker_sessions")

    op.drop_index("ix_pg_seekers_email", table_name="pg_seekers")
    op.drop_table("pg_seekers")

    op.drop_index("ix_login_codes_token_hash", table_name="login_codes")
    op.drop_index("ix_login_codes_customer_id", table_name="login_codes")
    op.drop_index("ix_login_codes_organization_id", table_name="login_codes")
    op.drop_table("login_codes")
