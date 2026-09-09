import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, Enum as SAEnum, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Timestamps, UUIDPrimaryKey
from app.models.enums import OrganizationStatus


class Organization(Base, UUIDPrimaryKey, Timestamps):
    """
    A tenant. The root of every scoping decision in the system: an authenticated
    user resolves to exactly one organization, and every query they make is
    filtered by it.
    """

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(200))

    owner_name: Mapped[str] = mapped_column(String(160), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    owner_phone: Mapped[str | None] = mapped_column(String(20))

    address: Mapped[str | None] = mapped_column(String(400))
    city: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(80))
    pincode: Mapped[str | None] = mapped_column(String(10))

    gstin: Mapped[str | None] = mapped_column(String(20))
    pg_type: Mapped[str | None] = mapped_column(String(40))     # Gents PG / Ladies PG / Co-living
    gender: Mapped[str | None] = mapped_column(String(20))

    status: Mapped[str] = mapped_column(
        SAEnum(OrganizationStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False,
        default=OrganizationStatus.TRIAL,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(String(1000))
    storage_used_gb: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    onboarded_on: Mapped[date | None] = mapped_column(Date)

    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    branches: Mapped[list["Branch"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("storage_used_gb >= 0", name="ck_organizations_storage_non_negative"),
        Index("ix_organizations_status_name", "status", "name"),
    )

    def __repr__(self) -> str:
        return f"<Organization {self.slug} ({self.status})>"
