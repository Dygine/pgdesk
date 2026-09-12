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
from datetime import datetime, timezone

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Bed, Branch, BranchPhoto, Building, Floor, PgEnquiry, Room
from app.models.enquiry import EnquiryStatus
from app.schemas.property import (
    BedCreate, BedUpdate, BranchCreate, BranchListingUpdate, BranchLocationUpdate,
    BranchPhotoReorder, BranchPhotoUpload, BranchUpdate, EnquiryUpdate,
    BuildingCreate, BuildingUpdate, FloorCreate, FloorUpdate, RoomCreate, RoomUpdate,
)
from app.services.property_service import BranchPhotoService, PropertyService
from app.utils import qr_payload

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
            "latitude": b.latitude, "longitude": b.longitude,
            "geofence_radius_m": b.geofence_radius_m,
            "self_checkin_enabled": b.self_checkin_enabled,
            # The token is returned to staff who can already edit the branch, and
            # is printed on a public wall anyway - it identifies a gate, never a
            # person, and confers nothing without a resident login and a position
            # inside the fence.
            "gate_qr_token": b.gate_qr_token,
            "gate_payload": (qr_payload.encode(qr_payload.KIND_GATE, b.gate_qr_token)
                             if b.gate_qr_token else None),
            "listed_publicly": b.listed_publicly,
            "listing_headline": b.listing_headline,
            "listing_description": b.listing_description,
            "starting_rent": float(b.starting_rent) if b.starting_rent else None,
            "gender_preference": b.gender_preference,
            "amenities": b.amenities or [],
            "contact_phone_public": b.contact_phone_public,
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
                # A count, never the bytes. This list is read on every dashboard
                # load and six photos per branch would be 30 KB of base64 each.
                "photos": db.scalar(select(func.count(BranchPhoto.id)).where(
                    BranchPhoto.branch_id == b.id)) or 0,
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


