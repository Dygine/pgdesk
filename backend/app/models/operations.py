"""
Daily operations: attendance, the gate, visitors, gate passes, food, laundry.

These tables share a shape - organisation, branch, a date, a status - and each
one is written by a different person standing in a different place, often on a
phone with poor signal. So every one of them carries its own natural-key unique
constraint rather than trusting the caller not to double-submit.
"""
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, Float, ForeignKey,
    Index, Integer, Numeric, String, Text, Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey
from app.models.enums import (
    AttendanceStatus, AttendanceSubject, GateDirection, GatePassStatus,
    LaundryRequestStatus, LaundrySlotStatus, MealStatus, MealType,
    TicketPriority, VisitorStatus,
)


# ---------------------------------------------------------------- attendance
class Attendance(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """
    One row per person per day. Residents and staff share the table because the
    questions asked of it are identical; `subject` separates them.
    """

    __tablename__ = "attendance"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    subject: Mapped[str] = mapped_column(
        SAEnum(AttendanceSubject, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=AttendanceSubject.RESIDENT, index=True)

    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)

    on_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        SAEnum(AttendanceStatus, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=AttendanceStatus.PRESENT, index=True)
    # "gate" (a QR scan wrote it) or "manual" (someone typed it).
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    notes: Mapped[str | None] = mapped_column(String(300))

    resident: Mapped["Customer | None"] = relationship()
    user: Mapped["User | None"] = relationship()

    __table_args__ = (
        UniqueConstraint("resident_id", "on_date", name="uq_attendance_resident_day"),
        UniqueConstraint("user_id", "on_date", name="uq_attendance_user_day"),
        Index("ix_attendance_org_branch_date", "organization_id", "branch_id", "on_date"),
        CheckConstraint(
            "(resident_id IS NOT NULL AND user_id IS NULL) "
            "OR (resident_id IS NULL AND user_id IS NOT NULL)",
            name="ck_attendance_one_subject"),
    )


class GateLog(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """
    Every entry and exit, from a QR scan or the security desk.

    Append-only: a gate log is evidence. Corrections are new rows, never edits.
    """

    __tablename__ = "gate_logs"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("visitors.id", ondelete="SET NULL"), index=True)

    direction: Mapped[str] = mapped_column(
        SAEnum(GateDirection, native_enum=False, length=10, validate_strings=True),
        nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True)
    gate: Mapped[str | None] = mapped_column(String(60))
    # "qr"   - a guard scanned the resident's code
    # "self" - the resident scanned the gate's code from their own phone
    # "manual" - typed at the desk
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="qr")
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(String(200))

    # Where the phone said it was, kept for every self check-in including the
    # refused ones. A geofence can be defeated by a mock-location app, so the
    # position is retained as evidence rather than thrown away once the decision
    # is made: a resident whose punches arrive from a scatter of impossible
    # coordinates is visible in the log even though no single scan was provable.
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    resident: Mapped["Customer | None"] = relationship()

    __table_args__ = (
        Index("ix_gate_logs_org_branch_time", "organization_id", "branch_id", "occurred_at"),
    )


# ------------------------------------------------------------------ visitors
class Visitor(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "visitors"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    resident_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    relation: Mapped[str | None] = mapped_column(String(60))
    purpose: Mapped[str | None] = mapped_column(String(200))
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        SAEnum(VisitorStatus, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=VisitorStatus.PENDING, index=True)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    id_proof_reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)

    resident: Mapped["Customer"] = relationship()

    __table_args__ = (
        Index("ix_visitors_org_branch_status", "organization_id", "branch_id", "status"),
    )


class GatePass(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "gate_passes"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    resident_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True)

    pass_number: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    destination: Mapped[str | None] = mapped_column(String(200))
    from_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_emergency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(
        SAEnum(GatePassStatus, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=GatePassStatus.PENDING, index=True)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(300))

    resident: Mapped["Customer"] = relationship()

    __table_args__ = (
        UniqueConstraint("organization_id", "pass_number", name="uq_gate_passes_org_number"),
        Index("ix_gate_passes_org_branch_status", "organization_id", "branch_id", "status"),
        CheckConstraint("to_at > from_at", name="ck_gate_passes_window"),
    )


