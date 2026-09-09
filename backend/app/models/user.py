import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, ForeignKey,
    Index, String, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Timestamps, UUIDPrimaryKey
from app.models.enums import UserStatus


class User(Base, UUIDPrimaryKey, Timestamps):
    """
    A staff account.

    `organization_id` is nullable for exactly one reason: the platform's master
    admins sit outside every tenant. Every other user must belong to one, which
    the CHECK constraint below enforces at the database level rather than by
    convention.
    """

    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    employee_id: Mapped[str | None] = mapped_column(String(40))

    # Never a plaintext password. Argon2id by default - see app/core/security.py.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_master_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(
        SAEnum(UserStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=UserStatus.ACTIVE, index=True,
    )

    joining_date: Mapped[date | None] = mapped_column(Date)
    # Phase 13 staff profile. Deliberately columns on User rather than a separate
    # staff table: a second table would mean a second identity to keep in step
    # with roles and branch assignments, which is exactly the split the brief
    # warned against.
    department: Mapped[str | None] = mapped_column(String(40), index=True)
    designation: Mapped[str | None] = mapped_column(String(80))
    emergency_contact_name: Mapped[str | None] = mapped_column(String(160))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["Role"]] = relationship(
        secondary="user_roles", back_populates="users", lazy="selectin"
    )
    branches: Mapped[list["Branch"]] = relationship(
        secondary="user_branches", back_populates="users", lazy="selectin"
    )

    __table_args__ = (
        # Email is unique per tenant, not globally: the same person may legitimately
        # hold accounts at two different PGs.
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        # A UNIQUE constraint treats NULLs as distinct, so it would not stop two
        # master admins sharing an email. A partial unique index does.
        Index(
            "uq_users_master_email",
            "email",
            unique=True,
            postgresql_where=text("organization_id IS NULL"),
        ),
        Index("ix_users_org_status", "organization_id", "status"),
        CheckConstraint(
            "(is_master_admin AND organization_id IS NULL) "
            "OR (NOT is_master_admin AND organization_id IS NOT NULL)",
            name="ck_users_master_has_no_org",
        ),
    )

    @property
    def all_branches(self) -> bool:
        return any(r.all_branches for r in self.roles)

    @property
    def permission_codes(self) -> set[str]:
        """Union across every role the user holds."""
        return {p.code for role in self.roles for p in role.permissions}

    def __repr__(self) -> str:
        return f"<User {self.email}{' [master]' if self.is_master_admin else ''}>"
