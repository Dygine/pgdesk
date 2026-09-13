"""Push notifications - device tokens, delivery state, Firebase settings

Revision ID: 0017_push_notifications
Revises: 0016_site_content

Three changes that only make sense together, so they ship as one revision: a
half-applied version of this leaves a dispatcher looking for a column that is
not there.

`device_tokens`   one row per phone that agreed to receive notifications.
`notifications`   gains delivery state, which turns the existing table into the
                  send queue rather than adding a second one beside it.
`platform_settings` gains the Firebase credentials and the toggles a master
                  admin sets from the settings screen.

Nothing here is destructive and the downgrade is exact, so this is safe to run
against a database with live data.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0017_push_notifications"
down_revision: str | None = "0016_site_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------- device tokens
    op.create_table(
        "device_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        # Nullable: a master admin has no organisation and is precisely the
        # account that must be able to register a phone for the test button.
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token", sa.String(length=500), nullable=False),
        sa.Column("platform", sa.String(length=10), nullable=False,
                  server_default="android"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resident_id"], ["customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # A token identifies an installation, not a person. Unique so that a
        # phone handed to a new resident moves to the new owner instead of
        # ending up on two rows and delivering to both.
        sa.UniqueConstraint("token", name="uq_device_tokens_token"),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND resident_id IS NULL) "
            "OR (user_id IS NULL AND resident_id IS NOT NULL)",
            name="ck_device_tokens_one_owner"),
        sa.CheckConstraint("platform IN ('android', 'ios', 'web')",
                           name="ck_device_tokens_platform"),
    )
    op.create_index("ix_device_tokens_organization_id", "device_tokens",
                    ["organization_id"])
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])
    op.create_index("ix_device_tokens_resident_id", "device_tokens", ["resident_id"])
    op.create_index("ix_device_tokens_user_live", "device_tokens",
                    ["user_id", "revoked_at"])
    op.create_index("ix_device_tokens_resident_live", "device_tokens",
                    ["resident_id", "revoked_at"])

    # ------------------------------------------------ notification send state
    # Existing rows get pushed_at = now(), not NULL. A NULL would mean "not yet
    # delivered", and the first sweep after this migration would push every
    # historical notification in the database to every phone at once.
    op.add_column("notifications",
                  sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE notifications SET pushed_at = now()")
    op.add_column("notifications",
                  sa.Column("push_attempts", sa.Integer(), nullable=False,
                            server_default="0"))
    op.add_column("notifications",
                  sa.Column("push_error", sa.String(length=200), nullable=True))
    op.create_index("ix_notifications_pushed_at", "notifications", ["pushed_at"])
    # Partial: the sweep only ever asks for undelivered rows, which are a tiny
    # and shrinking fraction of the table.
    op.create_index("ix_notifications_push_pending", "notifications", ["created_at"],
                    postgresql_where=sa.text("pushed_at IS NULL"))

    # ------------------------------------------------------- platform settings
    op.add_column("platform_settings",
                  sa.Column("notify_push_enabled", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    op.add_column("platform_settings",
                  sa.Column("push_to_residents", sa.Boolean(), nullable=False,
                            server_default=sa.true()))
    op.add_column("platform_settings",
                  sa.Column("push_to_staff", sa.Boolean(), nullable=False,
                            server_default=sa.true()))
    op.add_column("platform_settings",
                  sa.Column("fcm_project_id", sa.String(length=120), nullable=True))
    op.add_column("platform_settings",
                  sa.Column("fcm_credentials_encrypted", sa.Text(), nullable=True))
    op.add_column("platform_settings",
                  sa.Column("fcm_verified_at", sa.DateTime(timezone=True),
                            nullable=True))
    op.add_column("platform_settings",
                  sa.Column("rent_reminder_days", sa.Integer(), nullable=False,
                            server_default="3"))
    op.create_check_constraint("ck_platform_rent_reminder_days", "platform_settings",
                               "rent_reminder_days BETWEEN 0 AND 30")


def downgrade() -> None:
    op.drop_constraint("ck_platform_rent_reminder_days", "platform_settings",
                       type_="check")
    for column in ("rent_reminder_days", "fcm_verified_at",
                   "fcm_credentials_encrypted", "fcm_project_id",
                   "push_to_staff", "push_to_residents", "notify_push_enabled"):
        op.drop_column("platform_settings", column)

    op.drop_index("ix_notifications_push_pending", table_name="notifications")
    op.drop_index("ix_notifications_pushed_at", table_name="notifications")
    for column in ("push_error", "push_attempts", "pushed_at"):
        op.drop_column("notifications", column)

    for index in ("ix_device_tokens_resident_live", "ix_device_tokens_user_live",
                  "ix_device_tokens_resident_id", "ix_device_tokens_user_id",
                  "ix_device_tokens_organization_id"):
        op.drop_index(index, table_name="device_tokens")
    op.drop_table("device_tokens")
