"""platform settings and resident stay terms

Two unrelated-looking changes ship together because they are both what the
check-in workflow needs to stop being a demo:

  * customers.meal_plan / billing_cycle - the check-in form has always collected
    these; until now they were written to a browser store and dropped on refresh.
  * platform_settings - the master settings screen had a Save button that only
    set React state. Persisting it needs somewhere to persist to.

Revision ID: 0006_platform_settings
Revises: 0005_operational_modules
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = '0006_platform_settings'
down_revision: str | None = '0005_operational_modules'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SINGLETON_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # --- resident stay terms -------------------------------------------------
    op.add_column("customers", sa.Column("meal_plan", sa.String(length=40), nullable=True))
    op.add_column(
        "customers",
        sa.Column("billing_cycle", sa.String(length=20), nullable=False,
                  server_default="MONTHLY"),
    )

    # --- platform settings ---------------------------------------------------
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("default_trial_days", sa.Integer(), nullable=False),
        sa.Column("grace_period_days", sa.Integer(), nullable=False),
        sa.Column("auto_suspend_after_grace", sa.Boolean(), nullable=False),
        sa.Column("expiry_warning_days", sa.Integer(), nullable=False),
        sa.Column("notify_email_enabled", sa.Boolean(), nullable=False),
        sa.Column("notify_sms_enabled", sa.Boolean(), nullable=False),
        sa.Column("notify_whatsapp_enabled", sa.Boolean(), nullable=False),
        sa.Column("platform_name", sa.String(length=80), nullable=False),
        sa.Column("support_email", sa.String(length=255), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"id = '{SINGLETON_ID}'", name="ck_platform_settings_singleton"),
        sa.CheckConstraint("default_trial_days BETWEEN 0 AND 365",
                           name="ck_platform_trial_days"),
        sa.CheckConstraint("grace_period_days BETWEEN 0 AND 90",
                           name="ck_platform_grace_days"),
        sa.CheckConstraint("expiry_warning_days BETWEEN 0 AND 90",
                           name="ck_platform_warning_days"),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
    op.drop_column("customers", "billing_cycle")
    op.drop_column("customers", "meal_plan")
