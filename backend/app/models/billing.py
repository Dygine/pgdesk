"""
Rent, invoices and payments.

Three decisions worth stating.

**Invoice totals are stored, not computed on read.** A recomputed total would
change if a plan price or a tax rule changed later, which would silently rewrite
history. `Invoice.recalculate()` is called explicitly whenever items or payments
change, and the stored figures are what the resident was actually billed.

**Only a VERIFIED payment moves the balance.** A cash payment recorded at the
front desk starts PENDING; the accountant verifies it. This mirrors how a PG
actually works and means an unverified entry cannot make an invoice look paid.

**Invoice numbers are per-organisation.** Two PGs both start at INV-0001; the
unique constraint is scoped to the tenant, not global.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey
from app.models.enums import (
    InvoiceItemKind, InvoiceStatus, PaymentMethod, PaymentStatus,
)


class Invoice(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "invoices"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    resident_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True)

    invoice_number: Mapped[str] = mapped_column(String(30), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # The billing month this invoice covers, as the first of that month. Used to
    # stop the generator issuing two rent invoices for the same period.
    period: Mapped[date | None] = mapped_column(Date, index=True)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    late_fee: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    paid_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    balance: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    status: Mapped[str] = mapped_column(
        SAEnum(InvoiceStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=InvoiceStatus.PENDING, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="invoice", lazy="selectin")
    resident: Mapped["Customer"] = relationship()

    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_number", name="uq_invoices_org_number"),
        Index("ix_invoices_org_branch_status", "organization_id", "branch_id", "status"),
        Index("ix_invoices_resident_period", "resident_id", "period"),
        CheckConstraint("total >= 0 AND paid_amount >= 0", name="ck_invoices_non_negative"),
    )

    def recalculate(self) -> None:
        """
        Re-derive the money columns from items and verified payments.

        Called after any change to either. Deliberately explicit rather than an
        ORM event: an implicit recalculation firing mid-transaction is very hard
        to reason about when a payment and an item change together.
        """
        charge = sum(
            float(i.amount) for i in self.items
            if i.kind != InvoiceItemKind.DISCOUNT
        )
        discount = sum(
            float(i.amount) for i in self.items
            if i.kind == InvoiceItemKind.DISCOUNT
        )
        self.subtotal = round(charge, 2)
        self.discount = round(discount, 2)
        self.total = round(charge - discount + float(self.late_fee) + float(self.tax), 2)

        self.paid_amount = round(sum(
            float(p.amount) for p in self.payments
            if p.status == PaymentStatus.VERIFIED
        ), 2)
        self.balance = round(float(self.total) - float(self.paid_amount), 2)

        if self.status == InvoiceStatus.CANCELLED:
            return
        if self.balance <= 0.009 and float(self.total) > 0:
            self.status = InvoiceStatus.PAID
        elif float(self.paid_amount) > 0:
            self.status = InvoiceStatus.PARTIAL
        elif self.due_date < date.today():
            self.status = InvoiceStatus.OVERDUE
        else:
            self.status = InvoiceStatus.PENDING


class InvoiceItem(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """
    One charge line. `kind` is a broad bucket for reporting; `description` is
    what the resident reads. A PG that invents a new charge adds a line with
    kind=OTHER rather than needing a schema change.
    """

    __tablename__ = "invoice_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False, index=True)

    kind: Mapped[str] = mapped_column(
        SAEnum(InvoiceItemKind, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=InvoiceItemKind.OTHER, index=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    invoice: Mapped[Invoice] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_invoice_items_non_negative"),
    )


class Payment(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "payments"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    resident_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True)
    # Nullable: an advance paid before an invoice exists is still a payment.
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), index=True)

    payment_number: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    method: Mapped[str] = mapped_column(
        SAEnum(PaymentMethod, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=PaymentMethod.CASH, index=True)
    reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        SAEnum(PaymentStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=PaymentStatus.PENDING, index=True)

    received_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    invoice: Mapped[Invoice | None] = relationship(back_populates="payments")
    resident: Mapped["Customer"] = relationship()

    __table_args__ = (
        UniqueConstraint("organization_id", "payment_number", name="uq_payments_org_number"),
        Index("ix_payments_org_branch_date", "organization_id", "branch_id", "payment_date"),
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )
