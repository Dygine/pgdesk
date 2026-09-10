"""Staff list, checkout notices, weekly food menu, resident payments

Revision ID: 0013_staff_notice_menu_pay
Revises: 0012_qr_login_and_seekers

Five features land together because they share a release:

  staff_members           the workforce list (cooks, guards...), separate from
                          login accounts; salaries paid become expenses
  checkout_notices        a resident's notice that they are moving out
  food_week_menus         the menu that repeats every week
  payment_settings        how residents pay: Razorpay keys (encrypted), UPI,
                          bank details
  payment_gateway_orders  Razorpay orders, so the callback and the webhook
                          complete a payment exactly once

plus columns on expenses (salary link), payments (source, gateway ids) and
organization_settings (notice period, meal schedule).

Every new NOT NULL column on an existing table carries a server default, so the
migration runs on a database that already has rows.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_staff_notice_menu_pay"
down_revision: str | None = "0012_qr_login_and_seekers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    ]


def _org() -> sa.Column:
    return sa.Column("organization_id", UUID,
                     sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False)


def upgrade() -> None:
    # ------------------------------------------------------------- staff
    op.create_table(
        "staff_members",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("branch_id", UUID, sa.ForeignKey("branches.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("designation", sa.String(60), nullable=False),
        sa.Column("shift", sa.String(60)),
        sa.Column("monthly_salary", sa.Numeric(10, 2), nullable=False),
        sa.Column("joining_date", sa.Date()),
        sa.Column("left_on", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("id_proof_reference", sa.String(120)),
        sa.Column("address", sa.String(400)),
        sa.Column("emergency_contact_name", sa.String(160)),
        sa.Column("emergency_contact_phone", sa.String(20)),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
        sa.CheckConstraint("monthly_salary >= 0",
                           name="ck_staff_members_salary_non_negative"),
        sa.CheckConstraint("status IN ('ACTIVE', 'ON_LEAVE', 'LEFT')",
                           name="ck_staff_members_status"),
    )
    op.create_index("ix_staff_members_organization_id", "staff_members", ["organization_id"])
    op.create_index("ix_staff_members_branch_id", "staff_members", ["branch_id"])
    op.create_index("ix_staff_members_user_id", "staff_members", ["user_id"])
    op.create_index("ix_staff_members_full_name", "staff_members", ["full_name"])
    op.create_index("ix_staff_members_status", "staff_members", ["status"])
    op.create_index("ix_staff_members_org_branch", "staff_members",
                    ["organization_id", "branch_id"])

    op.add_column("expenses", sa.Column(
        "staff_member_id", UUID, sa.ForeignKey("staff_members.id", ondelete="SET NULL")))
    op.add_column("expenses", sa.Column("salary_period", sa.Date()))
    op.create_index("ix_expenses_staff_member_id", "expenses", ["staff_member_id"])

    # --------------------------------------------------- checkout notices
    op.create_table(
        "checkout_notices",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("branch_id", UUID, sa.ForeignKey("branches.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("resident_id", UUID, sa.ForeignKey("customers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("notice_date", sa.Date(), nullable=False),
        sa.Column("planned_checkout_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(300)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("raised_by", sa.String(20), nullable=False),
        sa.Column("notice_days_required", sa.Integer(), nullable=False),
        sa.Column("previous_status", sa.String(20)),
        sa.Column("decided_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("office_note", sa.String(300)),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('SUBMITTED', 'ACKNOWLEDGED', 'WITHDRAWN', 'CANCELLED', 'COMPLETED')",
            name="ck_checkout_notices_status"),
    )
    op.create_index("ix_checkout_notices_organization_id", "checkout_notices",
                    ["organization_id"])
    op.create_index("ix_checkout_notices_branch_id", "checkout_notices", ["branch_id"])
    op.create_index("ix_checkout_notices_resident_id", "checkout_notices", ["resident_id"])
    op.create_index("ix_checkout_notices_planned_checkout_date", "checkout_notices",
                    ["planned_checkout_date"])
    op.create_index("ix_checkout_notices_status", "checkout_notices", ["status"])
    op.create_index("ix_checkout_notices_org_status", "checkout_notices",
                    ["organization_id", "status"])

    op.add_column("organization_settings", sa.Column(
        "checkout_notice_days", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("organization_settings", sa.Column("meal_schedule", sa.JSON()))

    # -------------------------------------------------------- weekly menu
    op.create_table(
        "food_week_menus",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("branch_id", UUID, sa.ForeignKey("branches.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("meal", sa.String(12), nullable=False),
        sa.Column("items", sa.Text(), nullable=False),
        sa.Column("notes", sa.String(300)),
        *_timestamps(),
        sa.UniqueConstraint("branch_id", "weekday", "meal",
                            name="uq_food_week_menu_branch_day_meal"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_food_week_menus_weekday"),
    )
    op.create_index("ix_food_week_menus_organization_id", "food_week_menus",
                    ["organization_id"])
    op.create_index("ix_food_week_menus_branch_id", "food_week_menus", ["branch_id"])

    # ----------------------------------------------------------- payments
    op.create_table(
        "payment_settings",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("razorpay_enabled", sa.Boolean(), nullable=False),
        sa.Column("razorpay_key_id", sa.String(60)),
        sa.Column("razorpay_key_secret_encrypted", sa.Text()),
        sa.Column("razorpay_webhook_secret_encrypted", sa.Text()),
        sa.Column("upi_enabled", sa.Boolean(), nullable=False),
        sa.Column("upi_id", sa.String(100)),
        sa.Column("upi_payee_name", sa.String(100)),
        sa.Column("qr_image", sa.Text()),
        sa.Column("bank_enabled", sa.Boolean(), nullable=False),
        sa.Column("bank_account_name", sa.String(120)),
        sa.Column("bank_account_number", sa.String(40)),
        sa.Column("bank_ifsc", sa.String(20)),
        sa.Column("bank_name", sa.String(120)),
        sa.Column("instructions", sa.String(500)),
        *_timestamps(),
        sa.UniqueConstraint("organization_id", name="uq_payment_settings_org"),
    )
    op.create_index("ix_payment_settings_organization_id", "payment_settings",
                    ["organization_id"])

    op.add_column("payments", sa.Column(
        "source", sa.String(20), nullable=False, server_default="desk"))
    op.add_column("payments", sa.Column("gateway_order_id", sa.String(60)))
    op.add_column("payments", sa.Column("gateway_payment_id", sa.String(60)))
    op.create_index("ix_payments_gateway_order_id", "payments", ["gateway_order_id"])
    op.create_unique_constraint("payments_gateway_payment_id_key", "payments",
                                ["gateway_payment_id"])

    op.create_table(
        "payment_gateway_orders",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("branch_id", UUID, sa.ForeignKey("branches.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("resident_id", UUID, sa.ForeignKey("customers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id", ondelete="SET NULL")),
        sa.Column("gateway", sa.String(20), nullable=False),
        sa.Column("order_id", sa.String(60), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payment_id", UUID, sa.ForeignKey("payments.id", ondelete="SET NULL")),
        sa.Column("gateway_payment_id", sa.String(60)),
        sa.Column("failure_reason", sa.String(300)),
        *_timestamps(),
        sa.CheckConstraint("amount > 0", name="ck_payment_gateway_orders_amount_positive"),
        sa.CheckConstraint("status IN ('CREATED', 'PAID', 'FAILED')",
                           name="ck_payment_gateway_orders_status"),
    )
    for column in ("organization_id", "branch_id", "resident_id", "invoice_id", "status"):
        op.create_index(f"ix_payment_gateway_orders_{column}", "payment_gateway_orders",
                        [column])


def downgrade() -> None:
    op.drop_table("payment_gateway_orders")
    op.drop_constraint("payments_gateway_payment_id_key", "payments", type_="unique")
    op.drop_index("ix_payments_gateway_order_id", table_name="payments")
    for column in ("gateway_payment_id", "gateway_order_id", "source"):
        op.drop_column("payments", column)
    op.drop_table("payment_settings")
    op.drop_table("food_week_menus")
    op.drop_column("organization_settings", "meal_schedule")
    op.drop_column("organization_settings", "checkout_notice_days")
    op.drop_table("checkout_notices")
    op.drop_index("ix_expenses_staff_member_id", table_name="expenses")
    op.drop_column("expenses", "salary_period")
    op.drop_column("expenses", "staff_member_id")
    op.drop_table("staff_members")
