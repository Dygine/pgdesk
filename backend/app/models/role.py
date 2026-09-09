"""
Roles and permissions.

`permissions` is a catalogue table seeded from the same list the React app reads
(`src/data/permissions.js`). A role holds rows in `role_permissions`; there is no
free-text permission anywhere, so a typo cannot silently grant nothing.

Wildcards ('*', 'rooms.*') are an input convenience only - they are expanded to
concrete rows before being written.
"""
import uuid

from sqlalchemy import Boolean, Column, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", PgUUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

user_branches = Table(
    "user_branches",
    Base.metadata,
    Column("user_id", PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("branch_id", PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(Base, UUIDPrimaryKey, Timestamps):
    """Platform-wide catalogue. Not tenant data - every org draws from the same list."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    # Master-admin permissions live in their own namespace and never touch tenant data.
    is_master: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    __table_args__ = (UniqueConstraint("module", "action", name="uq_permissions_module_action"),)

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"


class Role(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    """
    Tenant-owned and fully editable. A PG owner creates whatever roles their
    operation needs; nothing here is hardcoded to Admin/Manager/Staff.
    """

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    # A system role (the Owner) cannot be deleted or stripped of permissions.
    is_system_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True => the holder sees every branch without an explicit user_branches row.
    all_branches: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, lazy="selectin")
    users: Mapped[list["User"]] = relationship(secondary=user_roles, back_populates="roles")

    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_roles_org_name"),)

    @property
    def permission_codes(self) -> list[str]:
        """Serialised to the frontend, which expects a flat list of 'module.action'."""
        return sorted(p.code for p in self.permissions)

    def __repr__(self) -> str:
        return f"<Role {self.name}>"
