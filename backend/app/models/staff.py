"""
The workforce list - cooks, cleaners, guards, wardens, managers.

Deliberately NOT the `users` table. A user is a login; a staff member is a
person the PG employs and pays. Most kitchen and housekeeping staff never sign
in to anything, and the owner still needs their phone number, their shift and
whether this month's salary has gone out. `user_id` links the two when the same
person also has a login, and is optional for exactly that reason.
"""
import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint, Date, Enum as SAEnum, ForeignKey, Index, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey
from app.models.enums import StaffStatus


class StaffMember(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "staff_members"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)

    full_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    # Free text: a PG names its roles its own way ("Cook", "Mess in-charge").
    designation: Mapped[str] = mapped_column(String(60), nullable=False)
    shift: Mapped[str | None] = mapped_column(String(60))
    monthly_salary: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    joining_date: Mapped[date | None] = mapped_column(Date)
    left_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        SAEnum(StaffStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=StaffStatus.ACTIVE, index=True)

    id_proof_reference: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(400))
    emergency_contact_name: Mapped[str | None] = mapped_column(String(160))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User | None"] = relationship()

    __table_args__ = (
        Index("ix_staff_members_org_branch", "organization_id", "branch_id"),
        CheckConstraint("monthly_salary >= 0", name="ck_staff_members_salary_non_negative"),
    )
