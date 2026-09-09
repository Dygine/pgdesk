"""
Master-admin organisation management.

Creating a tenant is not one INSERT. An organisation without an owner, a role
and a subscription is unusable, so `create_organization` does all four inside a
single transaction: either a working tenant exists afterwards, or nothing does.
"""
from __future__ import annotations

import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models import (
    Branch, Organization, Permission, Role, Subscription, SubscriptionPlan, User,
)
from app.models.enums import (
    AuditAction, BillingCycle, OrganizationStatus, SubscriptionStatus, UserStatus,
)
from app.permissions.engine import expand
from app.services.audit import AuditService
from app.services.subscription_limits import SubscriptionLimitService
from app.utils.slugs import slugify

# Ambiguous glyphs removed: these are read off a screen and typed by hand.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def generate_temporary_password(length: int = 12) -> str:
    core = "".join(secrets.choice(_ALPHABET) for _ in range(length - 2))
    return f"{core}{secrets.choice('@#$%')}{secrets.choice('23456789')}"


@dataclass
class CreatedOrganization:
    organization: Organization
    owner: User
    role: Role
    subscription: Subscription
    temporary_password: str


class OrganizationService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)
        self.limits = SubscriptionLimitService(db)

    # ------------------------------------------------------------- reading
    def get(self, organization_id: uuid.UUID) -> Organization:
        org = self.db.get(Organization, organization_id)
        if org is None:
            raise NotFoundError("Organisation not found.")
        return org

    def list(
        self, *, search: str | None = None, status: str | None = None,
        plan_code: str | None = None, page: int = 1, page_size: int = 20,
        sort: str = "-created_at",
    ) -> tuple[list[Organization], int]:
        stmt = select(Organization)

        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(
                Organization.name.ilike(like),
                Organization.owner_name.ilike(like),
                Organization.owner_email.ilike(like),
                Organization.city.ilike(like),
            ))
        if status and status != "all":
            stmt = stmt.where(Organization.status == status)
        if plan_code and plan_code != "all":
            stmt = stmt.where(Organization.id.in_(
                select(Subscription.organization_id)
                .join(SubscriptionPlan, SubscriptionPlan.id == Subscription.plan_id)
                .where(Subscription.is_current.is_(True), SubscriptionPlan.code == plan_code)
            ))

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        column = {"name": Organization.name, "status": Organization.status,
                  "created_at": Organization.created_at}.get(sort.lstrip("-"), Organization.created_at)
        stmt = stmt.order_by(column.desc() if sort.startswith("-") else column.asc())

        rows = list(self.db.scalars(
            stmt.offset((page - 1) * page_size).limit(page_size)
        ).all())
        return rows, total

    # ------------------------------------------------------------ creating
    def create_organization(self, data: dict, *, actor: User | None = None,
                            ip: str | None = None) -> CreatedOrganization:
        plan = self.db.scalars(
            select(SubscriptionPlan).where(SubscriptionPlan.code == data["plan_code"])
        ).first()
        if plan is None:
            raise NotFoundError("That subscription plan does not exist.")

        owner_email = data["owner_email"].strip().lower()
        if self.db.scalars(select(User).where(User.email == owner_email)).first():
            raise ConflictError("An account with that email address already exists.")

        base_slug = slugify(data["name"])
        existing = {s for s in self.db.scalars(select(Organization.slug)).all()}
        slug, n = base_slug, 2
        while slug in existing:
            slug, n = f"{base_slug}-{n}", n + 1

        status = data.get("status") or OrganizationStatus.TRIAL
        start = data.get("subscription_start") or date.today()
        end = data.get("subscription_end") or (start + timedelta(days=30))

        org = Organization(
            name=data["name"], slug=slug, legal_name=data.get("legal_name"),
            owner_name=data["owner_name"], owner_email=owner_email,
            owner_phone=data.get("owner_phone"),
            address=data.get("address"), city=data.get("city"),
            state=data.get("state"), pincode=data.get("pincode"),
            gstin=data.get("gstin"), pg_type=data.get("pg_type"),
            gender=data.get("gender"), notes=data.get("notes"),
            status=status, onboarded_on=date.today(),
        )
        self.db.add(org)
        self.db.flush()

        subscription = Subscription(
            organization_id=org.id, plan_id=plan.id,
            start_date=start, end_date=end,
            trial_end_date=end if status == OrganizationStatus.TRIAL else None,
            status=(SubscriptionStatus.TRIAL if status == OrganizationStatus.TRIAL
                    else SubscriptionStatus.ACTIVE),
            is_current=True,
            **{k: v for k, v in (data.get("limit_overrides") or {}).items() if v is not None},
        )
        self.db.add(subscription)

        # The owner role carries every tenant permission. It is a system role, so
        # it cannot be deleted or stripped - otherwise an owner could lock
        # themselves out of their own organisation.
        perms = {p.code: p for p in self.db.scalars(
            select(Permission).where(Permission.is_master.is_(False))
        ).all()}
        role = Role(
            organization_id=org.id, name="Owner",
            description="Full control of the organisation, every branch.",
            is_system_role=True, all_branches=True,
        )
        role.permissions = [perms[c] for c in sorted(expand(["*"])) if c in perms]
        self.db.add(role)
        self.db.flush()

        temporary_password = generate_temporary_password()
        owner = User(
            organization_id=org.id, name=data["owner_name"], email=owner_email,
            phone=data.get("owner_phone"), employee_id="OWN-001",
            password_hash=hash_password(temporary_password),
            # Forces the change-password flow on first sign-in, so the password
            # the operator saw is never the one in long-term use.
            must_change_password=True,
            status=UserStatus.ACTIVE, is_active=True,
        )
        owner.roles = [role]
        self.db.add(owner)
        self.db.flush()

        self.audit.record(
            scope=None, module="Organizations", action=AuditAction.CREATE,
            description=f"Created organisation {org.name} on the {plan.name} plan",
            entity_type="organization", entity_id=org.id, organization_id=org.id,
            user_name=actor.name if actor else "system", ip_address=ip,
        )
        return CreatedOrganization(org, owner, role, subscription, temporary_password)

    # ------------------------------------------------------------ updating
    def update(self, organization_id: uuid.UUID, data: dict, *,
               actor: User | None = None) -> Organization:
        org = self.get(organization_id)
        for field in ("name", "legal_name", "owner_name", "owner_phone", "address",
                      "city", "state", "pincode", "gstin", "pg_type", "gender", "notes"):
            if field in data and data[field] is not None:
                setattr(org, field, data[field])

        self.audit.record(
            scope=None, module="Organizations", action=AuditAction.UPDATE,
            description=f"Updated organisation {org.name}",
            entity_type="organization", entity_id=org.id, organization_id=org.id,
            user_name=actor.name if actor else "system",
        )
        return org

    def set_status(self, organization_id: uuid.UUID, status: str, *,
                   reason: str | None = None, actor: User | None = None) -> Organization:
        org = self.get(organization_id)
        previous = org.status
        org.status = status

        action = {
            OrganizationStatus.SUSPENDED: AuditAction.SUSPEND,
            OrganizationStatus.ACTIVE: AuditAction.ACTIVATE,
        }.get(status, AuditAction.UPDATE)

        self.audit.record(
            scope=None, module="Organizations", action=action,
            description=(f"{org.name}: {previous} \u2192 {status}"
                         + (f" ({reason})" if reason else "")),
            entity_type="organization", entity_id=org.id, organization_id=org.id,
            user_name=actor.name if actor else "system",
        )
        return org

    def extend_subscription(self, organization_id: uuid.UUID, days: int, *,
                            actor: User | None = None) -> Subscription:
        sub = self.limits.current_subscription(organization_id)
        if sub is None:
            raise NotFoundError("This organisation has no current subscription.")
        org = self.get(organization_id)

        # Extend from today when it has already lapsed, otherwise from the end
        # date - so an extension never silently loses the unused remainder.
        base = max(sub.end_date, date.today())
        sub.end_date = base + timedelta(days=days)
        sub.status = SubscriptionStatus.ACTIVE
        if org.status in (OrganizationStatus.EXPIRED, OrganizationStatus.EXPIRING):
            org.status = OrganizationStatus.ACTIVE

        self.audit.record(
            scope=None, module="Subscriptions", action=AuditAction.EXTEND,
            description=f"Extended {org.name} by {days} days to {sub.end_date}",
            entity_type="subscription", entity_id=sub.id, organization_id=org.id,
            user_name=actor.name if actor else "system",
        )
        return sub

    def change_plan(self, organization_id: uuid.UUID, plan_code: str, *,
                    actor: User | None = None) -> Subscription:
        plan = self.db.scalars(
            select(SubscriptionPlan).where(SubscriptionPlan.code == plan_code)
        ).first()
        if plan is None:
            raise NotFoundError("That subscription plan does not exist.")

        sub = self.limits.current_subscription(organization_id)
        if sub is None:
            raise NotFoundError("This organisation has no current subscription.")

        # A downgrade that would put the tenant over its new caps is refused
        # rather than silently accepted, which would leave them unable to create
        # anything and unable to explain why.
        usage = self.limits.usage_for(organization_id)
        breaches = [
            f"{key} {usage[key]}/{getattr(plan, col)}"
            for key, (_, col) in Subscription.LIMIT_COLUMNS.items()
            if usage.get(key, 0) > getattr(plan, col, 0)
        ]
        if breaches:
            raise ConflictError(
                "Current usage exceeds that plan's limits: " + ", ".join(breaches)
                + ". Reduce usage or choose a larger plan."
            )

        org = self.get(organization_id)
        previous = sub.plan.name if sub.plan else "none"
        sub.plan_id = plan.id
        # Per-tenant overrides belonged to the old plan; clear them.
        for sub_col, _ in Subscription.LIMIT_COLUMNS.values():
            setattr(sub, sub_col, None)

        self.audit.record(
            scope=None, module="Subscriptions", action=AuditAction.UPDATE,
            description=f"{org.name}: plan changed from {previous} to {plan.name}",
            entity_type="subscription", entity_id=sub.id, organization_id=org.id,
            user_name=actor.name if actor else "system",
        )
        return sub

    def set_limit_overrides(self, organization_id: uuid.UUID, overrides: dict, *,
                            actor: User | None = None) -> Subscription:
        sub = self.limits.current_subscription(organization_id)
        if sub is None:
            raise NotFoundError("This organisation has no current subscription.")
        applied = []
        for key, value in overrides.items():
            cols = Subscription.LIMIT_COLUMNS.get(key)
            if not cols:
                continue
            setattr(sub, cols[0], value)
            applied.append(f"{key}={value if value is not None else 'plan default'}")
        self.audit.record(
            scope=None, module="Subscriptions", action=AuditAction.UPDATE,
            description="Limit overrides: " + (", ".join(applied) or "none"),
            entity_type="subscription", entity_id=sub.id, organization_id=organization_id,
            user_name=actor.name if actor else "system",
        )
        return sub

    def sweep_expired(self) -> int:
        """
        Move lapsed subscriptions to EXPIRED and near-expiry ones to EXPIRING.

        Run on demand for now; a scheduler owns it once one exists. Nothing is
        deleted - the tenant is frozen so reactivation restores it intact.
        """
        today = date.today()
        soon = today + timedelta(days=15)
        changed = 0

        for org, sub in self.db.execute(
            select(Organization, Subscription)
            .join(Subscription, Subscription.organization_id == Organization.id)
            .where(Subscription.is_current.is_(True),
                   Organization.status.notin_([OrganizationStatus.SUSPENDED,
                                               OrganizationStatus.CANCELLED]))
        ).all():
            if sub.end_date < today and org.status != OrganizationStatus.EXPIRED:
                org.status = OrganizationStatus.EXPIRED
                sub.status = SubscriptionStatus.EXPIRED
                changed += 1
            elif today <= sub.end_date <= soon and org.status == OrganizationStatus.ACTIVE:
                org.status = OrganizationStatus.EXPIRING
                changed += 1
        return changed
