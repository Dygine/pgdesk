"""
Checkout notices: a resident saying "I am moving out on this date", ahead of time.

The resident gives notice from their app; the office is told, sees the leaving
date and days remaining on the Checkout screen, and acknowledges it. The
resident can withdraw before the date. On the day, the office runs the normal
checkout and the notice closes with it.

While notice is running the resident's status is NOTICE - which the rest of the
system already treats as living here: they keep their bed, their gate QR, their
portal and their rent invoices. Nothing about notice frees the bed early.

A notice shorter than the PG's notice period is accepted, not refused. People
leave at short notice for real reasons; what matters is that it is recorded as
short, because the deposit is normally settled against it.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import CurrentScope
from app.core.exceptions import ConflictError, NotFoundError
from app.models import (
    Bed, CheckoutNotice, Customer, Invoice, OrganizationSettings, Room,
)
from app.models.enums import (
    AuditAction, CheckoutNoticeStatus, CustomerStatus, InvoiceStatus, NotificationType,
)
from app.services.audit import AuditService
from app.services.notification_service import NotificationService

DEFAULT_NOTICE_DAYS = 30


def notice_days(db: Session, organization_id: uuid.UUID) -> int:
    row = db.scalars(select(OrganizationSettings).where(
        OrganizationSettings.organization_id == organization_id)).first()
    value = getattr(row, "checkout_notice_days", None) if row else None
    return DEFAULT_NOTICE_DAYS if value is None else int(value)


def notice_payload(db: Session, n: CheckoutNotice, *, for_staff: bool = True) -> dict:
    today = date.today()
    payload = {
        "id": str(n.id), "resident_id": str(n.resident_id),
        "branch_id": str(n.branch_id),
        "notice_date": n.notice_date.isoformat(),
        "planned_checkout_date": n.planned_checkout_date.isoformat(),
        "days_left": (n.planned_checkout_date - today).days,
        "days_given": n.days_given, "notice_days_required": n.notice_days_required,
        "short_notice": n.short_notice, "reason": n.reason, "status": n.status,
        "raised_by": n.raised_by, "office_note": n.office_note,
        "decided_at": n.decided_at.isoformat() if n.decided_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }
    resident = n.resident or db.get(Customer, n.resident_id)
    if resident is not None:
        payload["security_deposit"] = float(resident.security_deposit or 0)
        if for_staff:
            room = db.get(Room, resident.room_id) if resident.room_id else None
            bed = db.get(Bed, resident.bed_id) if resident.bed_id else None
            payload.update({
                "resident": resident.full_name, "phone": resident.phone,
                "room": room.room_number if room else None,
                "bed": (bed.bed_code or bed.bed_number) if bed else None,
                "outstanding": round(float(db.scalar(
                    select(func.sum(Invoice.balance)).where(
                        Invoice.resident_id == resident.id, Invoice.balance > 0,
                        Invoice.status != InvoiceStatus.CANCELLED)) or 0), 2),
            })
    return payload


class CheckoutNoticeService:
    def __init__(self, db: Session):
        self.db = db
        self.notify = NotificationService(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------ shared
    def open_notice(self, resident: Customer) -> CheckoutNotice | None:
        return self.db.scalars(select(CheckoutNotice).where(
            CheckoutNotice.resident_id == resident.id,
            CheckoutNotice.status.in_(CheckoutNoticeStatus.open()))
            .order_by(CheckoutNotice.created_at.desc())).first()

    def latest(self, resident: Customer) -> CheckoutNotice | None:
        return self.db.scalars(select(CheckoutNotice).where(
            CheckoutNotice.resident_id == resident.id)
            .order_by(CheckoutNotice.created_at.desc())).first()

    @staticmethod
    def _check_date(planned: date) -> None:
        today = date.today()
        if planned < today:
            raise ConflictError("Pick today or a later date.")
        if planned > today + timedelta(days=366):
            raise ConflictError("Pick a date within the next year.")

    def _restore(self, notice: CheckoutNotice, resident: Customer) -> None:
        if resident.status == CustomerStatus.NOTICE:
            resident.status = notice.previous_status or CustomerStatus.ACTIVE
        resident.expected_checkout_date = None

    def _audit(self, scope: CurrentScope | None, resident: Customer, action, text: str,
               notice: CheckoutNotice) -> None:
        self.audit.record(
            scope=scope, module="Residents", action=action, description=text,
            entity_type="checkout_notice", entity_id=notice.id,
            branch_id=notice.branch_id, organization_id=resident.organization_id,
            user_name=None if scope else resident.full_name)

    # ------------------------------------------------------------- giving
    def give(self, resident: Customer, *, planned_date: date, reason: str | None = None,
             scope: CurrentScope | None = None) -> CheckoutNotice:
        """`scope` present means the office is recording notice given in person."""
        by_staff = scope is not None
        if resident.status not in (CustomerStatus.ACTIVE, CustomerStatus.NOTICE) \
                or not resident.is_active:
            raise ConflictError("Notice can only be given by someone who is living here.")
        if resident.branch_id is None:
            raise ConflictError("This resident is not placed in a branch.")
        if self.open_notice(resident):
            raise ConflictError(
                "Notice has already been given. Withdraw it first to change the date."
                if not by_staff else
                "This resident already has notice running. Acknowledge or cancel that one.")
        self._check_date(planned_date)

        now = datetime.now(timezone.utc)
        notice = CheckoutNotice(
            organization_id=resident.organization_id, branch_id=resident.branch_id,
            resident_id=resident.id, notice_date=date.today(),
            planned_checkout_date=planned_date,
            reason=(reason or "").strip()[:300] or None,
            status=(CheckoutNoticeStatus.ACKNOWLEDGED if by_staff
                    else CheckoutNoticeStatus.SUBMITTED),
            raised_by="staff" if by_staff else "resident",
            notice_days_required=notice_days(self.db, resident.organization_id),
            previous_status=(resident.status if resident.status != CustomerStatus.NOTICE
                             else CustomerStatus.ACTIVE),
            decided_by_id=scope.user.id if by_staff else None,
            decided_at=now if by_staff else None)
        self.db.add(notice)
        resident.status = CustomerStatus.NOTICE
        resident.expected_checkout_date = planned_date
        self.db.flush()

        when = f"{planned_date:%d %b %Y}"
        short = " (short notice)" if notice.short_notice else ""
        if by_staff:
            self.notify.to_resident(
                resident, NotificationType.SYSTEM, "Your moving-out date is recorded",
                f"The office has noted that you are moving out on {when}.",
                entity_type="checkout_notice", entity_id=notice.id, link="/me/moving-out")
        else:
            self.notify.to_permission_holders(
                resident.organization_id, "customers.checkout", NotificationType.SYSTEM,
                "Checkout notice", f"{resident.full_name} plans to move out on {when}{short}.",
                branch_id=resident.branch_id,
                entity_type="checkout_notice", entity_id=notice.id)
        self._audit(scope, resident, AuditAction.UPDATE,
                    f"Checkout notice for {resident.full_name}: leaving {when}{short}", notice)
        return notice

    def withdraw(self, resident: Customer) -> CheckoutNotice:
        notice = self.open_notice(resident)
        if notice is None:
            raise NotFoundError("You have not given notice.")
        if notice.planned_checkout_date < date.today():
            raise ConflictError("Your leaving date has passed. Please speak to the office.")
        notice.status = CheckoutNoticeStatus.WITHDRAWN
        self._restore(notice, resident)
        self.notify.to_permission_holders(
            resident.organization_id, "customers.checkout", NotificationType.SYSTEM,
            "Notice withdrawn", f"{resident.full_name} is no longer moving out.",
            branch_id=resident.branch_id, entity_type="checkout_notice", entity_id=notice.id)
        self._audit(None, resident, AuditAction.UPDATE,
                    f"{resident.full_name} withdrew their checkout notice", notice)
        return notice

    # --------------------------------------------------------- the office
    def _scoped(self, scope: CurrentScope):
        return (select(CheckoutNotice)
                .options(selectinload(CheckoutNotice.resident))
                .where(CheckoutNotice.organization_id == scope.organization_id,
                       CheckoutNotice.branch_id.in_(scope.branch_ids or [uuid.UUID(int=0)])))

    def list(self, scope: CurrentScope, *, status: str | None = None,
             branch_id: uuid.UUID | None = None) -> list[CheckoutNotice]:
        stmt = self._scoped(scope)
        if status == "open" or not status:
            stmt = stmt.where(CheckoutNotice.status.in_(CheckoutNoticeStatus.open()))
        elif status != "all":
            stmt = stmt.where(CheckoutNotice.status == status)
        if branch_id:
            stmt = stmt.where(CheckoutNotice.branch_id == branch_id)
        return list(self.db.scalars(stmt.order_by(
            CheckoutNotice.planned_checkout_date, CheckoutNotice.created_at)).all())

    def get(self, scope: CurrentScope, notice_id: uuid.UUID) -> CheckoutNotice:
        row = self.db.scalars(self._scoped(scope).where(CheckoutNotice.id == notice_id)).first()
        if row is None:
            raise NotFoundError("Notice not found.")
        return row

    def acknowledge(self, scope: CurrentScope, notice_id: uuid.UUID, *,
                    note: str | None = None, planned_date: date | None = None) -> CheckoutNotice:
        notice = self.get(scope, notice_id)
        if notice.status not in CheckoutNoticeStatus.open():
            raise ConflictError(f"This notice is already {notice.status.lower()}.")
        resident = self.db.get(Customer, notice.resident_id)
        if planned_date and planned_date != notice.planned_checkout_date:
            self._check_date(planned_date)
            notice.planned_checkout_date = planned_date
            resident.expected_checkout_date = planned_date
        notice.status = CheckoutNoticeStatus.ACKNOWLEDGED
        notice.decided_by_id = scope.user.id
        notice.decided_at = datetime.now(timezone.utc)
        notice.office_note = (note or "").strip()[:300] or notice.office_note
        self.notify.to_resident(
            resident, NotificationType.SYSTEM, "Notice acknowledged",
            f"The office has confirmed your moving-out date: "
            f"{notice.planned_checkout_date:%d %b %Y}.",
            entity_type="checkout_notice", entity_id=notice.id, link="/me/moving-out")
        self._audit(scope, resident, AuditAction.APPROVE,
                    f"Acknowledged notice from {resident.full_name}", notice)
        return notice

    def cancel(self, scope: CurrentScope, notice_id: uuid.UUID, *,
               note: str | None = None) -> CheckoutNotice:
        notice = self.get(scope, notice_id)
        if notice.status not in CheckoutNoticeStatus.open():
            raise ConflictError(f"This notice is already {notice.status.lower()}.")
        resident = self.db.get(Customer, notice.resident_id)
        notice.status = CheckoutNoticeStatus.CANCELLED
        notice.decided_by_id = scope.user.id
        notice.decided_at = datetime.now(timezone.utc)
        notice.office_note = (note or "").strip()[:300] or None
        self._restore(notice, resident)
        self.notify.to_resident(
            resident, NotificationType.SYSTEM, "Notice cancelled",
            "The office cancelled your moving-out notice"
            + (f": {notice.office_note}" if notice.office_note else "."),
            entity_type="checkout_notice", entity_id=notice.id, link="/me/moving-out")
        self._audit(scope, resident, AuditAction.REJECT,
                    f"Cancelled the notice from {resident.full_name}", notice)
        return notice

    def complete_for(self, resident: Customer) -> None:
        """Called by checkout: a notice that ran its course is closed with it."""
        notice = self.open_notice(resident)
        if notice is not None:
            notice.status = CheckoutNoticeStatus.COMPLETED
