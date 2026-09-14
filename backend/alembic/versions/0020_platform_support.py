"""Platform support tickets, and invoice email tracking

Revision ID: 0020_platform_support
Revises: 0019_platform_billing

A PG owner raising a ticket with the platform, and the operator answering it.

Deliberately not the existing `support_queries` table, which is a resident
raising something with their PG owner. Those two look alike and run in opposite
directions: one is tenant data the PG owns, this crosses the tenant boundary and
is read by the platform operator. Sharing a table would mean every master-admin
query needed an "and not really a tenant record" filter, and one missed filter
leaks a PG's private thread into another PG's inbox.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020_platform_support"
down_revision = "0019_platform_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Short and random, not sequential: an owner reads this out on a phone
        # call, and a counter would tell every customer how many support
        # requests the platform has ever had.
        sa.Column("reference", sa.String(20), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raised_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("category", sa.String(20), nullable=False,
                  server_default="question"),
        sa.Column("priority", sa.String(10), nullable=False,
                  server_default="normal"),
        sa.Column("status", sa.String(15), nullable=False, server_default="open"),
        sa.Column("charge_id", postgresql.UUID(as_uuid=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by_id", postgresql.UUID(as_uuid=True)),
        # Whose turn it is. Drives the badge on both sides without per-user
        # read receipts.
        sa.Column("last_reply_by", sa.String(10), nullable=False,
                  server_default="owner"),
        sa.Column("last_reply_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raised_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["charge_id"], ["platform_charges.id"],
                                ondelete="SET NULL"),
        sa.UniqueConstraint("reference", name="uq_platform_tickets_reference"),
        sa.CheckConstraint(
            "status IN ('open','in_progress','waiting','resolved','closed')",
            name="ck_ticket_status"),
        sa.CheckConstraint("priority IN ('low','normal','high','urgent')",
                           name="ck_ticket_priority"),
        sa.CheckConstraint("last_reply_by IN ('owner','platform')",
                           name="ck_ticket_last_reply_by"),
    )
    op.create_index("ix_platform_tickets_organization_id", "platform_tickets",
                    ["organization_id"])
    op.create_index("ix_platform_tickets_status", "platform_tickets", ["status"])
    op.create_index("ix_platform_tickets_category", "platform_tickets", ["category"])
    op.create_index("ix_platform_tickets_priority", "platform_tickets", ["priority"])
    op.create_index("ix_ticket_org_status", "platform_tickets",
                    ["organization_id", "status"])
    op.create_index("ix_ticket_status_created", "platform_tickets",
                    ["status", "created_at"])

    op.create_table(
        "platform_ticket_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_side", sa.String(10), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True)),
        sa.Column("author_name", sa.String(120), nullable=False,
                  server_default=""),
        sa.Column("body", sa.Text(), nullable=False),
        # An operator's note to themselves. Never serialised on an owner-facing
        # path.
        sa.Column("internal", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ticket_id"], ["platform_tickets.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("author_side IN ('owner','platform')",
                           name="ck_ticket_message_side"),
    )
    op.create_index("ix_platform_ticket_messages_ticket_id",
                    "platform_ticket_messages", ["ticket_id"])

    # --- invoice email tracking on the charge ---
    # The guard that stops a customer receiving the same invoice every time the
    # scheduled job runs.
    op.add_column("platform_charges",
                  sa.Column("invoice_emailed_at", sa.DateTime(timezone=True)))
    op.add_column("platform_charges",
                  sa.Column("invoice_email_error", sa.String(400)))


def downgrade() -> None:
    op.drop_column("platform_charges", "invoice_email_error")
    op.drop_column("platform_charges", "invoice_emailed_at")
    op.drop_table("platform_ticket_messages")
    op.drop_table("platform_tickets")
