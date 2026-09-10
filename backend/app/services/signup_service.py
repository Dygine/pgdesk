"""
Owner self-signup, and what happens when the trial runs out.

Two halves that belong together because the second is the consequence of the
first: anyone can create a PG here without talking to a salesperson, so
something has to decide what that account becomes when nobody pays.

Signup creates three rows in one transaction - an organisation, its owner user,
and a trial subscription. All or nothing: an organisation with no owner is
unreachable, and an owner with no subscription trips every limit check on their
first click.

The email is proved before any of it happens. Without that, this endpoint is a
way to create unlimited organisations under addresses belonging to other people.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.models import (
    Customer, Organization, PlatformSettings, Role, Subscription,
    SubscriptionPlan, User,
)
from app.models.enums import (
    AuditAction, OrganizationStatus, SubscriptionStatus, UserStatus,
)
from app.models.platform import SINGLETON_ID
from app.services.audit import AuditService

#: Used when platform settings cannot be read. Matches the product promise
#: rather than the table default, because an operator who never touched the
#: setting still advertised thirty days.
FALLBACK_TRIAL_DAYS = 30

#: Every permission a PG owner needs. Not `is_system_role`, because this role
#: belongs to the tenant and they must be able to edit it - an owner who cannot
#: change their own role's permissions is stuck with whatever we guessed.
OWNER_PERMISSIONS_MARKER = "__all__"


class SignupService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------ helpers
    def _platform(self) -> PlatformSettings | None:
        try:
            return self.db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
        except Exception:
            return None

    def _trial_days(self) -> int:
        row = self._platform()
        if row is not None and row.default_trial_days:
            return row.default_trial_days
        return FALLBACK_TRIAL_DAYS

    def _trial_plan(self) -> SubscriptionPlan:
        """
        The plan a self-signed-up PG lands on.

        Picks the cheapest active plan rather than inventing a "Trial" plan.
        Inventing one would mean every limit check has a second code path, and
        the operator would have to remember to keep two plans in step. A trial
        is a subscription *status*, not a different product.
        """
        plan = self.db.scalars(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.status == "ACTIVE")
            .order_by(SubscriptionPlan.price.asc())
            .limit(1)).first()
        if plan is None:
            raise ConflictError(
                "Sign-ups are not available right now. Please contact support.")
        return plan

    def email_taken(self, email: str) -> bool:
        """
        Checked across both principal tables.

        A resident and a staff member cannot share an address: login resolves by
        address alone, so two rows would make "who is signing in" ambiguous.
        """
        address = email.strip().lower()
        if self.db.scalars(select(User).where(User.email == address)).first():
            return True
        return bool(self.db.scalars(
            select(Customer).where(Customer.email == address)).first())

    # ------------------------------------------------------------- signup
    def create_owner(self, *, pg_name: str, owner_name: str, email: str,
                     phone: str | None, password: str,
                     city: str | None = None) -> tuple[Organization, User]:
        address = email.strip().lower()
        if self.email_taken(address):
            # Said plainly. This is a signup form, and the address was typed by
            # the person in front of it - the enumeration argument that governs
            # /forgot-password does not apply, and "something went wrong" would
            # leave them retyping a working address forever.
            raise ConflictError(
                "An account already exists for this email address. "
                "Sign in instead, or reset your password.")

        today = date.today()
        trial_days = self._trial_days()
        plan = self._trial_plan()

        org = Organization(
            name=pg_name.strip(),
            slug=self._unique_slug(pg_name),
            owner_name=owner_name.strip(),
            owner_email=address,
            owner_phone=phone,
            city=city,
            # TRIAL, not ACTIVE. The distinction is what the expiry job reads,
            # and what lets a dashboard say "12 days left" honestly.
            status=OrganizationStatus.TRIAL,
        )
        self.db.add(org)
        self.db.flush()

        subscription = Subscription(
            organization_id=org.id, plan_id=plan.id,
            start_date=today,
            end_date=today + timedelta(days=trial_days),
            trial_end_date=today + timedelta(days=trial_days),
            status=SubscriptionStatus.TRIAL, is_current=True,
        )
        self.db.add(subscription)

        role = Role(
            organization_id=org.id, name="PG Owner",
            description="Full access to this PG.",
            all_branches=True, is_system_role=False,
        )
        role.permissions = list(self.db.scalars(select(_Permission)).all())
        self.db.add(role)
        self.db.flush()

        owner = User(
            organization_id=org.id, name=owner_name.strip(), email=address,
            phone=phone, password_hash=hash_password(password),
            status=UserStatus.ACTIVE, is_active=True,
            is_master_admin=False, must_change_password=False,
        )
        self.db.add(owner)
        self.db.flush()
        owner.roles = [role]
        self.db.flush()

        self.audit.record(
            scope=None, module="Signup", action=AuditAction.CREATE,
            description=f"{org.name} signed up for a {trial_days}-day trial",
            entity_type="organization", entity_id=org.id,
            organization_id=org.id, user_name=owner_name)
        return org, owner

    def _unique_slug(self, name: str) -> str:
        base = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:40] or "pg"
        slug = base
        # A collision is likely - "Sunrise PG" is not a rare name - so append a
        # short random suffix rather than counting up, which would leak how many
        # similarly named PGs exist.
        if self.db.scalars(select(Organization).where(Organization.slug == slug)).first():
            slug = f"{base}-{uuid.uuid4().hex[:6]}"
        return slug


# Imported late: app.models exports Permission, but naming it at module import
# time here creates a cycle through the RBAC service.
from app.models import Permission as _Permission  # noqa: E402
