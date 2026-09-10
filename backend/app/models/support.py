"""
Helpdesk, back-office and system tables.

Complaints and queries are deliberately separate. A complaint is something
broken with an SLA and an assignee; a query is a question with an answer. Fusing
them would mean one status enum that fits neither.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, ForeignKey, Index,
    Integer, JSON, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey
from app.models.enums import (
    AnnouncementAudience, AssetStatus, ComplaintStatus, InventoryTxnType,
    NotificationType, PublishStatus, QueryStatus, TicketPriority,
)


# ---------------------------------------------------------------- complaints
class Complaint(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "complaints"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"))

    ticket_number: Mapped[str] = mapped_column(String(30), nullable=False)
    # Free text rather than an enum: every PG has its own list, and a category
    # nobody can add is a category people work around.
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    priority: Mapped[str] = mapped_column(
        SAEnum(TicketPriority, native_enum=False, length=10, validate_strings=True),
        nullable=False, default=TicketPriority.MEDIUM, index=True)
    status: Mapped[str] = mapped_column(
        SAEnum(ComplaintStatus, native_enum=False, length=14, validate_strings=True),
        nullable=False, default=ComplaintStatus.OPEN, index=True)

    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)

    resident: Mapped["Customer | None"] = relationship()
    updates: Mapped[list["ComplaintUpdate"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("organization_id", "ticket_number", name="uq_complaints_org_ticket"),
        Index("ix_complaints_org_branch_status", "organization_id", "branch_id", "status"),
    )


class ComplaintUpdate(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """The thread on a ticket. `is_internal` hides a note from the resident."""

    __tablename__ = "complaint_updates"

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False, index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    author_resident_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"))
    author_name: Mapped[str] = mapped_column(String(160), nullable=False)

    message: Mapped[str] = mapped_column(Text, nullable=False)
    status_after: Mapped[str | None] = mapped_column(String(14))
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    complaint: Mapped[Complaint] = relationship(back_populates="updates")


# ------------------------------------------------------------------- queries
class SupportQuery(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """
    A question, not a fault.

    Messages live in their own table from the start so a real conversation - and
    later a chat UI - needs no migration.
    """

    __tablename__ = "support_queries"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True)

    ticket_number: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="General")
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(QueryStatus, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=QueryStatus.OPEN, index=True)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    resident: Mapped["Customer | None"] = relationship()
    messages: Mapped[list["QueryMessage"]] = relationship(
        back_populates="query", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("organization_id", "ticket_number", name="uq_queries_org_ticket"),
    )


class QueryMessage(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "query_messages"

    query_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("support_queries.id", ondelete="CASCADE"),
        nullable=False, index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    author_resident_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"))
    author_name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    query: Mapped[SupportQuery] = relationship(back_populates="messages")


# ------------------------------------------------------------------ expenses
class Expense(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "expenses"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)

    expense_number: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    spent_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    vendor: Mapped[str | None] = mapped_column(String(160))
    payment_method: Mapped[str | None] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    attachment_reference: Mapped[str | None] = mapped_column(String(300))
    # Set when this expense is a staff salary, so the staff screen can show
    # who has been paid for which month and refuse paying the same month twice.
    staff_member_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("staff_members.id", ondelete="SET NULL"),
        index=True)
    salary_period: Mapped[date | None] = mapped_column(Date)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("organization_id", "expense_number", name="uq_expenses_org_number"),
        Index("ix_expenses_org_branch_date", "organization_id", "branch_id", "spent_on"),
        CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
    )


# ----------------------------------------------------------------- inventory
class InventoryItem(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "inventory_items"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)

    sku: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="pcs")
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    minimum_stock: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    location: Mapped[str | None] = mapped_column(String(120))
    supplier: Mapped[str | None] = mapped_column(String(160))
    purchase_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    transactions: Mapped[list["InventoryTransaction"]] = relationship(
        back_populates="item", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("branch_id", "sku", name="uq_inventory_branch_sku"),
        # Stock cannot go negative. Enforced here rather than only in the service,
        # because two concurrent stock-outs can both pass a service-level check.
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity_non_negative"),
    )

    @property
    def is_low(self) -> bool:
        return float(self.quantity) <= float(self.minimum_stock)


class InventoryTransaction(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """The ledger behind `InventoryItem.quantity`. Append-only."""

    __tablename__ = "inventory_transactions"

    item_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"),
        nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)

    txn_type: Mapped[str] = mapped_column(
        SAEnum(InventoryTxnType, native_enum=False, length=12, validate_strings=True),
        nullable=False, index=True)
    # Signed: +5 for a stock-in, -5 for a stock-out. Summing the column gives
    # the on-hand quantity, so the ledger and the cached total can be compared.
    quantity_delta: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(String(300))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    item: Mapped[InventoryItem] = relationship(back_populates="transactions")


# -------------------------------------------------------------------- assets
class Asset(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "assets"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)

    asset_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    warranty_until: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(120))
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"))
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(
        SAEnum(AssetStatus, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=AssetStatus.ACTIVE, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("organization_id", "asset_code", name="uq_assets_org_code"),
    )


# ------------------------------------------------------------- notifications
class Notification(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """
    An in-app notification.

    Delivery channels (email, SMS, WhatsApp, push) are deliberately not modelled
    yet: the record is written first and a dispatcher can read this table later
    without any of the producers changing.
    """

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True)

    kind: Mapped[str] = mapped_column(
        SAEnum(NotificationType, native_enum=False, length=24, validate_strings=True),
        nullable=False, default=NotificationType.SYSTEM, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    link: Mapped[str | None] = mapped_column(String(200))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read_at"),
        Index("ix_notifications_resident_read", "resident_id", "read_at"),
        CheckConstraint(
            "(user_id IS NOT NULL AND resident_id IS NULL) "
            "OR (user_id IS NULL AND resident_id IS NOT NULL)",
            name="ck_notifications_one_recipient"),
    )


class Announcement(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "announcements"

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), index=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(
        SAEnum(AnnouncementAudience, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=AnnouncementAudience.ALL, index=True)
    priority: Mapped[str] = mapped_column(
        SAEnum(TicketPriority, native_enum=False, length=10, validate_strings=True),
        nullable=False, default=TicketPriority.MEDIUM)
    status: Mapped[str] = mapped_column(
        SAEnum(PublishStatus, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=PublishStatus.PUBLISHED, index=True)
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


# ------------------------------------------------------------------ settings
class OrganizationSettings(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """
    One row per organisation.

    The named columns are the ones the backend actually branches on. Everything
    else lives in `extra`, so a new toggle does not need a migration - but a
    setting that changes behaviour gets a real column, because a JSON key that
    silently defaults is impossible to audit.
    """

    __tablename__ = "organization_settings"

    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    timezone: Mapped[str] = mapped_column(String(40), nullable=False, default="Asia/Kolkata")
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(20))

    rent_due_day: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    late_fee_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    late_fee_after_days: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    invoice_prefix: Mapped[str] = mapped_column(String(10), nullable=False, default="INV")

    # Two scans of the same QR inside this window are treated as one press.
    gate_duplicate_window_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60)
    visitor_approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)
    gate_pass_approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)

    food_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    laundry_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    meal_optout_cutoff_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    # Days of notice a resident is expected to give before moving out. A notice
    # shorter than this is accepted but flagged, because the deposit is
    # usually settled against it.
    checkout_notice_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30")
    # Which meals this PG serves, what it calls them and when. Null means the
    # defaults in operations_service.DEFAULT_MEAL_SCHEDULE.
    meal_schedule: Mapped[dict | None] = mapped_column(JSON)

    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_settings_org"),
        CheckConstraint("rent_due_day BETWEEN 1 AND 28", name="ck_settings_rent_due_day"),
    )
