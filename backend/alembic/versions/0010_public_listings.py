"""public PG listings and enquiries

Adds the fields that let a branch appear in a public search, and the table that
receives enquiries from people who are not signed in.

`listed_publicly` defaults to false. That default is load-bearing: applying this
migration must not put a single existing PG's address, rent and vacancy count on
a public page. Listing is an opt-in decision an owner makes, never something
they inherit from an upgrade.

Revision ID: 0010_public_listings
Revises: 0009_mail_and_otp
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = '0010_public_listings'
down_revision: str | None = '0009_mail_and_otp'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------- branches
    op.add_column("branches", sa.Column(
        "listed_publicly", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("branches", sa.Column("listing_headline", sa.String(length=160), nullable=True))
    op.add_column("branches", sa.Column("listing_description", sa.Text(), nullable=True))
    op.add_column("branches", sa.Column("starting_rent", sa.Numeric(12, 2), nullable=True))
    op.add_column("branches", sa.Column("gender_preference", sa.String(length=10), nullable=True))
    op.add_column("branches", sa.Column("amenities", sa.JSON(), nullable=True))
    op.add_column("branches", sa.Column("contact_phone_public", sa.String(length=20), nullable=True))

    # The public search filters on this before anything else, so it carries the
    # whole result set and is worth an index of its own.
    op.create_index("ix_branches_listed_publicly", "branches", ["listed_publicly"])

    # ---------------------------------------------------- pg_enquiries
    op.create_table(
        "pg_enquiries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("move_in_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="NEW"),
        sa.Column("handled_by_id", sa.UUID(), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staff_notes", sa.Text(), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("requested_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["handled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('NEW', 'CONTACTED', 'VISITED', 'CONVERTED', 'CLOSED')",
            name="ck_pg_enquiries_status"),
    )
    op.create_index("ix_pg_enquiries_organization_id", "pg_enquiries", ["organization_id"])
    op.create_index("ix_pg_enquiries_branch_id", "pg_enquiries", ["branch_id"])
    op.create_index("ix_pg_enquiries_email", "pg_enquiries", ["email"])
    op.create_index("ix_pg_enquiries_status", "pg_enquiries", ["status"])
    op.create_index("ix_pg_enquiries_org_status_time", "pg_enquiries",
                    ["organization_id", "status", "created_at"])

    # The public signup page offers thirty days, so the default has to be
    # thirty. Only moved for installations still on the old default - an
    # operator who deliberately chose a different number keeps it.
    op.execute("UPDATE platform_settings SET default_trial_days = 30 "
               "WHERE default_trial_days = 14")
    op.alter_column("platform_settings", "default_trial_days",
                    server_default="30", existing_type=sa.Integer())


def downgrade() -> None:
    for name in ("ix_pg_enquiries_org_status_time", "ix_pg_enquiries_status",
                 "ix_pg_enquiries_email", "ix_pg_enquiries_branch_id",
                 "ix_pg_enquiries_organization_id"):
        op.drop_index(name, table_name="pg_enquiries")
    op.drop_table("pg_enquiries")

    op.drop_index("ix_branches_listed_publicly", table_name="branches")
    for column in ("contact_phone_public", "amenities", "gender_preference",
                   "starting_rent", "listing_description", "listing_headline",
                   "listed_publicly"):
        op.drop_column("branches", column)
