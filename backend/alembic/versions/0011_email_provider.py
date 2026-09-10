"""pluggable email provider (SMTP or Brevo)

Adds a provider switch and Brevo credentials to `platform_settings`.

Defaults to "smtp", so an installation already sending over SMTP keeps behaving
exactly as it did. Nothing changes until an operator picks the other one.

Revision ID: 0011_email_provider
Revises: 0010_public_listings
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = '0011_email_provider'
down_revision: str | None = '0010_public_listings'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("platform_settings", sa.Column(
        "email_provider", sa.String(length=20), nullable=False, server_default="smtp"))
    op.add_column("platform_settings", sa.Column(
        "brevo_api_key_encrypted", sa.Text(), nullable=True))
    op.add_column("platform_settings", sa.Column(
        "brevo_sender_email", sa.String(length=255), nullable=True))
    op.add_column("platform_settings", sa.Column(
        "brevo_sender_name", sa.String(length=120), nullable=True))
    op.add_column("platform_settings", sa.Column(
        "brevo_verified_at", sa.DateTime(timezone=True), nullable=True))

    op.create_check_constraint(
        "ck_platform_email_provider", "platform_settings",
        "email_provider IN ('smtp', 'brevo')")


def downgrade() -> None:
    op.drop_constraint("ck_platform_email_provider", "platform_settings", type_="check")
    for column in ("brevo_verified_at", "brevo_sender_name", "brevo_sender_email",
                   "brevo_api_key_encrypted", "email_provider"):
        op.drop_column("platform_settings", column)
