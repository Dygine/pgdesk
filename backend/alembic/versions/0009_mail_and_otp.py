"""outbound mail, one-time codes and long-lived phone sessions

Adds SMTP configuration to `platform_settings`, a table for emailed one-time
codes, and the setting that controls how long a signed-in phone stays signed in.

Safe to apply while the previous release is still serving: every column is
nullable or carries a server default, and nothing reads the new table yet.

Revision ID: 0009_mail_and_otp
Revises: 0008_gate_geofence
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = '0009_mail_and_otp'
down_revision: str | None = '0008_gate_geofence'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------- platform_settings
    op.add_column("platform_settings", sa.Column("smtp_host", sa.String(length=255), nullable=True))
    op.add_column("platform_settings", sa.Column(
        "smtp_port", sa.Integer(), nullable=False, server_default="587"))
    op.add_column("platform_settings", sa.Column("smtp_username", sa.String(length=255), nullable=True))
    # Text, not String(n): Fernet ciphertext grows with the plaintext and a
    # length cap here would silently truncate a long app password into
    # something that decrypts to nothing.
    op.add_column("platform_settings", sa.Column("smtp_password_encrypted", sa.Text(), nullable=True))
    op.add_column("platform_settings", sa.Column("smtp_from_email", sa.String(length=255), nullable=True))
    op.add_column("platform_settings", sa.Column("smtp_from_name", sa.String(length=120), nullable=True))
    op.add_column("platform_settings", sa.Column(
        "smtp_use_tls", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("platform_settings", sa.Column(
        "smtp_use_ssl", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("platform_settings", sa.Column(
        "smtp_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("platform_settings", sa.Column(
        "native_session_days", sa.Integer(), nullable=False, server_default="3650"))

    op.create_check_constraint(
        "ck_platform_smtp_port", "platform_settings", "smtp_port BETWEEN 1 AND 65535")
    op.create_check_constraint(
        "ck_platform_native_session_days", "platform_settings",
        "native_session_days BETWEEN 1 AND 3650")

    # -------------------------------------------------------- otp_codes
    op.create_table(
        "otp_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_token_hash", sa.String(length=64), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("purpose IN ('PASSWORD_RESET', 'SIGNUP_EMAIL')",
                           name="ck_otp_codes_purpose"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 20", name="ck_otp_codes_max_attempts"),
    )
    op.create_index("ix_otp_codes_purpose", "otp_codes", ["purpose"])
    op.create_index("ix_otp_codes_email", "otp_codes", ["email"])
    op.create_index("ix_otp_codes_verification_token_hash", "otp_codes",
                    ["verification_token_hash"], unique=True)
    # Issuing is throttled by "how many codes went to this address recently",
    # which without this index is a sequential scan on a table nothing prunes.
    op.create_index("ix_otp_codes_email_purpose_time", "otp_codes",
                    ["email", "purpose", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_otp_codes_email_purpose_time", table_name="otp_codes")
    op.drop_index("ix_otp_codes_verification_token_hash", table_name="otp_codes")
    op.drop_index("ix_otp_codes_email", table_name="otp_codes")
    op.drop_index("ix_otp_codes_purpose", table_name="otp_codes")
    op.drop_table("otp_codes")

    op.drop_constraint("ck_platform_native_session_days", "platform_settings", type_="check")
    op.drop_constraint("ck_platform_smtp_port", "platform_settings", type_="check")
    for column in ("native_session_days", "smtp_verified_at", "smtp_use_ssl",
                   "smtp_use_tls", "smtp_from_name", "smtp_from_email",
                   "smtp_password_encrypted", "smtp_username", "smtp_port", "smtp_host"):
        op.drop_column("platform_settings", column)
