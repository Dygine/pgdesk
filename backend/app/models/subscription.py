import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint, Date, Enum as SAEnum, ForeignKey, Index, Integer, JSON, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Timestamps, UUIDPrimaryKey
from app.models.enums import BillingCycle, PlanStatus, SubscriptionStatus


class SubscriptionPlan(Base, UUIDPrimaryKey, Timestamps):
    """
    Platform-wide plan definitions. Mirrors frontend `src/data/plans.js`, so the
    limit keys are exactly: branches, users, beds, customers, storage_gb.
    """

    __tablename__ = "subscription_plans"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)   # plan_starter, ...
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(300))
    price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # paise-free rupees
    billing_cycle: Mapped[str] = mapped_column(
        SAEnum(BillingCycle, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=BillingCycle.MONTHLY,
    )

    # Every limit lives here, in the database - never only in React. Adding a
    # new one means a column plus an entry in LIMIT_DEFINITIONS; the service,
    # the API and the usage screen all pick it up without further changes.
    max_branches: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_buildings: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    max_floors: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    max_rooms: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    max_beds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_customers: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_admins: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    storage_limit_gb: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    monthly_transaction_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=500)

    features: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    support_level: Mapped[str | None] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        SAEnum(PlanStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=PlanStatus.ACTIVE,
    )

    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_plans_price_non_negative"),
        CheckConstraint(
            "max_branches > 0 AND max_users > 0 AND max_beds > 0 AND max_customers > 0",
            name="ck_plans_limits_positive",
        ),
    )


class Subscription(Base, UUIDPrimaryKey, Timestamps):
    """
    One organization's current (or historical) subscription.

    Limits live here as well as on the plan: the platform operator can raise a
    single tenant's cap without inventing a new plan, which the master admin UI
    already does. A NULL override means "use the plan value".
    """

    __tablename__ = "subscriptions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    trial_end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        SAEnum(SubscriptionStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=SubscriptionStatus.ACTIVE, index=True,
    )
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)

    # Per-tenant overrides. NULL => inherit from the plan.
    max_branches: Mapped[int | None] = mapped_column(Integer)
    max_buildings: Mapped[int | None] = mapped_column(Integer)
    max_floors: Mapped[int | None] = mapped_column(Integer)
    max_rooms: Mapped[int | None] = mapped_column(Integer)
    max_beds: Mapped[int | None] = mapped_column(Integer)
    max_customers: Mapped[int | None] = mapped_column(Integer)
    max_users: Mapped[int | None] = mapped_column(Integer)
    max_admins: Mapped[int | None] = mapped_column(Integer)
    storage_limit_gb: Mapped[int | None] = mapped_column(Integer)
    monthly_transaction_limit: Mapped[int | None] = mapped_column(Integer)

    organization: Mapped["Organization"] = relationship(back_populates="subscriptions")
    plan: Mapped["SubscriptionPlan"] = relationship()

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_subscriptions_date_order"),
        Index("ix_subscriptions_org_current", "organization_id", "is_current"),
    )

    #: resource key -> (subscription override column, plan column)
    LIMIT_COLUMNS = {
        "branches": ("max_branches", "max_branches"),
        "buildings": ("max_buildings", "max_buildings"),
        "floors": ("max_floors", "max_floors"),
        "rooms": ("max_rooms", "max_rooms"),
        "beds": ("max_beds", "max_beds"),
        "customers": ("max_customers", "max_customers"),
        "users": ("max_users", "max_users"),
        "admins": ("max_admins", "max_admins"),
        "storage_gb": ("storage_limit_gb", "storage_limit_gb"),
        "monthly_transactions": ("monthly_transaction_limit", "monthly_transaction_limit"),
    }

    def effective_limits(self) -> dict[str, int]:
        """
        Per-tenant override wins; otherwise the plan value.

        The operator can raise one PG's cap without inventing a plan for them,
        which is what the master admin screen does when a customer outgrows a
        tier mid-cycle.
        """
        out: dict[str, int] = {}
        for key, (sub_col, plan_col) in self.LIMIT_COLUMNS.items():
            override = getattr(self, sub_col, None)
            out[key] = override if override is not None else getattr(self.plan, plan_col)
        return out
