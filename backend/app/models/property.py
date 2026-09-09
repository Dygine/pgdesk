"""
The property hierarchy: Building -> Floor -> Room -> Bed.

Two decisions worth stating.

**Every level carries `organization_id` and `branch_id`, not just a parent FK.**
Strictly it is redundant - a bed's branch could be reached through room, floor,
building - but that would mean a four-table join on every list query, and worse,
a scoping filter that is easy to write wrong. Denormalising the two scoping
columns lets `TenantRepository` apply the same two filters to every table
uniformly, and lets the indexes that matter be simple composites.

**Uniqueness is scoped to the parent, not global.** Two branches may both have a
"Room 101"; two rooms may both have a "Bed A". The constraints below say exactly
that, so a duplicate is rejected by PostgreSQL rather than by whichever service
method happened to remember to check.
"""
import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Enum as SAEnum, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, Timestamps, UUIDPrimaryKey
from app.models.enums import BedStatus, BuildingStatus, FloorStatus, GenderPolicy, RoomStatus


class Building(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "buildings"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    number_of_floors: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        SAEnum(BuildingStatus, native_enum=False, length=24, validate_strings=True),
        nullable=False, default=BuildingStatus.ACTIVE, index=True,
    )

    branch: Mapped["Branch"] = relationship()
    floors: Mapped[list["Floor"]] = relationship(
        back_populates="building", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("branch_id", "code", name="uq_buildings_branch_code"),
        Index("ix_buildings_org_branch", "organization_id", "branch_id"),
        CheckConstraint("number_of_floors > 0", name="ck_buildings_floors_positive"),
    )


class Floor(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "floors"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    building_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 0 is the ground floor, -1 a basement. Signed on purpose.
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(FloorStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=FloorStatus.ACTIVE, index=True,
    )

    building: Mapped[Building] = relationship(back_populates="floors")
    rooms: Mapped[list["Room"]] = relationship(
        back_populates="floor", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("building_id", "floor_number", name="uq_floors_building_number"),
        Index("ix_floors_org_branch", "organization_id", "branch_id"),
    )


class Room(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "rooms"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    building_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    floor_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("floors.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    room_number: Mapped[str] = mapped_column(String(20), nullable=False)
    # Free text rather than an enum: PGs invent sharing types constantly
    # ("Four Sharing AC", "Dormitory 8"). The catalogue is a UI suggestion list.
    room_type: Mapped[str] = mapped_column(String(40), nullable=False, default="Single")
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    gender_policy: Mapped[str] = mapped_column(
        SAEnum(GenderPolicy, native_enum=False, length=10, validate_strings=True),
        nullable=False, default=GenderPolicy.ANY,
    )
    rent_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    deposit_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    has_ac: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_attached_bathroom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        SAEnum(RoomStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=RoomStatus.ACTIVE, index=True,
    )

    floor: Mapped[Floor] = relationship(back_populates="rooms")
    beds: Mapped[list["Bed"]] = relationship(
        back_populates="room", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("floor_id", "room_number", name="uq_rooms_floor_number"),
        Index("ix_rooms_org_branch", "organization_id", "branch_id"),
        CheckConstraint("capacity > 0", name="ck_rooms_capacity_positive"),
        CheckConstraint("rent_amount >= 0 AND deposit_amount >= 0", name="ck_rooms_money_non_negative"),
    )

    @property
    def occupancy(self) -> dict:
        """Room occupancy is derived from bed status, never stored."""
        total = len(self.beds)
        occupied = sum(1 for b in self.beds if b.status == BedStatus.OCCUPIED)
        available = sum(1 for b in self.beds if b.status == BedStatus.AVAILABLE)
        return {
            "total": total,
            "occupied": occupied,
            "available": available,
            "reserved": sum(1 for b in self.beds if b.status == BedStatus.RESERVED),
            "maintenance": sum(1 for b in self.beds if b.status == BedStatus.MAINTENANCE),
            "blocked": sum(1 for b in self.beds if b.status == BedStatus.BLOCKED),
            "rate": round(occupied / total * 100, 1) if total else 0.0,
        }


class Bed(Base, UUIDPrimaryKey, TenantMixin, Timestamps):
    __tablename__ = "beds"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    bed_number: Mapped[str] = mapped_column(String(10), nullable=False)
    # Human-readable label used on physical tags: KOR-A-1-101-A
    bed_code: Mapped[str | None] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(
        SAEnum(BedStatus, native_enum=False, length=20, validate_strings=True),
        nullable=False, default=BedStatus.AVAILABLE, index=True,
    )
    rent_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(300))

    current_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )

    room: Mapped[Room] = relationship(back_populates="beds")

    __table_args__ = (
        UniqueConstraint("room_id", "bed_number", name="uq_beds_room_number"),
        Index("ix_beds_org_branch_status", "organization_id", "branch_id", "status"),
        # A bed holding a resident must say so, and vice versa. Enforced here
        # rather than trusted, because the two get out of step under concurrency
        # and an "available" bed with an occupant is the worst bug this app can have.
        CheckConstraint(
            "(status = 'OCCUPIED' AND current_customer_id IS NOT NULL) "
            "OR (status <> 'OCCUPIED' AND current_customer_id IS NULL)",
            name="ck_beds_occupancy_consistent",
        ),
    )
