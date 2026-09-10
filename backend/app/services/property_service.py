"""
Property hierarchy CRUD: branches, buildings, floors, rooms, beds.

Every create passes two gates before the INSERT: the subscription limit, and
the branch the caller is allowed to touch. Both live here rather than in the
router, so a new endpoint cannot forget one.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import CurrentScope
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models import Bed, Branch, Building, Customer, Floor, Room
from app.models.enums import (
    AuditAction, BedStatus, BranchStatus, BuildingStatus, FloorStatus, RoomStatus,
)
from app.services.audit import AuditService
from app.services.resident_service import generate_qr_token
from app.services.subscription_limits import SubscriptionLimitService
from app.utils.geo import is_valid_coordinate


class PropertyService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope
        self.audit = AuditService(db)
        self.limits = SubscriptionLimitService(db)

    # ------------------------------------------------------------- helpers
    @property
    def org_id(self) -> uuid.UUID:
        return self.scope.organization_id

    def _assert_branch(self, branch_id: uuid.UUID) -> Branch:
        """
        Resolve a branch the caller may actually touch.

        Order matters: the tenant filter runs first, so a branch belonging to
        another organisation comes back as "not found" rather than "forbidden".
        Saying forbidden would confirm it exists.
        """
        branch = self.db.scalars(
            select(Branch).where(Branch.id == branch_id, Branch.organization_id == self.org_id)
        ).first()
        if branch is None:
            raise NotFoundError("Branch not found.")
        if not self.scope.owns_branch(branch_id):
            raise PermissionDeniedError(
                "Branch access denied. You are not assigned to this branch."
            )
        return branch

    def _scoped(self, model):
        """
        Both scoping filters, always.

        Branch is the special case: it has no `branch_id` column because it *is*
        the branch, so it must be filtered on its own primary key. Relying on
        `hasattr(model, "branch_id")` alone silently applied no branch filter at
        all to the branch list, which let a manager see branches they were never
        assigned to.
        """
        stmt = select(model).where(model.organization_id == self.org_id)
        if model is Branch:
            stmt = stmt.where(Branch.id.in_(self.scope.branch_ids))
        elif hasattr(model, "branch_id"):
            stmt = stmt.where(model.branch_id.in_(self.scope.branch_ids))
        return stmt

    def _get(self, model, entity_id: uuid.UUID, label: str):
        obj = self.db.scalars(self._scoped(model).where(model.id == entity_id)).first()
        if obj is None:
            raise NotFoundError(f"{label} not found.")
        return obj

    def _log(self, module: str, action: str, description: str, entity_type: str,
             entity_id, branch_id=None) -> None:
        self.audit.record(
            scope=self.scope, module=module, action=action, description=description,
            entity_type=entity_type, entity_id=entity_id, branch_id=branch_id,
        )

    # ------------------------------------------------------------ branches
    def list_branches(self, *, search=None, status=None, page=1, page_size=50):
        stmt = self._scoped(Branch)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(Branch.name.ilike(like), Branch.code.ilike(like),
                                  Branch.city.ilike(like)))
        if status and status != "all":
            stmt = stmt.where(Branch.status == status)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.db.scalars(
            stmt.order_by(Branch.name).offset((page - 1) * page_size).limit(page_size)
        ).all())
        return rows, total

    def get_branch(self, branch_id: uuid.UUID) -> Branch:
        return self._assert_branch(branch_id)

    def create_branch(self, data: dict) -> Branch:
        self.limits.can_create_branch(self.org_id)
        code = data["code"].strip().upper()
        if self.db.scalars(select(Branch).where(
            Branch.organization_id == self.org_id, Branch.code == code
        )).first():
            raise ConflictError(f"A branch with the code {code} already exists.")

        branch = Branch(
            organization_id=self.org_id, name=data["name"].strip(), code=code,
            address=data.get("address"), city=data.get("city"), state=data.get("state"),
            pincode=data.get("pincode"), contact_number=data.get("contact_number"),
            opened_on=data.get("opened_on") or date.today(),
            status=data.get("status") or BranchStatus.ACTIVE,
        )
        self.db.add(branch)
        self.db.flush()

        # Without this the creator immediately loses sight of what they made,
        # because their scope was computed before the branch existed.
        if not self.scope.all_branches:
            self.scope.user.branches.append(branch)
            self.scope.branch_ids.append(branch.id)

        self._log("Branches", AuditAction.CREATE, f"Created branch {branch.name} ({code})",
                  "branch", branch.id, branch.id)
        return branch

    def update_branch(self, branch_id: uuid.UUID, data: dict) -> Branch:
        branch = self._assert_branch(branch_id)
        for field in ("name", "address", "city", "state", "pincode",
                      "contact_number", "status"):
            if data.get(field) is not None:
                setattr(branch, field, data[field])
        self._log("Branches", AuditAction.UPDATE, f"Updated branch {branch.name}",
                  "branch", branch.id, branch.id)
        return branch

    # ------------------------------------------------- gate and self check-in
    def set_branch_location(self, branch_id: uuid.UUID, data: dict) -> Branch:
        """
        Position the gate and set the radius residents must be inside.

        Validated here rather than only in the request schema because the same
        rules have to hold for the seed script and for any future import, and a
        geofence that silently accepts nonsense is worse than one that refuses:
        a radius of 5 metres locks every resident out, and nobody would connect
        the support calls back to a number typed once during setup.
        """
        branch = self._assert_branch(branch_id)

        if "latitude" in data or "longitude" in data:
            lat, lon = data.get("latitude"), data.get("longitude")
            if (lat is None) != (lon is None):
                raise ConflictError(
                    "A location needs both a latitude and a longitude.")
            if lat is not None and not is_valid_coordinate(lat, lon):
                raise ConflictError("That is not a valid location on the map.")
            branch.latitude, branch.longitude = lat, lon

        if data.get("geofence_radius_m") is not None:
            radius = int(data["geofence_radius_m"])
            if not 10 <= radius <= 5000:
                raise ConflictError("The radius must be between 10 and 5000 metres.")
            branch.geofence_radius_m = radius

        if data.get("self_checkin_enabled") is not None:
            enabling = bool(data["self_checkin_enabled"])
            if enabling and not branch.has_geofence():
                # Refused rather than quietly stored, because the resident-facing
                # failure - a button that never becomes available with no
                # explanation on the owner's side - is invisible from here.
                raise ConflictError(
                    "Set the gate location before switching self check-in on.")
            branch.self_checkin_enabled = enabling
            if enabling and not branch.gate_qr_token:
                # No gate code means nothing for a resident to scan, so issue one
                # rather than making the owner find a second button.
                branch.gate_qr_token = generate_qr_token()

        self._log("Branches", AuditAction.UPDATE,
                  f"Updated gate location for {branch.name}", "branch",
                  branch.id, branch.id)
        return branch

    def set_branch_listing(self, branch_id: uuid.UUID, data: dict) -> Branch:
        """
        Publish or unpublish a branch, and edit what is published.

        Refuses to switch listing on without a city or an address. A listing
        nobody can find is worse than no listing: the owner believes they are
        visible, sees no enquiries, and concludes the feature is broken.
        """
        branch = self._assert_branch(branch_id)

        for field in ("listing_headline", "listing_description",
                      "gender_preference", "contact_phone_public", "amenities"):
            if field in data and data[field] is not None:
                setattr(branch, field, data[field])
        if data.get("starting_rent") is not None:
            branch.starting_rent = data["starting_rent"]

        if data.get("listed_publicly") is not None:
            listing = bool(data["listed_publicly"])
            if listing and not (branch.city or branch.address):
                raise ConflictError(
                    "Add a city or address to the branch before listing it, "
                    "or nobody searching will find it.")
            branch.listed_publicly = listing

        self._log("Branches", AuditAction.UPDATE,
                  (f"{'Listed' if branch.listed_publicly else 'Unlisted'} "
                   f"{branch.name} publicly"),
                  "branch", branch.id, branch.id)
        return branch

    def rotate_gate_token(self, branch_id: uuid.UUID) -> Branch:
        """
        Issue a fresh gate code and kill the old one.

        The gate QR is printed and stuck on a wall, so it leaks by design - a
        photograph of it is enough to attempt a check-in from elsewhere, if the
        geofence is also defeated. Rotation is the response to a code believed
        to be circulating, and the old token stops working the moment this
        returns because the column is the only lookup key.
        """
        branch = self._assert_branch(branch_id)
        branch.gate_qr_token = generate_qr_token()
        self._log("Branches", AuditAction.UPDATE,
                  f"Reissued the gate QR for {branch.name}", "branch",
                  branch.id, branch.id)
        return branch

    def deactivate_branch(self, branch_id: uuid.UUID) -> Branch:
        branch = self._assert_branch(branch_id)
        occupied = self.db.scalar(
            select(func.count(Bed.id)).where(Bed.branch_id == branch_id,
                                             Bed.status == BedStatus.OCCUPIED)
        ) or 0
        if occupied:
            raise ConflictError(
                f"This branch still has {occupied} occupied bed"
                f"{'s' if occupied != 1 else ''}. Check those residents out first."
            )
        branch.status = BranchStatus.INACTIVE
        self._log("Branches", AuditAction.UPDATE, f"Deactivated branch {branch.name}",
                  "branch", branch.id, branch.id)
        return branch

    # ----------------------------------------------------------- buildings
    def list_buildings(self, *, branch_id=None, search=None, status=None):
        stmt = self._scoped(Building)
        if branch_id:
            self._assert_branch(branch_id)
            stmt = stmt.where(Building.branch_id == branch_id)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(Building.name.ilike(like), Building.code.ilike(like)))
        if status and status != "all":
            stmt = stmt.where(Building.status == status)
        return list(self.db.scalars(stmt.order_by(Building.name)).all())

    def create_building(self, data: dict) -> Building:
        branch = self._assert_branch(data["branch_id"])
        self.limits.can_create_building(self.org_id)
        code = (data.get("code") or data["name"][:3]).strip().upper()
        if self.db.scalars(select(Building).where(
            Building.branch_id == branch.id, Building.code == code
        )).first():
            raise ConflictError(f"Building code {code} already exists in this branch.")

        building = Building(
            organization_id=self.org_id, branch_id=branch.id,
            name=data["name"].strip(), code=code, description=data.get("description"),
            number_of_floors=data.get("number_of_floors") or 1,
            status=data.get("status") or BuildingStatus.ACTIVE,
        )
        self.db.add(building)
        self.db.flush()
        self._log("Property", AuditAction.CREATE,
                  f"Created building {building.name} in {branch.name}",
                  "building", building.id, branch.id)
        return building

    def update_building(self, building_id: uuid.UUID, data: dict) -> Building:
        building = self._get(Building, building_id, "Building")
        for field in ("name", "description", "number_of_floors", "status"):
            if data.get(field) is not None:
                setattr(building, field, data[field])
        self._log("Property", AuditAction.UPDATE, f"Updated building {building.name}",
                  "building", building.id, building.branch_id)
        return building

    def delete_building(self, building_id: uuid.UUID) -> None:
        building = self._get(Building, building_id, "Building")
        rooms = self.db.scalar(
            select(func.count(Room.id)).where(Room.building_id == building_id)) or 0
        if rooms:
            raise ConflictError(
                f"This building still contains {rooms} room{'s' if rooms != 1 else ''}. "
                "Remove them first."
            )
        self._log("Property", AuditAction.DELETE, f"Deleted building {building.name}",
                  "building", building.id, building.branch_id)
        self.db.delete(building)

    # -------------------------------------------------------------- floors
    def list_floors(self, *, branch_id=None, building_id=None, status=None):
        stmt = self._scoped(Floor)
        if branch_id:
            self._assert_branch(branch_id)
            stmt = stmt.where(Floor.branch_id == branch_id)
        if building_id:
            stmt = stmt.where(Floor.building_id == building_id)
        if status and status != "all":
            stmt = stmt.where(Floor.status == status)
        return list(self.db.scalars(stmt.order_by(Floor.floor_number)).all())

    def create_floor(self, data: dict) -> Floor:
        building = self._get(Building, data["building_id"], "Building")
        self._assert_branch(building.branch_id)
        self.limits.can_create_floor(self.org_id)

        number = int(data["floor_number"])
        if self.db.scalars(select(Floor).where(
            Floor.building_id == building.id, Floor.floor_number == number
        )).first():
            raise ConflictError(f"Floor {number} already exists in {building.name}.")

        floor = Floor(
            organization_id=self.org_id, branch_id=building.branch_id,
            building_id=building.id, floor_number=number,
            name=data.get("name") or _floor_name(number),
            status=data.get("status") or FloorStatus.ACTIVE,
        )
        self.db.add(floor)
        self.db.flush()
        self._log("Property", AuditAction.CREATE,
                  f"Created {floor.name} in {building.name}", "floor", floor.id,
                  floor.branch_id)
        return floor

    def update_floor(self, floor_id: uuid.UUID, data: dict) -> Floor:
        floor = self._get(Floor, floor_id, "Floor")
        for field in ("name", "status"):
            if data.get(field) is not None:
                setattr(floor, field, data[field])
        self._log("Property", AuditAction.UPDATE, f"Updated {floor.name}",
                  "floor", floor.id, floor.branch_id)
        return floor

    def delete_floor(self, floor_id: uuid.UUID) -> None:
        floor = self._get(Floor, floor_id, "Floor")
        rooms = self.db.scalar(
            select(func.count(Room.id)).where(Room.floor_id == floor_id)) or 0
        if rooms:
            raise ConflictError(
                f"This floor still contains {rooms} room{'s' if rooms != 1 else ''}."
            )
        self._log("Property", AuditAction.DELETE, f"Deleted {floor.name}",
                  "floor", floor.id, floor.branch_id)
        self.db.delete(floor)

    # --------------------------------------------------------------- rooms
    def list_rooms(self, *, branch_id=None, floor_id=None, building_id=None,
                   search=None, status=None, room_type=None, page=1, page_size=50):
        stmt = self._scoped(Room).options(selectinload(Room.beds))
        if branch_id:
            self._assert_branch(branch_id)
            stmt = stmt.where(Room.branch_id == branch_id)
        if building_id:
            stmt = stmt.where(Room.building_id == building_id)
        if floor_id:
            stmt = stmt.where(Room.floor_id == floor_id)
        if room_type and room_type != "all":
            stmt = stmt.where(Room.room_type == room_type)
        if status and status != "all":
            stmt = stmt.where(Room.status == status)
        if search:
            stmt = stmt.where(Room.room_number.ilike(f"%{search.strip()}%"))

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.db.scalars(
            stmt.order_by(Room.room_number).offset((page - 1) * page_size).limit(page_size)
        ).all())
        return rows, total

    def get_room(self, room_id: uuid.UUID) -> Room:
        return self._get(Room, room_id, "Room")

    def create_room(self, data: dict, *, generate_beds: bool = True) -> Room:
        floor = self._get(Floor, data["floor_id"], "Floor")
        self._assert_branch(floor.branch_id)

        capacity = int(data.get("capacity") or 1)
        self.limits.can_create_room(self.org_id)
        if generate_beds:
            # Check the beds up front: creating a room whose beds then fail the
            # limit would leave a room nobody can sell.
            self.limits.can_create_bed(self.org_id, capacity)

        number = str(data["room_number"]).strip()
        if self.db.scalars(select(Room).where(
            Room.floor_id == floor.id, Room.room_number == number
        )).first():
            raise ConflictError(
                f"Room {number} already exists on this floor."
            )

        rent = data.get("rent_amount") or 0
        room = Room(
            organization_id=self.org_id, branch_id=floor.branch_id,
            building_id=floor.building_id, floor_id=floor.id,
            room_number=number, room_type=data.get("room_type") or "Single",
            capacity=capacity, gender_policy=data.get("gender_policy") or "ANY",
            rent_amount=rent,
            deposit_amount=data.get("deposit_amount") or (float(rent) * 2),
            has_ac=bool(data.get("has_ac")),
            has_attached_bathroom=bool(data.get("has_attached_bathroom", True)),
            description=data.get("description"),
            status=data.get("status") or RoomStatus.ACTIVE,
        )
        self.db.add(room)
        self.db.flush()

        if generate_beds:
            branch = self.db.get(Branch, floor.branch_id)
            for i in range(capacity):
                letter = chr(ord("A") + i)
                self.db.add(Bed(
                    organization_id=self.org_id, branch_id=room.branch_id, room_id=room.id,
                    bed_number=letter,
                    bed_code=f"{branch.code}-{floor.floor_number}-{number}-{letter}",
                    status=BedStatus.AVAILABLE, rent_amount=rent,
                ))
            self.db.flush()

        self._log("Rooms", AuditAction.CREATE,
                  f"Created room {number} ({room.room_type})"
                  + (f" with {capacity} beds" if generate_beds else ""),
                  "room", room.id, room.branch_id)
        return room

    def update_room(self, room_id: uuid.UUID, data: dict) -> Room:
        room = self._get(Room, room_id, "Room")
        for field in ("room_number", "room_type", "gender_policy", "rent_amount",
                      "deposit_amount", "has_ac", "has_attached_bathroom",
                      "description", "status"):
            if data.get(field) is not None:
                setattr(room, field, data[field])
        self._log("Rooms", AuditAction.UPDATE, f"Updated room {room.room_number}",
                  "room", room.id, room.branch_id)
        return room

    def delete_room(self, room_id: uuid.UUID) -> None:
        room = self._get(Room, room_id, "Room")
        occupied = [b for b in room.beds if b.status == BedStatus.OCCUPIED]
        if occupied:
            raise ConflictError(
                f"Room {room.room_number} has {len(occupied)} occupied bed"
                f"{'s' if len(occupied) != 1 else ''}. Check those residents out first."
            )
        self._log("Rooms", AuditAction.DELETE, f"Deleted room {room.room_number}",
                  "room", room.id, room.branch_id)
        self.db.delete(room)

    # ---------------------------------------------------------------- beds
    def list_beds(self, *, branch_id=None, room_id=None, status=None,
                  search=None, page=1, page_size=100):
        stmt = self._scoped(Bed)
        if branch_id:
            self._assert_branch(branch_id)
            stmt = stmt.where(Bed.branch_id == branch_id)
        if room_id:
            stmt = stmt.where(Bed.room_id == room_id)
        if status and status != "all":
            stmt = stmt.where(Bed.status == status)
        if search:
            stmt = stmt.where(Bed.bed_code.ilike(f"%{search.strip()}%"))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.db.scalars(
            stmt.order_by(Bed.bed_code).offset((page - 1) * page_size).limit(page_size)
        ).all())
        return rows, total

    def create_bed(self, data: dict) -> Bed:
        room = self._get(Room, data["room_id"], "Room")
        self.limits.can_create_bed(self.org_id)

        number = str(data["bed_number"]).strip().upper()
        if self.db.scalars(select(Bed).where(
            Bed.room_id == room.id, Bed.bed_number == number
        )).first():
            raise ConflictError(
                f"Bed {number} already exists in room {room.room_number}."
            )

        branch = self.db.get(Branch, room.branch_id)
        floor = self.db.get(Floor, room.floor_id)
        bed = Bed(
            organization_id=self.org_id, branch_id=room.branch_id, room_id=room.id,
            bed_number=number,
            bed_code=data.get("bed_code")
            or f"{branch.code}-{floor.floor_number}-{room.room_number}-{number}",
            status=data.get("status") or BedStatus.AVAILABLE,
            rent_amount=data.get("rent_amount") or room.rent_amount,
            notes=data.get("notes"),
        )
        self.db.add(bed)
        self.db.flush()
        self._log("Beds", AuditAction.CREATE,
                  f"Created bed {number} in room {room.room_number}",
                  "bed", bed.id, bed.branch_id)
        return bed

    def update_bed(self, bed_id: uuid.UUID, data: dict) -> Bed:
        bed = self._get(Bed, bed_id, "Bed")
        if "status" in data and data["status"] is not None:
            self._set_bed_status(bed, data["status"])
        for field in ("bed_number", "bed_code", "rent_amount", "notes"):
            if data.get(field) is not None:
                setattr(bed, field, data[field])
        self._log("Beds", AuditAction.UPDATE, f"Updated bed {bed.bed_code or bed.bed_number}",
                  "bed", bed.id, bed.branch_id)
        return bed

    def _set_bed_status(self, bed: Bed, status: str) -> None:
        """
        Occupancy is not a status you may simply type.

        Assigning a resident is a Phase 5 workflow with its own transaction; the
        database CHECK would reject an OCCUPIED bed with no occupant anyway, so
        this refuses early with an explanation rather than a constraint error.
        """
        if status == BedStatus.OCCUPIED and bed.current_customer_id is None:
            raise ConflictError(
                "A bed becomes occupied by assigning a resident to it, not by "
                "setting its status directly."
            )
        if bed.status == BedStatus.OCCUPIED and status != BedStatus.OCCUPIED:
            raise ConflictError(
                "This bed has a resident. Check them out or transfer them first."
            )
        bed.status = status

    def delete_bed(self, bed_id: uuid.UUID) -> None:
        bed = self._get(Bed, bed_id, "Bed")
        if bed.status == BedStatus.OCCUPIED:
            raise ConflictError("This bed has a resident and cannot be removed.")
        self._log("Beds", AuditAction.DELETE, f"Deleted bed {bed.bed_code or bed.bed_number}",
                  "bed", bed.id, bed.branch_id)
        self.db.delete(bed)

    # ----------------------------------------------------------- blueprint
    def blueprint(self, branch_id: uuid.UUID | None = None) -> list[dict]:
        """
        The whole hierarchy, nested, for the floor-plan screen.

        Loaded in four flat queries and assembled in memory rather than by
        walking relationships, which would issue a query per room.
        """
        branch_ids = [branch_id] if branch_id else list(self.scope.branch_ids)
        if branch_id:
            self._assert_branch(branch_id)
        if not branch_ids:
            return []

        branches = list(self.db.scalars(
            select(Branch).where(Branch.organization_id == self.org_id,
                                 Branch.id.in_(branch_ids)).order_by(Branch.name)
        ).all())
        buildings = list(self.db.scalars(
            select(Building).where(Building.branch_id.in_(branch_ids)).order_by(Building.name)
        ).all())
        floors = list(self.db.scalars(
            select(Floor).where(Floor.branch_id.in_(branch_ids)).order_by(Floor.floor_number)
        ).all())
        rooms = list(self.db.scalars(
            select(Room).options(selectinload(Room.beds))
            .where(Room.branch_id.in_(branch_ids)).order_by(Room.room_number)
        ).all())

        rooms_by_floor: dict[uuid.UUID, list[Room]] = {}
        for room in rooms:
            rooms_by_floor.setdefault(room.floor_id, []).append(room)
        floors_by_building: dict[uuid.UUID, list[Floor]] = {}
        for floor in floors:
            floors_by_building.setdefault(floor.building_id, []).append(floor)
        buildings_by_branch: dict[uuid.UUID, list[Building]] = {}
        for building in buildings:
            buildings_by_branch.setdefault(building.branch_id, []).append(building)

        def room_node(room: Room) -> dict:
            return {
                "id": str(room.id), "room_number": room.room_number,
                "room_type": room.room_type, "capacity": room.capacity,
                "rent_amount": float(room.rent_amount), "status": room.status,
                "has_ac": room.has_ac, "gender_policy": room.gender_policy,
                "occupancy": room.occupancy,
                "beds": [
                    {"id": str(b.id), "bed_number": b.bed_number, "bed_code": b.bed_code,
                     "status": b.status, "rent_amount": float(b.rent_amount),
                     "current_customer_id": str(b.current_customer_id)
                     if b.current_customer_id else None}
                    for b in sorted(room.beds, key=lambda x: x.bed_number)
                ],
            }

        out = []
        for branch in branches:
            branch_rooms = [r for r in rooms if r.branch_id == branch.id]
            branch_beds = [b for r in branch_rooms for b in r.beds]
            out.append({
                "id": str(branch.id), "name": branch.name, "code": branch.code,
                "status": branch.status,
                "occupancy": _occupancy(branch_beds),
                "buildings": [
                    {
                        "id": str(bld.id), "name": bld.name, "code": bld.code,
                        "status": bld.status,
                        "floors": [
                            {
                                "id": str(fl.id), "name": fl.name,
                                "floor_number": fl.floor_number, "status": fl.status,
                                "rooms": [room_node(r) for r in rooms_by_floor.get(fl.id, [])],
                            }
                            for fl in floors_by_building.get(bld.id, [])
                        ],
                    }
                    for bld in buildings_by_branch.get(branch.id, [])
                ],
            })
        return out


def _occupancy(beds: list[Bed]) -> dict:
    total = len(beds)
    counts = {s.value: sum(1 for b in beds if b.status == s.value) for s in BedStatus}
    occupied = counts.get(BedStatus.OCCUPIED.value, 0)
    return {
        "total": total, **{k.lower(): v for k, v in counts.items()},
        "rate": round(occupied / total * 100, 1) if total else 0.0,
    }


def _floor_name(number: int) -> str:
    if number == 0:
        return "Ground Floor"
    if number < 0:
        return f"Basement {abs(number)}"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(number if number < 20 else number % 10, "th")
    return f"{number}{suffix} Floor"
