"""
A resident's notice that they are moving out.

PGs work on a notice period (usually a month): the resident says "I am leaving
on the 30th" well ahead, the bed goes on the market, and the deposit is settled
against the notice given. Before this table the only way out was the owner's
Checkout button on the day - nothing recorded that the resident had told anyone.

A row per notice rather than two columns on the resident, because notices get
withdrawn and given again, and "she gave notice in March, withdrew, and gave it
again in May" is exactly the history a deposit dispute turns on.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey
from app.models.enums import CheckoutNoticeStatus


class CheckoutNotice(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "checkout_notices"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True)
    resident_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True)

    notice_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_checkout_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(
        SAEnum(CheckoutNoticeStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=CheckoutNoticeStatus.SUBMITTED, index=True)
    # "resident" or "staff" - who typed it in.
    raised_by: Mapped[str] = mapped_column(String(20), nullable=False, default="resident")
    # The PG's policy at the moment notice was given. Stored, not looked up,
    # because changing the policy later must not rewrite an old notice.
    notice_days_required: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # What the resident's status was before notice, restored on withdrawal.
    previous_status: Mapped[str | None] = mapped_column(String(20))

    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    office_note: Mapped[str | None] = mapped_column(String(300))

    resident: Mapped["Customer"] = relationship()

    __table_args__ = (
        Index("ix_checkout_notices_org_status", "organization_id", "status"),
    )

    @property
    def days_given(self) -> int:
        return (self.planned_checkout_date - self.notice_date).days

    @property
    def short_notice(self) -> bool:
        return self.days_given < self.notice_days_required