@router.put("/branches/{branch_id}/location", summary="Set the gate location and geofence")
def set_branch_location(branch_id: uuid.UUID, body: BranchLocationUpdate,
                        db: DbSession, scope: Tenant,
                        _: None = Depends(require("branches.edit"))) -> dict:
    """
    One-time setup: where the gate is, how close a resident must be, and
    whether self check-in is on at all.

    Guarded by `branches.edit` rather than a new permission. A separate one
    would have to be granted to every existing role before the feature worked,
    and the failure mode - an owner who cannot find the setting - looks
    identical to a bug. Anyone trusted to move a branch's address is trusted to
    position its gate.
    """
    branch = _svc(db, scope).set_branch_location(
        branch_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok({
        "id": str(branch.id), "name": branch.name,
        "latitude": branch.latitude, "longitude": branch.longitude,
        "geofence_radius_m": branch.geofence_radius_m,
        "self_checkin_enabled": branch.self_checkin_enabled,
        "gate_qr_token": branch.gate_qr_token,
        "gate_payload": qr_payload.encode(qr_payload.KIND_GATE, branch.gate_qr_token)
                        if branch.gate_qr_token else None,
    }, message="Gate location saved.")


@router.put("/branches/{branch_id}/listing", summary="Publish or unpublish this branch")
def set_branch_listing(branch_id: uuid.UUID, body: BranchListingUpdate,
                       db: DbSession, scope: Tenant,
                       _: None = Depends(require("branches.edit"))) -> dict:
    """
    Listing is off until someone here turns it on.

    Guarded by `branches.edit` rather than a new permission, for the same reason
    the gate location is: a separate permission would have to be granted to
    every existing role before the feature worked at all, and an owner who
    cannot find the setting cannot tell that from a bug.
    """
    branch = _svc(db, scope).set_branch_listing(branch_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok({
        "id": str(branch.id), "name": branch.name,
        "listed_publicly": branch.listed_publicly,
        "listing_headline": branch.listing_headline,
        "listing_description": branch.listing_description,
        "starting_rent": float(branch.starting_rent) if branch.starting_rent else None,
        "gender_preference": branch.gender_preference,
        "amenities": branch.amenities or [],
        "contact_phone_public": branch.contact_phone_public,
    }, message=("This branch is now visible in public search."
                if branch.listed_publicly else
                "This branch is no longer listed publicly."))


# --------------------------------------------------------- listing photos
def _photo(p, *, with_image: bool = True) -> dict:
    """
    One photo, ready for JSON.

    `with_image` exists for the same reason it does on resident documents: a
    list of six photos is 30 KB of base64, which is fine on a listing screen and
    wasteful on a branch list that only needs to know whether photos exist.
    """
    import base64
    payload = {
        "id": str(p.id), "caption": p.caption, "mime_type": p.mime_type,
        "size_bytes": p.size_bytes, "width": p.width, "height": p.height,
        "source": p.source, "position": p.position,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
    if with_image:
        payload["data_url"] = (f"data:{p.mime_type};base64,"
                               f"{base64.b64encode(p.content).decode()}")
    return payload


@router.get("/branches/{branch_id}/photos", summary="Photos on this branch's listing")
def list_branch_photos(branch_id: uuid.UUID, db: DbSession, scope: Tenant,
                       _: None = Depends(require("branches.view"))) -> dict:
    from app.models.branch import PHOTO_MAX_BYTES, PHOTOS_PER_BRANCH
    rows = BranchPhotoService(db, scope).list(branch_id)
    return ok({"items": [_photo(p) for p in rows],
               "max_bytes": PHOTO_MAX_BYTES, "max_photos": PHOTOS_PER_BRANCH})


@router.post("/branches/{branch_id}/photos", status_code=status.HTTP_201_CREATED,
             summary="Add a listing photo (max 6, each under 5 KB)")
def add_branch_photo(branch_id: uuid.UUID, body: BranchPhotoUpload, db: DbSession,
                     scope: Tenant,
                     _: None = Depends(require("branches.edit"))) -> dict:
    row = BranchPhotoService(db, scope).add(
        branch_id, image=body.image, caption=body.caption, source=body.source,
        width=body.width, height=body.height)
    db.commit()
    return ok(_photo(row), message="Photo added.")


@router.put("/branches/{branch_id}/photos/order", summary="Choose which photo leads")
def reorder_branch_photos(branch_id: uuid.UUID, body: BranchPhotoReorder, db: DbSession,
                          scope: Tenant,
                          _: None = Depends(require("branches.edit"))) -> dict:
    rows = BranchPhotoService(db, scope).reorder(branch_id, body.photo_ids)
    db.commit()
    return ok({"items": [_photo(p, with_image=False) for p in rows]},
              message="Photo order saved.")


@router.delete("/branches/{branch_id}/photos/{photo_id}", summary="Delete a listing photo")
def delete_branch_photo(branch_id: uuid.UUID, photo_id: uuid.UUID, db: DbSession,
                        scope: Tenant,
                        _: None = Depends(require("branches.edit"))) -> dict:
    BranchPhotoService(db, scope).delete(branch_id, photo_id)
    db.commit()
    return ok(None, message="Photo deleted.")


@router.get("/enquiries", summary="Enquiries from people looking for a bed")
def list_enquiries(db: DbSession, scope: Tenant,
                   _: None = Depends(require("customers.view")),
                   status_filter: str | None = Query(default=None, alias="status"),
                   page: int = Query(default=1, ge=1),
                   page_size: int = Query(default=50, ge=1, le=200)) -> dict:
    """
    Scoped to the caller's organisation and branches like everything else.

    Guarded by `customers.view`: whoever is trusted to see residents is trusted
    to see the people asking to become one, and inventing a permission nobody
    has yet would leave every existing role unable to read their own leads.
    """
    stmt = select(PgEnquiry).where(
        PgEnquiry.organization_id == scope.organization_id)
    if not scope.all_branches:
        stmt = stmt.where(PgEnquiry.branch_id.in_(scope.branch_ids))
    if status_filter and status_filter != "all":
        stmt = stmt.where(PgEnquiry.status == status_filter)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(PgEnquiry.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)).all()

    branches = {b.id: b.name for b in db.scalars(select(Branch).where(
        Branch.organization_id == scope.organization_id)).all()}

    return paginated([{
        "id": str(e.id), "branch_id": str(e.branch_id),
        "branch_name": branches.get(e.branch_id),
        "full_name": e.full_name, "email": e.email, "phone": e.phone,
        "message": e.message,
        "move_in_date": e.move_in_date.isoformat() if e.move_in_date else None,
        "status": e.status, "staff_notes": e.staff_notes,
        "email_verified": e.email_verified,
        "created_at": e.created_at.isoformat(),
    } for e in rows], page, page_size, total)


@router.patch("/enquiries/{enquiry_id}", summary="Update an enquiry")
def update_enquiry(enquiry_id: uuid.UUID, body: EnquiryUpdate, db: DbSession,
                   scope: Tenant,
                   _: None = Depends(require("customers.edit"))) -> dict:
    row = db.scalars(select(PgEnquiry).where(
        PgEnquiry.id == enquiry_id,
        PgEnquiry.organization_id == scope.organization_id)).first()
    if row is None:
        # Not found rather than forbidden, so this cannot confirm that another
        # tenant's enquiry exists.
        raise NotFoundError("Enquiry not found.")

    if body.status is not None:
        if body.status not in EnquiryStatus.ALL:
            raise ConflictError(f"{body.status} is not a valid status.")
        row.status = body.status
        row.handled_by_id = scope.user.id
        row.handled_at = datetime.now(timezone.utc)
    if body.staff_notes is not None:
        row.staff_notes = body.staff_notes

    db.commit()
    return ok({"id": str(row.id), "status": row.status}, message="Enquiry updated.")


@router.post("/branches/{branch_id}/gate-token", summary="Issue a new gate QR")
def rotate_gate_token(branch_id: uuid.UUID, db: DbSession, scope: Tenant,
                      _: None = Depends(require("branches.edit"))) -> dict:
    """
    Replaces the printed gate code. The previous one stops working immediately.

    Worth doing when a photograph of the poster is believed to be circulating,
    and after any staff departure where that seems plausible.
    """
    branch = _svc(db, scope).rotate_gate_token(branch_id)
    db.commit()
    return ok({
        "id": str(branch.id), "name": branch.name,
        "gate_qr_token": branch.gate_qr_token,
        "gate_payload": qr_payload.encode(qr_payload.KIND_GATE, branch.gate_qr_token),
    }, message="A new gate QR has been issued. Print and replace the old one.")


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
