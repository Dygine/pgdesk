"""
Property hierarchy endpoints: branches, buildings, floors, rooms, beds.

Each route states the permission it needs. `require_tenant` keeps master admins
out - they have no organisation scope, so a tenant endpoint would have nothing
to filter by.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.core.dependencies import CurrentScope, DbSession, require, require_tenant
from app.core.responses import ok, paginated
from app.models import Bed, Branch, Building, Floor, Room
from app.schemas.property import (
    BedCreate, BedUpdate, BranchCreate, BranchUpdate, BuildingCreate, BuildingUpdate,
    FloorCreate, FloorUpdate, RoomCreate, RoomUpdate,
)
from app.services.property_service import PropertyService

router = APIRouter(tags=["property"])
Tenant = Annotated[CurrentScope, Depends(require_tenant)]


def _svc(db, scope) -> PropertyService:
    return PropertyService(db, scope)


# ------------------------------------------------------------- serialisers
def _bed(b: Bed) -> dict:
    return {
        "id": str(b.id), "branch_id": str(b.branch_id), "room_id": str(b.room_id),
        "bed_number": b.bed_number, "bed_code": b.bed_code, "status": b.status,
        "rent_amount": float(b.rent_amount), "notes": b.notes,
        "current_customer_id": str(b.current_customer_id) if b.current_customer_id else None,
    }


def _room(r: Room) -> dict:
    return {
        "id": str(r.id), "branch_id": str(r.branch_id), "building_id": str(r.building_id),
        "floor_id": str(r.floor_id), "room_number": r.room_number,
        "room_type": r.room_type, "capacity": r.capacity,
        "gender_policy": r.gender_policy, "rent_amount": float(r.rent_amount),
        "deposit_amount": float(r.deposit_amount), "has_ac": r.has_ac,
        "has_attached_bathroom": r.has_attached_bathroom, "description": r.description,
        "status": r.status, "occupancy": r.occupancy,
        "beds": [_bed(b) for b in sorted(r.beds, key=lambda x: x.bed_number)],
    }


# ---------------------------------------------------------------- branches
@router.get("/branches", summary="List branches")
def list_branches(db: DbSession, scope: Tenant,
                  _: None = Depends(require("branches.view")),
                  search: str | None = None,
                  status_filter: str | None = Query(default=None, alias="status"),
                  page: int = Query(default=1, ge=1),
                  page_size: int = Query(default=50, ge=1, le=200)) -> dict:
    service = _svc(db, scope)
    rows, total = service.list_branches(search=search, status=status_filter,
                                        page=page, page_size=page_size)
    payload = []
    for b in rows:
        payload.append({
            "id": str(b.id), "name": b.name, "code": b.code, "address": b.address,
            "city": b.city, "state": b.state, "pincode": b.pincode,
            "contact_number": b.contact_number,
            "opened_on": b.opened_on.isoformat() if b.opened_on else None,
            "status": b.status,
            "counts": {
                "buildings": db.scalar(select(func.count(Building.id)).where(
                    Building.branch_id == b.id)) or 0,
                "floors": db.scalar(select(func.count(Floor.id)).where(
                    Floor.branch_id == b.id)) or 0,
                "rooms": db.scalar(select(func.count(Room.id)).where(
                    Room.branch_id == b.id)) or 0,
                "beds": db.scalar(select(func.count(Bed.id)).where(
                    Bed.branch_id == b.id)) or 0,
                "occupied": db.scalar(select(func.count(Bed.id)).where(
                    Bed.branch_id == b.id, Bed.status == "OCCUPIED")) or 0,
            },
        })
    return paginated(payload, page, page_size, total)


@router.post("/branches", status_code=status.HTTP_201_CREATED, summary="Create a branch")
def create_branch(body: BranchCreate, db: DbSession, scope: Tenant,
                  _: None = Depends(require("branches.create"))) -> dict:
    branch = _svc(db, scope).create_branch(body.model_dump())
    db.commit()
    return ok({"id": str(branch.id), "name": branch.name, "code": branch.code},
              message=f"{branch.name} created.")


@router.patch("/branches/{branch_id}", summary="Edit a branch")
def update_branch(branch_id: uuid.UUID, body: BranchUpdate, db: DbSession, scope: Tenant,
                  _: None = Depends(require("branches.edit"))) -> dict:
    branch = _svc(db, scope).update_branch(branch_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok({"id": str(branch.id), "name": branch.name}, message="Branch updated.")


@router.delete("/branches/{branch_id}", summary="Deactivate a branch")
def deactivate_branch(branch_id: uuid.UUID, db: DbSession, scope: Tenant,
                      _: None = Depends(require("branches.delete"))) -> dict:
    """Deactivates rather than deletes - the history behind a branch stays intact."""
    branch = _svc(db, scope).deactivate_branch(branch_id)
    db.commit()
    return ok({"id": str(branch.id), "status": branch.status},
              message=f"{branch.name} deactivated.")


# --------------------------------------------------------------- buildings
@router.get("/buildings", summary="List buildings")
def list_buildings(db: DbSession, scope: Tenant,
                   _: None = Depends(require("buildings.view", "property.view")),
                   branch_id: uuid.UUID | None = None,
                   search: str | None = None,
                   status_filter: str | None = Query(default=None, alias="status")) -> dict:
    rows = _svc(db, scope).list_buildings(branch_id=branch_id, search=search,
                                          status=status_filter)
    return ok([
        {"id": str(b.id), "branch_id": str(b.branch_id), "name": b.name, "code": b.code,
         "description": b.description, "number_of_floors": b.number_of_floors,
         "status": b.status,
         "counts": {
             "floors": db.scalar(select(func.count(Floor.id)).where(
                 Floor.building_id == b.id)) or 0,
             "rooms": db.scalar(select(func.count(Room.id)).where(
                 Room.building_id == b.id)) or 0,
         }}
        for b in rows
    ])


@router.post("/buildings", status_code=status.HTTP_201_CREATED, summary="Create a building")
def create_building(body: BuildingCreate, db: DbSession, scope: Tenant,
                    _: None = Depends(require("buildings.create", "property.create"))) -> dict:
    building = _svc(db, scope).create_building(body.model_dump())
    db.commit()
    return ok({"id": str(building.id), "name": building.name, "code": building.code},
              message=f"{building.name} created.")


@router.patch("/buildings/{building_id}", summary="Edit a building")
def update_building(building_id: uuid.UUID, body: BuildingUpdate, db: DbSession,
                    scope: Tenant,
                    _: None = Depends(require("buildings.edit", "property.edit"))) -> dict:
    building = _svc(db, scope).update_building(building_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok({"id": str(building.id), "name": building.name}, message="Building updated.")


@router.delete("/buildings/{building_id}", summary="Delete a building")
def delete_building(building_id: uuid.UUID, db: DbSession, scope: Tenant,
                    _: None = Depends(require("buildings.delete", "property.delete"))) -> dict:
    _svc(db, scope).delete_building(building_id)
    db.commit()
    return ok(None, message="Building deleted.")


# ------------------------------------------------------------------ floors
@router.get("/floors", summary="List floors")
def list_floors(db: DbSession, scope: Tenant,
                _: None = Depends(require("floors.view", "property.view")),
                branch_id: uuid.UUID | None = None,
                building_id: uuid.UUID | None = None,
                status_filter: str | None = Query(default=None, alias="status")) -> dict:
    rows = _svc(db, scope).list_floors(branch_id=branch_id, building_id=building_id,
                                       status=status_filter)
    return ok([
        {"id": str(f.id), "branch_id": str(f.branch_id), "building_id": str(f.building_id),
         "floor_number": f.floor_number, "name": f.name, "status": f.status,
         "counts": {"rooms": db.scalar(select(func.count(Room.id)).where(
             Room.floor_id == f.id)) or 0}}
        for f in rows
    ])


@router.post("/floors", status_code=status.HTTP_201_CREATED, summary="Create a floor")
def create_floor(body: FloorCreate, db: DbSession, scope: Tenant,
                 _: None = Depends(require("floors.create", "property.create"))) -> dict:
    floor = _svc(db, scope).create_floor(body.model_dump())
    db.commit()
    return ok({"id": str(floor.id), "name": floor.name,
               "floor_number": floor.floor_number}, message=f"{floor.name} created.")


@router.patch("/floors/{floor_id}", summary="Edit a floor")
def update_floor(floor_id: uuid.UUID, body: FloorUpdate, db: DbSession, scope: Tenant,
                 _: None = Depends(require("floors.edit", "property.edit"))) -> dict:
    floor = _svc(db, scope).update_floor(floor_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok({"id": str(floor.id), "name": floor.name}, message="Floor updated.")


@router.delete("/floors/{floor_id}", summary="Delete a floor")
def delete_floor(floor_id: uuid.UUID, db: DbSession, scope: Tenant,
                 _: None = Depends(require("floors.delete", "property.delete"))) -> dict:
    _svc(db, scope).delete_floor(floor_id)
    db.commit()
    return ok(None, message="Floor deleted.")


# ------------------------------------------------------------------- rooms
@router.get("/rooms", summary="List rooms")
def list_rooms(db: DbSession, scope: Tenant,
               _: None = Depends(require("rooms.view")),
               branch_id: uuid.UUID | None = None,
               building_id: uuid.UUID | None = None,
               floor_id: uuid.UUID | None = None,
               room_type: str | None = None,
               search: str | None = None,
               status_filter: str | None = Query(default=None, alias="status"),
               page: int = Query(default=1, ge=1),
               page_size: int = Query(default=50, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_rooms(
        branch_id=branch_id, building_id=building_id, floor_id=floor_id,
        room_type=room_type, search=search, status=status_filter,
        page=page, page_size=page_size,
    )
    return paginated([_room(r) for r in rows], page, page_size, total)


@router.get("/rooms/{room_id}", summary="Room detail")
def get_room(room_id: uuid.UUID, db: DbSession, scope: Tenant,
             _: None = Depends(require("rooms.view"))) -> dict:
    return ok(_room(_svc(db, scope).get_room(room_id)))


@router.post("/rooms", status_code=status.HTTP_201_CREATED, summary="Create a room")
def create_room(body: RoomCreate, db: DbSession, scope: Tenant,
                _: None = Depends(require("rooms.create"))) -> dict:
    """Beds are generated from capacity unless `generate_beds` is false."""
    data = body.model_dump()
    generate = data.pop("generate_beds", True)
    room = _svc(db, scope).create_room(data, generate_beds=generate)
    db.commit()
    db.refresh(room)
    return ok(_room(room), message=f"Room {room.room_number} created.")


@router.patch("/rooms/{room_id}", summary="Edit a room")
def update_room(room_id: uuid.UUID, body: RoomUpdate, db: DbSession, scope: Tenant,
                _: None = Depends(require("rooms.edit"))) -> dict:
    room = _svc(db, scope).update_room(room_id, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(room)
    return ok(_room(room), message="Room updated.")


@router.delete("/rooms/{room_id}", summary="Delete a room")
def delete_room(room_id: uuid.UUID, db: DbSession, scope: Tenant,
                _: None = Depends(require("rooms.delete"))) -> dict:
    _svc(db, scope).delete_room(room_id)
    db.commit()
    return ok(None, message="Room deleted.")


# -------------------------------------------------------------------- beds
@router.get("/beds", summary="List beds")
def list_beds(db: DbSession, scope: Tenant,
              _: None = Depends(require("beds.view")),
              branch_id: uuid.UUID | None = None,
              room_id: uuid.UUID | None = None,
              search: str | None = None,
              status_filter: str | None = Query(default=None, alias="status"),
              page: int = Query(default=1, ge=1),
              page_size: int = Query(default=100, ge=1, le=500)) -> dict:
    rows, total = _svc(db, scope).list_beds(
        branch_id=branch_id, room_id=room_id, search=search,
        status=status_filter, page=page, page_size=page_size)
    return paginated([_bed(b) for b in rows], page, page_size, total)


@router.post("/beds", status_code=status.HTTP_201_CREATED, summary="Create a bed")
def create_bed(body: BedCreate, db: DbSession, scope: Tenant,
               _: None = Depends(require("beds.create"))) -> dict:
    bed = _svc(db, scope).create_bed(body.model_dump())
    db.commit()
    return ok(_bed(bed), message=f"Bed {bed.bed_number} created.")


@router.patch("/beds/{bed_id}", summary="Edit a bed or change its status")
def update_bed(bed_id: uuid.UUID, body: BedUpdate, db: DbSession, scope: Tenant,
               _: None = Depends(require("beds.edit", "beds.block"))) -> dict:
    bed = _svc(db, scope).update_bed(bed_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok(_bed(bed), message="Bed updated.")


@router.delete("/beds/{bed_id}", summary="Delete a bed")
def delete_bed(bed_id: uuid.UUID, db: DbSession, scope: Tenant,
               _: None = Depends(require("beds.delete"))) -> dict:
    _svc(db, scope).delete_bed(bed_id)
    db.commit()
    return ok(None, message="Bed deleted.")


# --------------------------------------------------------------- blueprint
@router.get("/property/blueprint", summary="The full hierarchy, nested")
def blueprint(db: DbSession, scope: Tenant,
              _: None = Depends(require("rooms.view")),
              branch_id: uuid.UUID | None = None) -> dict:
    """Branch -> building -> floor -> room -> bed, with occupancy at every level."""
    return ok(_svc(db, scope).blueprint(branch_id))
