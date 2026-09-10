import uuid
from datetime import date

from sqlalchemy import (
    Boolean, CheckConstraint, Date, Enum as SAEnum, Float, Integer, JSON,
    Numeric, String, Text, UniqueConstraint,
)
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

    # ------------------------------------------------------ public listing
    # Off by default, and that default is the important part. A PG owner who
    # discovers their address, rent and vacancy count are on a public page
    # because they signed up would be right to be angry - and a competitor
    # reading occupancy across a city is a real thing, not a hypothetical.
    # Listing is a decision, so it has to be made rather than inherited.
    listed_publicly: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True)
    listing_headline: Mapped[str | None] = mapped_column(String(160))
    listing_description: Mapped[str | None] = mapped_column(Text)
    #: What a bed starts at. Stored rather than derived from the rent on each
    #: resident, because those are negotiated individually and publishing the
    #: real minimum would expose what individual people pay.
    starting_rent: Mapped[Numeric | None] = mapped_column(Numeric(12, 2))
    #: "MALE", "FEMALE", "ANY". A string rather than an enum: PG gender policy
    #: is a marketing field that changes, not a state machine.
    gender_preference: Mapped[str | None] = mapped_column(String(10))
    amenities: Mapped[list | None] = mapped_column(JSON)
    contact_phone_public: Mapped[str | None] = mapped_column(String(20))

    # ------------------------------------------------- gate and self check-in
    # The gate's own QR. A resident scans this; the resident's own qr_token is
    # the reverse flow, scanned by a guard. Two tokens rather than one because
    # they answer different questions - "which gate is this" and "who are you" -
    # and because the gate token is printed on a wall where anyone can photograph
    # it, so it must never be usable as an identity.
    gate_qr_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    # Geofence. Nullable: a branch that has never been positioned simply cannot
    # offer self check-in, which is a clearer state than a default coordinate
    # somebody forgets to change.
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geofence_radius_m: Mapped[int] = mapped_column(Integer, nullable=False, default=150)
    self_checkin_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)

    organization: Mapped["Organization"] = relationship(back_populates="branches")
    users: Mapped[list["User"]] = relationship(
        secondary="user_branches", back_populates="branches", viewonly=False
    )

    __table_args__ = (
        # Codes are unique inside a tenant, not globally - two PGs may both use "KOR".
        UniqueConstraint("organization_id", "code", name="uq_branches_org_code"),
        UniqueConstraint("organization_id", "name", name="uq_branches_org_name"),
        # Declared here as well as in the migration so the test schema, which is
        # built with create_all, rejects the same values production does. A
        # constraint that exists only in the migration is one the suite can never
        # prove anything about.
        CheckConstraint("geofence_radius_m >= 10 AND geofence_radius_m <= 5000",
                        name="ck_branches_geofence_radius"),
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
                        name="ck_branches_latitude"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
                        name="ck_branches_longitude"),
    )

    def has_geofence(self) -> bool:
        """Positioned well enough to answer a self check-in."""
        return self.latitude is not None and self.longitude is not None

    def __repr__(self) -> str:
        return f"<Branch {self.code}>"
