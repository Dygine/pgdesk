"""
What happens when a trial ends and nobody pays.

Run daily. Three transitions, in order, and each one is a separate day so that
nothing goes from "working" to "locked out" without warning in between:

    TRIAL/ACTIVE  --- end_date passed --->  EXPIRED   (grace period begins)
    EXPIRED       --- grace passed  --->  SUSPENDED   (owner locked out)

Both are reversible, and neither deletes anything. A PG that pays two months
late gets everything back exactly as it was, because "expired" and "suspended"
are states on the organisation, not a data-retention policy.

What suspension actually costs
------------------------------
`SubscriptionLimitService.assert_active` is called on the paths that create
records, not on the ones that read them. So a suspended PG's staff can still
open the app and see their data; they cannot add a resident, raise an invoice or
record a payment.

That asymmetry is deliberate and worth stating plainly, because the alternative
punishes the wrong people. Two hundred residents did not miss the payment. If a
suspension took the resident portal down, they would lose their rent history and
their gate check-in over their landlord's billing problem, and the PG would have
a support crisis instead of a renewal conversation.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization, PlatformSettings, Subscription
from app.models.enums import (
    AuditAction, NotificationType, OrganizationStatus, SubscriptionStatus,
)
from app.models.platform import SINGLETON_ID
from app.services.audit import AuditService
from app.services.notification_service import NotificationService

log = logging.getLogger("pgdesk.subscriptions")


@dataclass
class SweepResult:
    warned: list[str] = field(default_factory=list)
    expired: list[str] = field(default_factory=list)
    suspended: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"warned": self.warned, "expired": self.expired,
                "suspended": self.suspended}


class SubscriptionLifecycleService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)
        self.notify = NotificationService(db)

    def _settings(self) -> PlatformSettings | None:
        try:
            return self.db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
        except Exception:
            return None

    def days_left(self, organization_id: uuid.UUID) -> int | None:
        """
        Days until the current subscription ends. Negative once it has.

        Used by the dashboard to say "12 days left" rather than making an owner
        work it out from a date, which is the difference between a banner people
        act on and one they scroll past.
        """
        sub = self.db.scalars(select(Subscription).where(
            Subscription.organization_id == organization_id,
            Subscription.is_current.is_(True))).first()
        if sub is None:
            return None
        return (sub.end_date - date.today()).days

    def sweep(self, *, today: date | None = None, dry_run: bool = False) -> SweepResult:
        """
        One pass over every current subscription.

        Idempotent: running it twice on the same day changes nothing the second
        time, because each transition is guarded by the status it moves away
        from. That matters because cron jobs get retried, run twice after a
        deploy, and occasionally run on a machine whose clock disagrees.
        """
        today = today or date.today()
        settings = self._settings()
        grace_days = settings.grace_period_days if settings else 7
        warn_days = settings.expiry_warning_days if settings else 7
        auto_suspend = settings.auto_suspend_after_grace if settings else True

        result = SweepResult()

        rows = self.db.scalars(
            select(Subscription).where(Subscription.is_current.is_(True))).all()

        for sub in rows:
            org = self.db.get(Organization, sub.organization_id)
            if org is None or org.status == OrganizationStatus.CANCELLED:
                continue

            days = (sub.end_date - today).days

            # --- still running, but close ---------------------------------
            if days > 0:
                if days <= warn_days and org.status in (
                        OrganizationStatus.ACTIVE, OrganizationStatus.TRIAL):
                    result.warned.append(org.name)
                    if not dry_run:
                        self._notify_owner(
                            org, "Your subscription is about to end",
                            f"{org.name} has {days} day{'s' if days != 1 else ''} "
                            "left. Renew to keep adding residents, invoices and "
                            "payments.")
                continue

            # --- ended: move into the grace period -------------------------
            if org.status in (OrganizationStatus.ACTIVE, OrganizationStatus.TRIAL):
                result.expired.append(org.name)
                if not dry_run:
                    org.status = OrganizationStatus.EXPIRED
                    sub.status = SubscriptionStatus.EXPIRED
                    self._notify_owner(
                        org, "Your subscription has ended",
                        f"{org.name} is now read-only for staff. You have "
                        f"{grace_days} day{'s' if grace_days != 1 else ''} to "
                        "renew before the account is suspended. Residents are "
                        "not affected.")
                    self.audit.record(
                        scope=None, module="Subscription", action=AuditAction.UPDATE,
                        description=f"{org.name} expired on {today.isoformat()}",
                        entity_type="organization", entity_id=org.id,
                        organization_id=org.id)
                continue

            # --- grace spent: suspend --------------------------------------
            if (org.status == OrganizationStatus.EXPIRED
                    and auto_suspend
                    and -days >= grace_days):
                result.suspended.append(org.name)
                if not dry_run:
                    org.status = OrganizationStatus.SUSPENDED
                    self._notify_owner(
                        org, "Your account has been suspended",
                        f"{org.name} is suspended after {grace_days} days without "
                        "renewal. Nothing has been deleted - renewing restores "
                        "everything exactly as it was.")
                    self.audit.record(
                        scope=None, module="Subscription", action=AuditAction.SUSPEND,
                        description=(f"{org.name} suspended after a "
                                     f"{grace_days}-day grace period"),
                        entity_type="organization", entity_id=org.id,
                        organization_id=org.id)

        if not dry_run:
            self.db.flush()
        return result

    def _notify_owner(self, org: Organization, title: str, message: str) -> None:
        """
        Best effort. A notification that fails must not abort the sweep.

        The sweep processes every tenant on the platform in one pass; one
        organisation with a broken owner record would otherwise stop the rest
        from ever being expired.
        """
        try:
            # Addressed by permission rather than by role name. "Who should
            # hear about billing" is exactly the set who can see the dashboard,
            # and a tenant who renamed their owner role still gets the message.
            self.notify.to_permission_holders(
                org.id, "dashboard.view", NotificationType.WARNING, title, message)
        except Exception as exc:                                # noqa: BLE001
            log.warning("could not notify %s: %s", org.name, exc)
