"""Database-level CHECK constraints for status columns

Revision ID: 0004_enum_checks
Revises: 0003_property_and_limits

SQLAlchemy 2.0's `Enum(..., native_enum=False)` defaults to
`create_constraint=False`, so up to this point the status columns were plain
VARCHARs: the application validated them and the database accepted anything.
This migration closes that gap by adding the CHECK constraints explicitly.

Written by hand because Alembic's autogenerate does not reliably detect CHECK
constraints, so leaving it to autogenerate would silently do nothing.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004_enum_checks"
down_revision: str | None = "0003_property_and_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CONSTRAINTS = {
    "ck_organizations_status": (
        "organizations", "status",
        ["TRIAL", "ACTIVE", "EXPIRING", "EXPIRED", "SUSPENDED", "INACTIVE", "CANCELLED"],
    ),
    "ck_subscriptions_status": (
        "subscriptions", "status", ["TRIAL", "ACTIVE", "EXPIRED", "CANCELLED"],
    ),
    "ck_subscription_plans_status": (
        "subscription_plans", "status", ["ACTIVE", "RETIRED"],
    ),
    "ck_branches_status": ("branches", "status", ["ACTIVE", "INACTIVE"]),
    "ck_users_status": (
        "users", "status", ["ACTIVE", "INVITED", "SUSPENDED", "DEACTIVATED"],
    ),
    "ck_customers_status": (
        "customers", "status",
        ["ENQUIRY", "BOOKED", "RESERVED", "ACTIVE", "NOTICE", "CHECKED_OUT", "ARCHIVED"],
    ),
    "ck_buildings_status": (
        "buildings", "status", ["ACTIVE", "INACTIVE", "UNDER_CONSTRUCTION"],
    ),
    "ck_floors_status": ("floors", "status", ["ACTIVE", "INACTIVE"]),
    "ck_rooms_status": ("rooms", "status", ["ACTIVE", "INACTIVE", "MAINTENANCE"]),
    "ck_beds_status": (
        "beds", "status", ["AVAILABLE", "RESERVED", "OCCUPIED", "MAINTENANCE", "BLOCKED"],
    ),
    "ck_rooms_gender_policy": ("rooms", "gender_policy", ["MALE", "FEMALE", "ANY"]),
}


def upgrade() -> None:
    for name, (table, column, values) in CONSTRAINTS.items():
        allowed = ", ".join(f"'{v}'" for v in values)
        op.create_check_constraint(name, table, f"{column} IN ({allowed})")


def downgrade() -> None:
    for name, (table, _column, _values) in CONSTRAINTS.items():
        op.drop_constraint(name, table, type_="check")
