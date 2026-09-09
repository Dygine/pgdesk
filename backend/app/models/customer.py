"""
Resident.

Phase 5 completes this table: the placement chain (branch through bed), the
money that follows from it, emergency contacts, the lifecycle dates, and a QR
identity for the gate.

The placement columns are denormalised down the whole chain - a resident stores
`branch_id`, `building_id`, `floor_id`, `room_id` and `bed_id` rather than only
`bed_id`. Strictly the parents are derivable, but every operational query
("residents in this branch", "who is on the second floor") would otherwise be a
four-table join, and the branch filter that enforces isolation is the one filter
that must never be accidentally omitted.

A resident is a separate table from `users` on purpose: staff and residents have
different lifecycles, different identifiers and completely different
authorisation. Folding them together would mean one `is_customer` flag guarding
every query, which is exactly the sort of thing that gets forgotten once.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey
from app.models.enums import BillingCycle, CustomerStatus, KycIdType, KycStatus


class Customer(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "customers"

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # Placement. Every level is carried so operational queries never need the
    # full join, and so branch scoping is a single indexed predicate.
    building_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("buildings.id", ondelete="SET NULL"))
    floor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("floors.id", ondelete="SET NULL"))
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"), index=True)
    # `beds.current_customer_id` points back here, so these two tables form a
    # foreign-key cycle. Alembic orders the DDL fine, but metadata-driven
    # create_all/drop_all cannot sort a cycle - so this side is emitted as a
    # separate ALTER. The name matches what PostgreSQL generated for the
    # original inline constraint, which keeps autogenerate reporting no drift.
    bed_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("beds.id", ondelete="SET NULL",
                   use_alter=True, name="customers_bed_id_fkey"),
        index=True)

    first_name: Mapped[str | None] = mapped_column(String(80))
    last_name: Mapped[str | None] = mapped_column(String(80))
    full_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)

    # Nullable: a resident recorded at the enquiry stage has no portal login yet.
    # Nothing can authenticate against a NULL hash - see AuthService.authenticate.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(
        SAEnum(CustomerStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=CustomerStatus.ENQUIRY, index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    alternate_phone: Mapped[str | None] = mapped_column(String(20))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(10))
    address: Mapped[str | None] = mapped_column(String(400))
    city: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(80))
    pincode: Mapped[str | None] = mapped_column(String(10))
    occupation: Mapped[str | None] = mapped_column(String(120))

    emergency_contact_name: Mapped[str | None] = mapped_column(String(160))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20))
    emergency_contact_relation: Mapped[str | None] = mapped_column(String(60))

    joining_date: Mapped[date | None] = mapped_column(Date)
    expected_checkout_date: Mapped[date | None] = mapped_column(Date)
    actual_checkout_date: Mapped[date | None] = mapped_column(Date)

    monthly_rent: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    security_deposit: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    rent_due_day: Mapped[int] = mapped_column(nullable=False, default=5)

    # Agreed at check-in. Free text rather than an enum: a PG renames its meal
    # tiers constantly, and a rename must not require a migration. The food
    # module reads this to decide who is on the register by default.
    meal_plan: Mapped[str | None] = mapped_column(String(40))
    billing_cycle: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BillingCycle.MONTHLY,
        server_default=BillingCycle.MONTHLY)

    notes: Mapped[str | None] = mapped_column(Text)

    # Gate identity. A random opaque token, never the resident id: the QR is
    # printed on a card that gets photographed, shared and lost, so it must
    # reveal nothing and be revocable on its own.
    qr_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    branch: Mapped["Branch | None"] = relationship()
    kyc: Mapped[list["ResidentKyc"]] = relationship(
        back_populates="resident", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_customers_org_email"),
        Index("ix_customers_org_status", "organization_id", "status"),
    )

    @property
    def can_sign_in(self) -> bool:
        return bool(self.password_hash) and self.is_active and self.status not in (
            CustomerStatus.CHECKED_OUT, CustomerStatus.ARCHIVED
        )

    def __repr__(self) -> str:
        return f"<Customer {self.full_name}>"


class ResidentKyc(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """
    Identity documents, kept in their own table rather than as columns on the
    resident.

    Two reasons. A resident may present more than one document, and more
    importantly the number itself is sensitive: keeping it separate means the
    resident list, the dashboards and every report can be served without the
    column ever entering the query. Only the KYC endpoints read this table, and
    they return a masked number unless the caller holds `residents.kyc_view`.

    The document itself is referenced, never stored - file storage is a later
    concern and putting a scan in a database column is the wrong answer anyway.
    """

    __tablename__ = "resident_kyc"

    resident_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True)

    id_type: Mapped[str] = mapped_column(
        SAEnum(KycIdType, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=KycIdType.AADHAAR)
    id_number: Mapped[str] = mapped_column(String(80), nullable=False)
    document_reference: Mapped[str | None] = mapped_column(String(300))

    status: Mapped[str] = mapped_column(
        SAEnum(KycStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=KycStatus.SUBMITTED, index=True)
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    resident: Mapped["Customer"] = relationship(back_populates="kyc")

    __table_args__ = (
        UniqueConstraint("resident_id", "id_type", name="uq_resident_kyc_type"),
    )

    @property
    def masked_number(self) -> str:
        """Last four digits only. What every screen shows by default."""
        n = (self.id_number or "").strip()
        return f"{'X' * max(0, len(n) - 4)}{n[-4:]}" if n else ""