# ---------------------------------------------------------------------- food
class FoodMenu(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "food_menus"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)

    on_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal: Mapped[str] = mapped_column(
        SAEnum(MealType, native_enum=False, length=12, validate_strings=True),
        nullable=False, index=True)
    items: Mapped[str] = mapped_column(Text, nullable=False)
    calories: Mapped[int | None] = mapped_column(Integer)
    serve_from: Mapped[time | None] = mapped_column(Time)
    serve_to: Mapped[time | None] = mapped_column(Time)
    notes: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        UniqueConstraint("branch_id", "on_date", "meal", name="uq_food_menu_branch_day_meal"),
    )


class FoodWeekMenu(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """
    The menu that repeats every week: Monday breakfast, Monday lunch, ...

    This is what a PG kitchen actually works from - the same weekly chart on
    the mess wall, month after month. A `FoodMenu` row for a specific date is
    now a *special* that overrides this for one day (a festival lunch), and
    specials older than a week are deleted automatically.
    """

    __tablename__ = "food_week_menus"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)    # 0 = Monday
    meal: Mapped[str] = mapped_column(
        SAEnum(MealType, native_enum=False, length=12, validate_strings=True),
        nullable=False)
    items: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        UniqueConstraint("branch_id", "weekday", "meal",
                         name="uq_food_week_menu_branch_day_meal"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_food_week_menus_weekday"),
    )


class MealAttendance(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """One row per resident per meal. The unique key is what stops double counting."""

    __tablename__ = "meal_attendance"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    resident_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True)

    on_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal: Mapped[str] = mapped_column(
        SAEnum(MealType, native_enum=False, length=12, validate_strings=True), nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(MealStatus, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=MealStatus.EXPECTED, index=True)
    marked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    resident: Mapped["Customer"] = relationship()

    __table_args__ = (
        UniqueConstraint("resident_id", "on_date", "meal", name="uq_meal_resident_day_meal"),
        Index("ix_meal_org_branch_date", "organization_id", "branch_id", "on_date"),
    )


# ------------------------------------------------------------------- laundry
class LaundrySlot(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "laundry_slots"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)

    on_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    status: Mapped[str] = mapped_column(
        SAEnum(LaundrySlotStatus, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=LaundrySlotStatus.AVAILABLE, index=True)

    requests: Mapped[list["LaundryRequest"]] = relationship(
        back_populates="slot", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("branch_id", "on_date", "start_time",
                         name="uq_laundry_slot_branch_day_start"),
        CheckConstraint("capacity > 0", name="ck_laundry_slot_capacity"),
        CheckConstraint("end_time > start_time", name="ck_laundry_slot_window"),
    )

    @property
    def booked(self) -> int:
        return sum(
            1 for r in self.requests
            if r.status != LaundryRequestStatus.CANCELLED
        )


class LaundryRequest(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "laundry_requests"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    resident_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True)
    slot_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("laundry_slots.id", ondelete="CASCADE"),
        nullable=False, index=True)

    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        SAEnum(LaundryRequestStatus, native_enum=False, length=12, validate_strings=True),
        nullable=False, default=LaundryRequestStatus.BOOKED, index=True)
    notes: Mapped[str | None] = mapped_column(String(300))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    slot: Mapped[LaundrySlot] = relationship(back_populates="requests")
    resident: Mapped["Customer"] = relationship()

    __table_args__ = (
        # One booking per resident per slot: the database refuses the double-tap
        # rather than the handler having to notice it.
        UniqueConstraint("resident_id", "slot_id", name="uq_laundry_resident_slot"),
        CheckConstraint("item_count > 0", name="ck_laundry_item_count"),
    )
