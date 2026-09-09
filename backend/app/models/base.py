"""
Shared column mixins. Every table gets a UUID primary key and timestamps;
tenant-owned tables additionally get organization_id, and branch-owned tables
get branch_id.

Inheriting `TenantMixin` is the signal that a table is tenant data. Nothing in
`app/repositories` will query such a table without an organization filter.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """
    Marks a table as tenant-owned. The column is NOT NULL and indexed because
    every single query against these tables filters on it.
    """

    @declared_attr
    def organization_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            PgUUID(as_uuid=True),
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


class BranchMixin:
    """For rows that belong to one branch. Nullable where a row is org-wide."""

    @declared_attr
    def branch_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            PgUUID(as_uuid=True),
            ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        )


def tenant_branch_index(table_name: str) -> Index:
    """The composite every list endpoint hits. Added per-table in __table_args__."""
    return Index(
        f"ix_{table_name}_org_branch", "organization_id", "branch_id"
    )
