"""
People looking for a PG, and the enquiries they send.

Deliberately not a login. A seeker has no `organization_id` - they belong to no
tenant yet, which is the whole point - and every principal in this system is
scoped to one. Adding a third kind of account would mean touching the token
tables, the principal resolver and every isolation guarantee built on them, to
support someone whose entire interaction is "I saw your listing, call me".

So an enquiry is a row, not an account. The seeker proves their email with the
same one-time code the password reset uses, sends the enquiry, and the PG rings
them. When they move in the PG creates their resident account through the
ordinary check-in flow, which already exists and already does bed assignment,
rent and invoicing correctly.

The row IS tenant-scoped, because once it exists it belongs to the PG that
received it and must be invisible to every other PG.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey


class EnquiryStatus:
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    VISITED = "VISITED"
    CONVERTED = "CONVERTED"
    CLOSED = "CLOSED"

    ALL = (NEW, CONTACTED, VISITED, CONVERTED, CLOSED)


class PgEnquiry(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "pg_enquiries"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    message: Mapped[str | None] = mapped_column(Text)
    move_in_date: Mapped[date | None] = mapped_column(Date)

    status: Mapped[str] = mapped_column(String(20), nullable=False,
                                        default=EnquiryStatus.NEW, index=True)
    handled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    staff_notes: Mapped[str | None] = mapped_column(Text)

    #: Whether the address was proved by a code before this row was written.
    #: Always true today; kept as a column because an unverified channel (a
    #: phone call logged by staff) is an obvious future source, and a boolean
    #: added later would have to guess at history.
    email_verified: Mapped[bool] = mapped_column(nullable=False, default=True)

    requested_ip: Mapped[str | None] = mapped_column(String(64))

    branch: Mapped["Branch"] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status IN ('NEW', 'CONTACTED', 'VISITED', 'CONVERTED', 'CLOSED')",
            name="ck_pg_enquiries_status"),
        # The owner's inbox is "my newest enquiries", which without this is a
        # scan of every enquiry on the platform.
        Index("ix_pg_enquiries_org_status_time",
              "organization_id", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<PgEnquiry {self.full_name} -> {self.branch_id}>"
