"""
SubscriptionLimitService - the single gate every quota-consuming create passes.

Adding a limit means adding one row to LIMIT_DEFINITIONS plus a column on the
plan. The counter, the usage screen, the `can_create_*` helper and the error
message all follow from that one entry, so limits stay in the database rather
than drifting into React.

This is the enforcement. The frontend runs a copy purely so the user gets an
immediate message instead of a round trip.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, SubscriptionLimitError
from app.models import (
    Bed, Branch, Building, Customer, Floor, Organization, Role, Room,
    Subscription, User, user_roles,
)
from app.models.enums import CustomerStatus, OrganizationStatus, UserStatus


@dataclass(frozen=True)
class LimitDefinition:
    key: str
    label: str          # singular, used in error messages
    plural: str


LIMIT_DEFINITIONS: tuple[LimitDefinition, ...] = (
    LimitDefinition("branches", "Branch", "branches"),
    LimitDefinition("buildings", "Building", "buildings"),
    LimitDefinition("floors", "Floor", "floors"),
    LimitDefinition("rooms", "Room", "rooms"),
    LimitDefinition("beds", "Bed", "beds"),
    LimitDefinition("customers", "Resident", "residents"),
    LimitDefinition("users", "User", "users"),
    LimitDefinition("admins", "Admin", "admins"),
    LimitDefinition("storage_gb", "Storage", "GB of storage"),
    LimitDefinition("monthly_transactions", "Transaction", "monthly transactions"),
)

LIMITS_BY_KEY = {d.key: d for d in LIMIT_DEFINITIONS}


@dataclass
class LimitReport:
    key: str
    label: str
    plural: str
    used: int
    limit: int | None

    @property
    def remaining(self) -> int | None:
        return None if self.limit is None else max(0, self.limit - self.used)

    @property
    def ratio(self) -> float:
        return 0.0 if not self.limit else min(self.used / self.limit, 1.0)

    @property
    def severity(self) -> str:
        r = self.ratio
        if r >= 1:
            return "critical"
        if r >= 0.9:
            return "high"
        if r >= 0.8:
            return "warn"
        return "ok"

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "plural": self.plural,
            "used": self.used, "limit": self.limit, "remaining": self.remaining,
            "ratio": round(self.ratio, 4), "severity": self.severity,
        }


class SubscriptionLimitService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------ internals
    def _organization(self, organization_id: uuid.UUID) -> Organization:
        org = self.db.get(Organization, organization_id)
        if org is None:
            raise NotFoundError("Organisation not found.")
        return org

    def current_subscription(self, organization_id: uuid.UUID) -> Subscription | None:
        return self.db.scalars(
            select(Subscription)
            .where(Subscription.organization_id == organization_id,
                   Subscription.is_current.is_(True))
            .order_by(Subscription.start_date.desc())
        ).first()

    def limits_for(self, organization_id: uuid.UUID) -> dict[str, int]:
        sub = self.current_subscription(organization_id)
        if sub is None:
            # No subscription means nothing is allowed, not everything.
            return {d.key: 0 for d in LIMIT_DEFINITIONS}
        return sub.effective_limits()

    def _count(self, model, organization_id: uuid.UUID, *extra) -> int:
        stmt = select(func.count(model.id)).where(model.organization_id == organization_id)
        for clause in extra:
            stmt = stmt.where(clause)
        return self.db.scalar(stmt) or 0

    def usage_for(self, organization_id: uuid.UUID) -> dict[str, int]:
        """Live counts. A stale denormalised counter is worse than a cheap COUNT."""
        org = self._organization(organization_id)
        return {
            "branches": self._count(Branch, organization_id),
            "buildings": self._count(Building, organization_id),
            "floors": self._count(Floor, organization_id),
            "rooms": self._count(Room, organization_id),
            "beds": self._count(Bed, organization_id),
            "customers": self._count(
                Customer, organization_id,
                Customer.status.notin_([CustomerStatus.CHECKED_OUT, CustomerStatus.ARCHIVED]),
            ),
            "users": self._count(User, organization_id, User.status != UserStatus.DEACTIVATED),
            # An admin seat is anyone holding a role that sees every branch. It
            # is the level of access that costs, not the job title.
            "admins": self._count(
                User, organization_id,
                User.status != UserStatus.DEACTIVATED,
                User.id.in_(
                    select(user_roles.c.user_id)
                    .join(Role, Role.id == user_roles.c.role_id)
                    .where(Role.all_branches.is_(True))
                ),
            ),
            "storage_gb": int(org.storage_used_gb or 0),
            "monthly_transactions": 0,   # billing lands in a later phase
        }

    # --------------------------------------------------------------- public
    def report(self, organization_id: uuid.UUID) -> list[LimitReport]:
        limits = self.limits_for(organization_id)
        usage = self.usage_for(organization_id)
        return [
            LimitReport(d.key, d.label, d.plural, usage.get(d.key, 0), limits.get(d.key))
            for d in LIMIT_DEFINITIONS
        ]

    def summary(self, organization_id: uuid.UUID) -> dict:
        sub = self.current_subscription(organization_id)
        org = self._organization(organization_id)
        reports = self.report(organization_id)
        return {
            "organization_id": str(organization_id),
            "organization_name": org.name,
            "status": org.status,
            "plan": sub.plan.name if sub and sub.plan else None,
            "plan_code": sub.plan.code if sub and sub.plan else None,
            "end_date": sub.end_date.isoformat() if sub else None,
            "days_remaining": (sub.end_date - date.today()).days if sub else None,
            "limits": {r.key: r.limit for r in reports},
            "usage": {r.key: r.used for r in reports},
            "detail": [r.as_dict() for r in reports],
            "worst_severity": max(
                (r.severity for r in reports),
                key=lambda s: ["ok", "warn", "high", "critical"].index(s),
                default="ok",
            ),
        }

    def assert_operational(self, organization_id: uuid.UUID) -> Organization:
        """
        Can this organisation do anything at all right now?

        Data is never deleted when a subscription lapses - the tenant is frozen,
        not erased, so reactivating restores everything as it was.
        """
        org = self._organization(organization_id)
        if org.status == OrganizationStatus.SUSPENDED:
            raise SubscriptionLimitError(
                "This organisation is currently suspended. Contact the platform administrator.",
                code="organization_suspended",
            )
        if org.status == OrganizationStatus.EXPIRED:
            raise SubscriptionLimitError(
                "Your subscription has expired. Renew it to continue adding records.",
                code="subscription_expired",
            )
        if org.status == OrganizationStatus.CANCELLED:
            raise SubscriptionLimitError(
                "This organisation has been cancelled.", code="organization_cancelled",
            )
        if org.status == OrganizationStatus.INACTIVE:
            raise SubscriptionLimitError(
                "This organisation is inactive.", code="organization_inactive",
            )
        return org

    def check(self, organization_id: uuid.UUID, resource: str, adding: int = 1) -> None:
        """Raises 409 when the quota would be exceeded. Call before the INSERT."""
        definition = LIMITS_BY_KEY.get(resource)
        if definition is None:
            raise ValueError(f"Unknown limited resource: {resource}")

        self.assert_operational(organization_id)

        limit = self.limits_for(organization_id).get(resource)
        if limit is None:
            return

        used = self.usage_for(organization_id).get(resource, 0)
        if used + adding > limit:
            raise SubscriptionLimitError(
                f"Subscription limit reached. You have reached the maximum number of "
                f"{definition.plural} allowed by your plan ({used}/{limit}). "
                f"Upgrade the plan or contact the platform administrator."
            )

    # Named helpers, so call sites read as the rule they enforce.
    def can_create_branch(self, org_id: uuid.UUID, n: int = 1) -> None:
        self.check(org_id, "branches", n)

    def can_create_building(self, org_id: uuid.UUID, n: int = 1) -> None:
        self.check(org_id, "buildings", n)

    def can_create_floor(self, org_id: uuid.UUID, n: int = 1) -> None:
        self.check(org_id, "floors", n)

    def can_create_room(self, org_id: uuid.UUID, n: int = 1) -> None:
        self.check(org_id, "rooms", n)

    def can_create_bed(self, org_id: uuid.UUID, n: int = 1) -> None:
        self.check(org_id, "beds", n)

    def can_create_customer(self, org_id: uuid.UUID, n: int = 1) -> None:
        self.check(org_id, "customers", n)

    def can_create_user(self, org_id: uuid.UUID, n: int = 1) -> None:
        self.check(org_id, "users", n)
