"""Branch, building, floor, room and bed contracts."""
import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ---------------------------------------------------------------- branches
class BranchOut(ORMModel):
    id: uuid.UUID
    name: str
    code: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    contact_number: str | None = None
    opened_on: date | None = None
    status: str
    counts: dict[str, int] = Field(default_factory=dict)


class BranchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=1, max_length=10)
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    contact_number: str | None = None
    opened_on: date | None = None
    status: str | None = None


class BranchUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    contact_number: str | None = None
    status: str | None = None


# --------------------------------------------------------------- buildings
class BuildingOut(ORMModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    number_of_floors: int
    status: str
    counts: dict[str, int] = Field(default_factory=dict)


class BuildingCreate(BaseModel):
    branch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=20)
    description: str | None = None
    number_of_floors: int = Field(default=1, ge=1, le=200)
    status: str | None = None


class BuildingUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    number_of_floors: int | None = Field(default=None, ge=1, le=200)
    status: str | None = None


# ------------------------------------------------------------------ floors
class FloorOut(ORMModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    building_id: uuid.UUID
    floor_number: int
    name: str
    status: str
    counts: dict[str, int] = Field(default_factory=dict)


class FloorCreate(BaseModel):
    building_id: uuid.UUID
    floor_number: int = Field(ge=-5, le=200)
    name: str | None = None
    status: str | None = None


class FloorUpdate(BaseModel):
    name: str | None = None
    status: str | None = None


# ------------------------------------------------------------------- rooms
class BedOut(ORMModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    room_id: uuid.UUID
    bed_number: str
    bed_code: str | None = None
    status: str
    rent_amount: float
    notes: str | None = None
    current_customer_id: uuid.UUID | None = None


class RoomOut(ORMModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    building_id: uuid.UUID
    floor_id: uuid.UUID
    room_number: str
    room_type: str
    capacity: int
    gender_policy: str
    rent_amount: float
    deposit_amount: float
    has_ac: bool
    has_attached_bathroom: bool
    description: str | None = None
    status: str
    beds: list[BedOut] = Field(default_factory=list)
    occupancy: dict = Field(default_factory=dict)


class RoomCreate(BaseModel):
    floor_id: uuid.UUID
    room_number: str = Field(min_length=1, max_length=20)
    room_type: str = "Single"
    capacity: int = Field(default=1, ge=1, le=30)
    gender_policy: str = "ANY"
    rent_amount: float = Field(default=0, ge=0)
    deposit_amount: float | None = Field(default=None, ge=0)
    has_ac: bool = False
    has_attached_bathroom: bool = True
    description: str | None = None
    status: str | None = None
    generate_beds: bool = Field(
        default=True, description="Create one bed per unit of capacity."
    )


class RoomUpdate(BaseModel):
    room_number: str | None = None
    room_type: str | None = None
    gender_policy: str | None = None
    rent_amount: float | None = Field(default=None, ge=0)
    deposit_amount: float | None = Field(default=None, ge=0)
    has_ac: bool | None = None
    has_attached_bathroom: bool | None = None
    description: str | None = None
    status: str | None = None


# -------------------------------------------------------------------- beds
class BedCreate(BaseModel):
    room_id: uuid.UUID
    bed_number: str = Field(min_length=1, max_length=10)
    bed_code: str | None = None
    status: str | None = None
    rent_amount: float | None = Field(default=None, ge=0)
    notes: str | None = None


class BedUpdate(BaseModel):
    bed_number: str | None = None
    bed_code: str | None = None
    status: str | None = None
    rent_amount: float | None = Field(default=None, ge=0)
    notes: str | None = None
