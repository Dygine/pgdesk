import uuid
from datetime import date

from sqlalchemy import Date, Enum as SAEnum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey
from app.models.enums import BranchStatus


class Branch(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """A physical location. The second scoping axis after the organization."""

    __tablename__ = "branches"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    address: Mapped[str | None] = mapped_column(String(400))
    city: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(80))
    pincode: Mapped[str | None] = mapped_column(String(10))
    contact_number: Mapped[str | None] = mapped_column(String(20))
    opened_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        SAEnum(BranchStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=BranchStatus.ACTIVE, index=True,
    )

    organization: Mapped["Organization"] = relationship(back_populates="branches")
    users: Mapped[list["User"]] = relationship(
        secondary="user_branches", back_populates="branches", viewonly=False
    )

    __table_args__ = (
        # Codes are unique inside a tenant, not globally - two PGs may both use "KOR".
        UniqueConstraint("organization_id", "code", name="uq_branches_org_code"),
        UniqueConstraint("organization_id", "name", name="uq_branches_org_name"),
    )

    def __repr__(self) -> str:
        return f"<Branch {self.code}>"
