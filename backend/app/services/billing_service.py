"""
Rent, invoices and payments.

The rule that shapes this module: **only a verified payment moves an invoice
balance.** Front-desk staff record what they received; someone with
`payments.verify` confirms it. Until then the invoice still shows the money as
outstanding, which is the honest answer - a note saying "paid by UPI" is not
proof the UPI landed.

Invoice and payment numbers are per-organisation sequences. They are generated
inside the same transaction as the row, taking the current maximum for that
tenant. Under heavy concurrency two callers could pick the same number; the
unique constraint rejects the loser rather than silently issuing a duplicate,
and a retry gets the next one. That is the right trade at this scale - a real
sequence table would be the fix if it ever bites.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import CurrentScope
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models import (
    Branch, Customer, Invoice, InvoiceItem, OrganizationSettings, Payment,
)
from app.models.enums import (
    AuditAction, CustomerStatus, InvoiceItemKind, InvoiceStatus,
    NotificationType, PaymentStatus,
)
from app.services.audit import AuditService
from app.services.notification_service import NotificationService


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


class BillingService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope
        self.audit = AuditService(db)
        self.notify = NotificationService(db)

    @property
    def org_id(self) -> uuid.UUID:
        return self.scope.organization_id

    # ------------------------------------------------------------- helpers
    def settings(self) -> OrganizationSettings:
        row = self.db.scalars(
            select(OrganizationSettings).where(
                OrganizationSettings.organization_id == self.org_id)).first()
        if row is None:
            row = OrganizationSettings(organization_id=self.org_id)
            self.db.add(row)
            self.db.flush()
        return row

    def _next_number(self, model, column, prefix: str) -> str:
        last = self.db.scalar(
            select(func.max(column)).where(model.organization_id == self.org_id))
        n = 1
        if last:
            tail = str(last).rsplit("-", 1)[-1]
            if tail.isdigit():
                n = int(tail) + 1
        return f"{prefix}-{n:05d}"

    def _scoped_invoices(self):
        return (select(Invoice)
                .where(Invoice.organization_id == self.org_id,
                       Invoice.branch_id.in_(self.scope.branch_ids)))

    def _scoped_payments(self):
        return (select(Payment)
                .where(Payment.organization_id == self.org_id,
                       Payment.branch_id.in_(self.scope.branch_ids)))

    def get_invoice(self, invoice_id: uuid.UUID) -> Invoice:
        row = self.db.scalars(
            self._scoped_invoices().where(Invoice.id == invoice_id)).first()
        if row is None:
            raise NotFoundError("Invoice not found.")
        return row

    def get_payment(self, payment_id: uuid.UUID) -> Payment:
        row = self.db.scalars(
            self._scoped_payments().where(Payment.id == payment_id)).first()
        if row is None:
            raise NotFoundError("Payment not found.")
        return row

    def _resident(self, resident_id: uuid.UUID) -> Customer:
        row = self.db.scalars(
            select(Customer).where(Customer.id == resident_id,
                                   Customer.organization_id == self.org_id)).first()
        if row is None:
            raise NotFoundError("Resident not found.")
        if row.branch_id and not self.scope.owns_branch(row.branch_id):
            raise PermissionDeniedError(
                "Branch access denied. You are not assigned to this resident's branch.")
        return row

    # ------------------------------------------------------------ invoices
    def list_invoices(self, *, search=None, status=None, branch_id=None,
                      resident_id=None, from_date=None, to_date=None,
                      page=1, page_size=25):
        stmt = self._scoped_invoices().options(selectinload(Invoice.resident))
        if branch_id:
            stmt = stmt.where(Invoice.branch_id == branch_id)
        if resident_id:
            stmt = stmt.where(Invoice.resident_id == resident_id)
        if status and status != "all":
            stmt = stmt.where(Invoice.status == status)
        if from_date:
            stmt = stmt.where(Invoice.invoice_date >= from_date)
        if to_date:
            stmt = stmt.where(Invoice.invoice_date <= to_date)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(
                Invoice.invoice_number.ilike(like),
                Invoice.resident_id.in_(
                    select(Customer.id).where(Customer.full_name.ilike(like)))))

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.db.scalars(
            stmt.order_by(Invoice.invoice_date.desc(), Invoice.invoice_number.desc())
            .offset((page - 1) * page_size).limit(page_size)).all())
        return rows, total

    def create_invoice(self, data: dict) -> Invoice:
        resident = self._resident(data["resident_id"])
        settings = self.settings()

        invoice_date = data.get("invoice_date") or date.today()
        due_date = data.get("due_date") or invoice_date + timedelta(days=7)
        if due_date < invoice_date:
            raise ConflictError("The due date cannot be before the invoice date.")

        invoice = Invoice(
            organization_id=self.org_id, branch_id=resident.branch_id,
            resident_id=resident.id,
            invoice_number=self._next_number(
                Invoice, Invoice.invoice_number, settings.invoice_prefix),
            invoice_date=invoice_date, due_date=due_date,
            period=data.get("period"), notes=data.get("notes"),
            tax=data.get("tax") or 0, late_fee=data.get("late_fee") or 0,
            status=InvoiceStatus.PENDING)
        self.db.add(invoice)
        self.db.flush()

        items = data.get("items") or []
        if not items:
            raise ConflictError("An invoice needs at least one line.")
        for item in items:
            self._add_item(invoice, item)

        invoice.recalculate()
        self.audit.record(
            scope=self.scope, module="Invoices", action=AuditAction.CREATE,
            description=(f"Invoice {invoice.invoice_number} for {resident.full_name} "
                         f"({invoice.total})"),
            entity_type="invoice", entity_id=invoice.id, branch_id=invoice.branch_id)
        self.notify.to_resident(
            resident, NotificationType.RENT_DUE, "New invoice",
            f"Invoice {invoice.invoice_number} for {invoice.total} is due on {due_date}.",
            entity_type="invoice", entity_id=invoice.id, link="/me/rent")
        return invoice

    def _add_item(self, invoice: Invoice, item: dict) -> InvoiceItem:
        quantity = float(item.get("quantity") or 1)
        unit_price = float(item.get("unit_price") or item.get("amount") or 0)
        amount = float(item.get("amount") or quantity * unit_price)
        row = InvoiceItem(
            organization_id=self.org_id, invoice_id=invoice.id,
            kind=item.get("kind") or InvoiceItemKind.OTHER,
            description=item["description"], quantity=quantity,
            unit_price=unit_price, amount=round(amount, 2))
        self.db.add(row)
        invoice.items.append(row)
        return row

    def update_invoice(self, invoice_id: uuid.UUID, data: dict) -> Invoice:
        invoice = self.get_invoice(invoice_id)
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ConflictError("A cancelled invoice cannot be edited.")
        for field in ("due_date", "notes", "late_fee", "tax"):
            if data.get(field) is not None:
                setattr(invoice, field, data[field])
        if data.get("items") is not None:
            for existing in list(invoice.items):
                self.db.delete(existing)
            invoice.items.clear()
            self.db.flush()
            for item in data["items"]:
                self._add_item(invoice, item)
        invoice.recalculate()
        self.audit.record(
            scope=self.scope, module="Invoices", action=AuditAction.UPDATE,
            description=f"Updated invoice {invoice.invoice_number}",
            entity_type="invoice", entity_id=invoice.id, branch_id=invoice.branch_id)
        return invoice

    def cancel_invoice(self, invoice_id: uuid.UUID, reason: str | None = None) -> Invoice:
        invoice = self.get_invoice(invoice_id)
        verified = [p for p in invoice.payments if p.status == PaymentStatus.VERIFIED]
        if verified:
            raise ConflictError(
                f"This invoice has {len(verified)} verified payment"
                f"{'s' if len(verified) != 1 else ''} against it. Refund those first.")
        invoice.status = InvoiceStatus.CANCELLED
        invoice.balance = 0
        self.audit.record(
            scope=self.scope, module="Invoices", action=AuditAction.UPDATE,
            description=f"Cancelled invoice {invoice.invoice_number}"
                        + (f": {reason}" if reason else ""),
            entity_type="invoice", entity_id=invoice.id, branch_id=invoice.branch_id)
        return invoice

    # ------------------------------------------------------ rent generation
    def generate_rent(self, *, period: date | None = None,
                      branch_id: uuid.UUID | None = None) -> dict:
        """
        Issue this month's rent invoice for every live resident who has no rent
        invoice for the period yet.

        Idempotent by (resident, period): running it twice in a month adds
        nothing the second time, which matters because someone will click it
        twice.
        """
        settings = self.settings()
        period = month_start(period or date.today())
        branch_ids = [branch_id] if branch_id else list(self.scope.branch_ids)
        if branch_id and not self.scope.owns_branch(branch_id):
            raise PermissionDeniedError("Branch access denied.")

        residents = self.db.scalars(
            select(Customer).where(
                Customer.organization_id == self.org_id,
                Customer.branch_id.in_(branch_ids),
                Customer.status.in_([CustomerStatus.ACTIVE, CustomerStatus.NOTICE]),
                Customer.monthly_rent > 0)).all()

        already = {
            r for (r,) in self.db.execute(
                select(Invoice.resident_id).where(
                    Invoice.organization_id == self.org_id,
                    Invoice.period == period,
                    Invoice.status != InvoiceStatus.CANCELLED)).all()
        }

        created, skipped = [], 0
        for resident in residents:
            if resident.id in already:
                skipped += 1
                continue
            due_day = min(resident.rent_due_day or settings.rent_due_day, 28)
            invoice = self.create_invoice({
                "resident_id": resident.id,
                "invoice_date": period,
                "due_date": period.replace(day=due_day),
                "period": period,
                "items": [{
                    "kind": InvoiceItemKind.RENT,
                    "description": f"Room rent — {period.strftime('%B %Y')}",
                    "quantity": 1, "unit_price": float(resident.monthly_rent),
                }],
            })
            created.append(invoice)

        self.audit.record(
            scope=self.scope, module="Rent", action=AuditAction.CREATE,
            description=(f"Generated {len(created)} rent invoice"
                         f"{'s' if len(created) != 1 else ''} for "
                         f"{period.strftime('%B %Y')} ({skipped} already existed)"),
            entity_type="rent_run", entity_id=None)
        return {"period": period.isoformat(), "created": len(created),
                "skipped": skipped, "invoice_ids": [str(i.id) for i in created]}

    def apply_late_fees(self) -> int:
        """Add the configured late fee to invoices past their grace period."""
        settings = self.settings()
        if not float(settings.late_fee_amount):
            return 0
        cutoff = date.today() - timedelta(days=settings.late_fee_after_days)
        overdue = self.db.scalars(
            self._scoped_invoices().where(
                Invoice.due_date < cutoff,
                Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.PARTIAL,
                                    InvoiceStatus.OVERDUE]),
                Invoice.late_fee == 0)).all()
        for invoice in overdue:
            invoice.late_fee = settings.late_fee_amount
            invoice.recalculate()
        return len(overdue)

    # ------------------------------------------------------------ payments
    def list_payments(self, *, search=None, status=None, method=None, branch_id=None,
                      resident_id=None, invoice_id=None, from_date=None, to_date=None,
                      page=1, page_size=25):
        stmt = self._scoped_payments().options(selectinload(Payment.resident))
        if branch_id:
            stmt = stmt.where(Payment.branch_id == branch_id)
        if resident_id:
            stmt = stmt.where(Payment.resident_id == resident_id)
        if invoice_id:
            stmt = stmt.where(Payment.invoice_id == invoice_id)
        if status and status != "all":
            stmt = stmt.where(Payment.status == status)
        if method and method != "all":
            stmt = stmt.where(Payment.method == method)
        if from_date:
            stmt = stmt.where(Payment.payment_date >= from_date)
        if to_date:
            stmt = stmt.where(Payment.payment_date <= to_date)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(
                Payment.payment_number.ilike(like), Payment.reference.ilike(like),
                Payment.resident_id.in_(
                    select(Customer.id).where(Customer.full_name.ilike(like)))))

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.db.scalars(
            stmt.order_by(Payment.payment_date.desc(), Payment.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)).all())
        return rows, total

    def record_payment(self, data: dict, *, auto_verify: bool = False) -> Payment:
        resident = self._resident(data["resident_id"])
        amount = round(float(data["amount"]), 2)
        if amount <= 0:
            raise ConflictError("A payment must be more than zero.")

        invoice = None
        if data.get("invoice_id"):
            invoice = self.get_invoice(data["invoice_id"])
            if invoice.resident_id != resident.id:
                raise ConflictError("That invoice belongs to a different resident.")
            if invoice.status == InvoiceStatus.CANCELLED:
                raise ConflictError("A cancelled invoice cannot take a payment.")
            # Overpayment is refused rather than quietly held as credit: a
            # credit balance needs a ledger, and inventing one silently here
            # would lose money the first time someone reconciled.
            if amount > float(invoice.balance) + 0.009:
                raise ConflictError(
                    f"That is more than the outstanding balance ({invoice.balance}). "
                    "Reduce the amount or record it against another invoice.")

        payment = Payment(
            organization_id=self.org_id, branch_id=resident.branch_id,
            resident_id=resident.id, invoice_id=invoice.id if invoice else None,
            payment_number=self._next_number(Payment, Payment.payment_number, "PAY"),
            amount=amount, payment_date=data.get("payment_date") or date.today(),
            method=data.get("method") or "CASH", reference=data.get("reference"),
            notes=data.get("notes"), received_by_id=self.scope.user.id,
            status=PaymentStatus.PENDING)
        self.db.add(payment)
        self.db.flush()

        if auto_verify:
            self._verify(payment)

        if invoice:
            invoice.payments.append(payment)
            invoice.recalculate()

        self.audit.record(
            scope=self.scope, module="Payments", action=AuditAction.CREATE,
            description=(f"Recorded {payment.method} payment {payment.payment_number} "
                         f"of {amount} from {resident.full_name}"),
            entity_type="payment", entity_id=payment.id, branch_id=payment.branch_id)
        self.notify.to_resident(
            resident, NotificationType.PAYMENT_RECEIVED, "Payment recorded",
            f"We recorded {amount} by {payment.method.replace('_', ' ').lower()}.",
            entity_type="payment", entity_id=payment.id, link="/me/rent")
        return payment

    def _verify(self, payment: Payment) -> None:
        payment.status = PaymentStatus.VERIFIED
        payment.verified_by_id = self.scope.user.id
        payment.verified_at = datetime.now(timezone.utc)

    def verify_payment(self, payment_id: uuid.UUID, *, approved: bool,
                       note: str | None = None) -> Payment:
        payment = self.get_payment(payment_id)
        if payment.status == PaymentStatus.VERIFIED and approved:
            return payment
        if payment.status == PaymentStatus.REFUNDED:
            raise ConflictError("A refunded payment cannot be verified.")

        if approved:
            self._verify(payment)
        else:
            payment.status = PaymentStatus.REJECTED
            payment.verified_by_id = self.scope.user.id
            payment.verified_at = datetime.now(timezone.utc)
        if note:
            payment.notes = f"{payment.notes or ''}\n{note}".strip()

        if payment.invoice_id:
            invoice = self.db.get(Invoice, payment.invoice_id)
            invoice.recalculate()

        resident = self.db.get(Customer, payment.resident_id)
        self.audit.record(
            scope=self.scope, module="Payments", action=AuditAction.UPDATE,
            description=(f"{'Verified' if approved else 'Rejected'} payment "
                         f"{payment.payment_number} ({payment.amount})"),
            entity_type="payment", entity_id=payment.id, branch_id=payment.branch_id)
        if resident:
            self.notify.to_resident(
                resident, NotificationType.PAYMENT_VERIFIED,
                "Payment verified" if approved else "Payment rejected",
                (f"Your payment of {payment.amount} has been confirmed."
                 if approved else
                 f"Your payment of {payment.amount} could not be confirmed. "
                 "Please contact the front desk."),
                entity_type="payment", entity_id=payment.id, link="/me/rent")
        return payment

    def refund_payment(self, payment_id: uuid.UUID, reason: str) -> Payment:
        payment = self.get_payment(payment_id)
        if payment.status != PaymentStatus.VERIFIED:
            raise ConflictError("Only a verified payment can be refunded.")
        payment.status = PaymentStatus.REFUNDED
        payment.notes = f"{payment.notes or ''}\nRefunded: {reason}".strip()
        if payment.invoice_id:
            self.db.get(Invoice, payment.invoice_id).recalculate()
        self.audit.record(
            scope=self.scope, module="Payments", action=AuditAction.UPDATE,
            description=f"Refunded payment {payment.payment_number}: {reason}",
            entity_type="payment", entity_id=payment.id, branch_id=payment.branch_id)
        return payment

    # ----------------------------------------------------------- dashboard
    def rent_summary(self, *, branch_id: uuid.UUID | None = None,
                     period: date | None = None) -> dict:
        branch_ids = [branch_id] if branch_id else list(self.scope.branch_ids)
        if branch_id and not self.scope.owns_branch(branch_id):
            branch_ids = []
        period = month_start(period or date.today())
        next_period = add_month(period)

        def money(stmt) -> float:
            return float(self.db.scalar(stmt) or 0)

        base = [Invoice.organization_id == self.org_id,
                Invoice.branch_id.in_(branch_ids or [uuid.UUID(int=0)]),
                Invoice.status != InvoiceStatus.CANCELLED]

        expected = money(select(func.sum(Invoice.total)).where(
            *base, Invoice.invoice_date >= period, Invoice.invoice_date < next_period))
        collected = money(select(func.sum(Invoice.paid_amount)).where(
            *base, Invoice.invoice_date >= period, Invoice.invoice_date < next_period))
        outstanding = money(select(func.sum(Invoice.balance)).where(*base))
        overdue = money(select(func.sum(Invoice.balance)).where(
            *base, Invoice.due_date < date.today(), Invoice.balance > 0))

        upcoming = list(self.db.scalars(
            self._scoped_invoices()
            .options(selectinload(Invoice.resident))
            .where(Invoice.balance > 0, Invoice.status != InvoiceStatus.CANCELLED)
            .order_by(Invoice.due_date).limit(8)).all())
        recent = list(self.db.scalars(
            self._scoped_payments()
            .options(selectinload(Payment.resident))
            .order_by(Payment.created_at.desc()).limit(8)).all())

        by_method = [
            {"method": m, "amount": float(a or 0), "count": n}
            for m, a, n in self.db.execute(
                select(Payment.method, func.sum(Payment.amount), func.count(Payment.id))
                .where(Payment.organization_id == self.org_id,
                       Payment.branch_id.in_(branch_ids or [uuid.UUID(int=0)]),
                       Payment.status == PaymentStatus.VERIFIED,
                       Payment.payment_date >= period)
                .group_by(Payment.method)).all()
        ]

        return {
            "period": period.isoformat(),
            "expected": round(expected, 2),
            "collected": round(collected, 2),
            "pending": round(max(expected - collected, 0), 2),
            "outstanding": round(outstanding, 2),
            "overdue": round(overdue, 2),
            "collection_rate": round(collected / expected * 100, 1) if expected else 0.0,
            "unverified_payments": self.db.scalar(
                select(func.count(Payment.id)).where(
                    Payment.organization_id == self.org_id,
                    Payment.branch_id.in_(branch_ids or [uuid.UUID(int=0)]),
                    Payment.status == PaymentStatus.PENDING)) or 0,
            "by_method": by_method,
            "upcoming": [
                {"id": str(i.id), "invoice_number": i.invoice_number,
                 "resident": i.resident.full_name if i.resident else "—",
                 "due_date": i.due_date.isoformat(), "balance": float(i.balance),
                 "status": i.status,
                 "days_overdue": (date.today() - i.due_date).days}
                for i in upcoming],
            "recent_payments": [
                {"id": str(p.id), "payment_number": p.payment_number,
                 "resident": p.resident.full_name if p.resident else "—",
                 "amount": float(p.amount), "method": p.method, "status": p.status,
                 "payment_date": p.payment_date.isoformat()}
                for p in recent],
        }
