"""
Residents and the bed lifecycle.

The bed transitions are the heart of the product and the place where a race
condition costs real money, so `assign_bed`, `transfer` and `checkout` all take
a row lock on the bed before reading its state:

    SELECT ... FROM beds WHERE id = :id FOR UPDATE

Without it, two staff members assigning the last free bed at the same moment
both read AVAILABLE and both write their resident. The database CHECK
(`ck_beds_occupancy_consistent`) would catch a bed that ends up occupied with no
occupant, but not two residents pointing at one bed - only the lock prevents
that. Everything inside these methods runs in one transaction; the caller
commits.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import CurrentScope
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.models import (
    Bed, Branch, Building, Customer, Floor, ResidentKyc, Room,
)
from app.models.enums import (
    AuditAction, BedStatus, CustomerStatus, InvoiceItemKind, KycStatus,
    NotificationType,
)
from app.services.audit import AuditService
from app.services.notification_service import NotificationService
from app.services.subscription_limits import SubscriptionLimitService

#: Statuses that occupy a bed and count against the plan.
LIVE_STATUSES = (
    CustomerStatus.RESERVED, CustomerStatus.BOOKED,
    CustomerStatus.ACTIVE, CustomerStatus.NOTICE,
)


def generate_qr_token() -> str:
    """Opaque gate identity. Never derived from the resident id."""
    return secrets.token_urlsafe(24)


class ResidentService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope
        self.audit = AuditService(db)
        self.limits = SubscriptionLimitService(db)
        self.notify = NotificationService(db)

    @property
    def org_id(self) -> uuid.UUID:
        return self.scope.organization_id

    # ------------------------------------------------------------- helpers
    def _scoped(self):
        return (
            select(Customer)
            .where(Customer.organization_id == self.org_id)
            .where(or_(Customer.branch_id.is_(None),
                       Customer.branch_id.in_(self.scope.branch_ids)))
        )

    def get(self, resident_id: uuid.UUID) -> Customer:
        row = self.db.scalars(self._scoped().where(Customer.id == resident_id)).first()
        if row is None:
            # 404 rather than 403: confirming the row exists elsewhere is itself
            # a leak across tenants.
            raise NotFoundError("Resident not found.")
        return row

    def _assert_branch(self, branch_id: uuid.UUID) -> Branch:
        branch = self.db.scalars(
            select(Branch).where(Branch.id == branch_id,
                                 Branch.organization_id == self.org_id)).first()
        if branch is None:
            raise NotFoundError("Branch not found.")
        if not self.scope.owns_branch(branch_id):
            raise PermissionDeniedError(
                "Branch access denied. You are not assigned to this branch.")
        return branch

    def _lock_bed(self, bed_id: uuid.UUID) -> Bed:
        """Load a bed for update. The lock is the whole point of this method."""
        bed = self.db.scalars(
            select(Bed)
            .where(Bed.id == bed_id, Bed.organization_id == self.org_id)
            .with_for_update()
        ).first()
        if bed is None:
            raise NotFoundError("Bed not found.")
        self._assert_branch(bed.branch_id)
        return bed

    def _place(self, resident: Customer, bed: Bed | None) -> None:
        """Write the whole placement chain, or clear it."""
        if bed is None:
            resident.bed_id = resident.room_id = None
            resident.building_id = resident.floor_id = None
            return
        room = self.db.get(Room, bed.room_id)
        resident.bed_id = bed.id
        resident.room_id = room.id
        resident.floor_id = room.floor_id
        resident.building_id = room.building_id
        resident.branch_id = bed.branch_id

    # ------------------------------------------------------------ querying
    def list(self, *, search=None, status=None, branch_id=None, room_id=None,
             page=1, page_size=25):
        stmt = self._scoped()
        if branch_id:
            self._assert_branch(branch_id)
            stmt = stmt.where(Customer.branch_id == branch_id)
        if room_id:
            stmt = stmt.where(Customer.room_id == room_id)
        if status and status != "all":
            if status == "live":
                stmt = stmt.where(Customer.status.in_(LIVE_STATUSES))
            else:
                stmt = stmt.where(Customer.status == status)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(Customer.full_name.ilike(like),
                                  Customer.email.ilike(like),
                                  Customer.phone.ilike(like)))

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.db.scalars(
            stmt.order_by(Customer.full_name)
            .offset((page - 1) * page_size).limit(page_size)).all())
        return rows, total

    # ------------------------------------------------------------ creating
    def create(self, data: dict) -> tuple[Customer, str | None]:
        branch = self._assert_branch(data["branch_id"])
        self.limits.can_create_customer(self.org_id)

        email = (data.get("email") or "").strip().lower() or None
        if email and self.db.scalars(
            select(Customer).where(Customer.organization_id == self.org_id,
                                   Customer.email == email)).first():
            raise ConflictError("A resident with that email already exists.")

        first = (data.get("first_name") or "").strip()
        last = (data.get("last_name") or "").strip()
        full = (data.get("full_name") or f"{first} {last}").strip()
        if not full:
            raise ConflictError("A resident needs a name.")

        resident = Customer(
            organization_id=self.org_id, branch_id=branch.id,
            first_name=first or None, last_name=last or None, full_name=full,
            email=email, phone=data["phone"], alternate_phone=data.get("alternate_phone"),
            date_of_birth=data.get("date_of_birth"), gender=data.get("gender"),
            address=data.get("address"), city=data.get("city"), state=data.get("state"),
            pincode=data.get("pincode"), occupation=data.get("occupation"),
            emergency_contact_name=data.get("emergency_contact_name"),
            emergency_contact_phone=data.get("emergency_contact_phone"),
            emergency_contact_relation=data.get("emergency_contact_relation"),
            joining_date=data.get("joining_date") or date.today(),
            expected_checkout_date=data.get("expected_checkout_date"),
            monthly_rent=data.get("monthly_rent") or 0,
            security_deposit=data.get("security_deposit") or 0,
            rent_due_day=data.get("rent_due_day") or 5,
            notes=data.get("notes"),
            status=data.get("status") or CustomerStatus.ACTIVE,
            is_active=True,
            qr_token=generate_qr_token(),
        )

        # Portal access is optional. A resident recorded at the enquiry desk has
        # no login until someone gives them one.
        temporary_password = None
        if data.get("create_portal_login") and email:
            from app.services.organization_service import generate_temporary_password
            temporary_password = generate_temporary_password()
            resident.password_hash = hash_password(temporary_password)
            resident.must_change_password = True

        self.db.add(resident)
        self.db.flush()

        if data.get("bed_id"):
            self.assign_bed(resident.id, data["bed_id"], log=False)

        self.audit.record(
            scope=self.scope, module="Residents", action=AuditAction.CREATE,
            description=f"Created resident {resident.full_name}",
            entity_type="resident", entity_id=resident.id, branch_id=branch.id)
        return resident, temporary_password

    def update(self, resident_id: uuid.UUID, data: dict) -> Customer:
        resident = self.get(resident_id)
        for field in ("first_name", "last_name", "full_name", "phone", "alternate_phone",
                      "date_of_birth", "gender", "address", "city", "state", "pincode",
                      "occupation", "emergency_contact_name", "emergency_contact_phone",
                      "emergency_contact_relation", "expected_checkout_date",
                      "monthly_rent", "security_deposit", "rent_due_day", "notes",
                      "joining_date"):
            if data.get(field) is not None:
                setattr(resident, field, data[field])

        if data.get("status") is not None and data["status"] != resident.status:
            # Checkout has its own method - it has to free the bed.
            if data["status"] == CustomerStatus.CHECKED_OUT:
                raise ConflictError(
                    "Use the checkout action so the bed is released properly.")
            resident.status = data["status"]

        self.audit.record(
            scope=self.scope, module="Residents", action=AuditAction.UPDATE,
            description=f"Updated resident {resident.full_name}",
            entity_type="resident", entity_id=resident.id, branch_id=resident.branch_id)
        return resident

    # -------------------------------------------------------- bed lifecycle
    def assign_bed(self, resident_id: uuid.UUID, bed_id: uuid.UUID, *,
                   log: bool = True) -> Customer:
        resident = self.get(resident_id)
        bed = self._lock_bed(bed_id)

        if resident.bed_id == bed.id:
            return resident
        if resident.status in (CustomerStatus.CHECKED_OUT, CustomerStatus.ARCHIVED):
            raise ConflictError("This resident has checked out.")
        if resident.bed_id is not None:
            raise ConflictError(
                "This resident already has a bed. Use transfer instead.")
        if bed.status == BedStatus.OCCUPIED:
            raise ConflictError("That bed is already occupied.")
        if bed.status in (BedStatus.MAINTENANCE, BedStatus.BLOCKED):
            raise ConflictError(
                f"That bed is marked {bed.status.lower()} and cannot be assigned.")

        # Belt and braces: the lock should make this impossible, but a stale
        # pointer from an earlier bug would otherwise go unnoticed.
        clash = self.db.scalars(
            select(Customer).where(Customer.bed_id == bed.id,
                                   Customer.id != resident.id)).first()
        if clash:
            raise ConflictError(
                f"That bed is already held by {clash.full_name}.")

        bed.status = BedStatus.OCCUPIED
        bed.current_customer_id = resident.id
        self._place(resident, bed)
        if resident.status == CustomerStatus.RESERVED:
            resident.status = CustomerStatus.ACTIVE
        if not resident.monthly_rent:
            resident.monthly_rent = bed.rent_amount

        if log:
            self.audit.record(
                scope=self.scope, module="Residents", action=AuditAction.ASSIGN,
                description=f"Assigned {resident.full_name} to bed {bed.bed_code or bed.bed_number}",
                entity_type="bed", entity_id=bed.id, branch_id=bed.branch_id)
        return resident

    def check_in(self, resident_id: uuid.UUID, *, bed_id: uuid.UUID,
                 joining_date: date | None = None,
                 monthly_rent: float | None = None,
                 security_deposit: float | None = None,
                 meal_plan: str | None = None,
                 billing_cycle: str | None = None,
                 rent_due_day: int | None = None,
                 raise_invoice: bool = True,
                 food_charge: float | None = None,
                 notes: str | None = None) -> tuple[Customer, object | None]:
        """
        Move someone in: place them on a bed, write the agreed terms, and
        optionally raise their first invoice - all in one transaction.

        This exists as a single method rather than as three calls the frontend
        chains together, because the intermediate states are all wrong. A
        resident on a bed with no rent set bills nothing; an invoice raised
        before the placement has no branch to belong to. If the invoice fails,
        the bed must not stay taken. Only one transaction gives that.

        `assign_bed` does the locking and the state validation; this method adds
        the commercial terms around it. The caller commits.
        """
        resident = self.get(resident_id)

        if resident.status == CustomerStatus.ACTIVE and resident.bed_id is not None:
            raise ConflictError(f"{resident.full_name} is already checked in.")

        rent = float(monthly_rent) if monthly_rent is not None else None
        if rent is not None and rent <= 0:
            raise ConflictError("Monthly rent must be greater than zero.")
        deposit = float(security_deposit) if security_deposit is not None else None
        if deposit is not None and deposit < 0:
            raise ConflictError("Security deposit cannot be negative.")
        if food_charge is not None and float(food_charge) < 0:
            raise ConflictError("Food charges cannot be negative.")
        if rent_due_day is not None and not 1 <= rent_due_day <= 28:
            raise ConflictError("The rent due day must be between 1 and 28.")

        # A reserved bed is held for this resident; assign_bed accepts it. Any
        # other unavailable state is refused there, under the row lock.
        self.assign_bed(resident_id, bed_id, log=False)

        resident.status = CustomerStatus.ACTIVE
        resident.is_active = True
        resident.joining_date = joining_date or date.today()
        if rent is not None:
            resident.monthly_rent = rent
        if deposit is not None:
            resident.security_deposit = deposit
        elif not resident.security_deposit:
            resident.security_deposit = float(resident.monthly_rent or 0) * 2
        if meal_plan is not None:
            resident.meal_plan = meal_plan
        if billing_cycle is not None:
            resident.billing_cycle = billing_cycle
        if rent_due_day is not None:
            resident.rent_due_day = rent_due_day
        if notes:
            resident.notes = notes

        if not resident.monthly_rent or float(resident.monthly_rent) <= 0:
            raise ConflictError(
                "This resident has no rent set. Enter a monthly rent to check them in.")

        if not resident.qr_token:
            resident.qr_token = generate_qr_token()

        bed = self.db.get(Bed, bed_id)
        self.audit.record(
            scope=self.scope, module="Residents", action=AuditAction.CREATE,
            description=(f"Checked in {resident.full_name} to bed "
                         f"{bed.bed_code or bed.bed_number} from {resident.joining_date}"),
            entity_type="customer", entity_id=resident.id, branch_id=resident.branch_id)

        invoice = None
        if raise_invoice:
            invoice = self._first_invoice(resident, food_charge=food_charge)

        self.notify.to_permission_holders(
            self.org_id, "customers.view", NotificationType.SYSTEM,
            "Resident checked in",
            f"{resident.full_name} moved into bed {bed.bed_code or bed.bed_number}.",
            branch_id=resident.branch_id,
            entity_type="customer", entity_id=resident.id)

        return resident, invoice

    def _first_invoice(self, resident: Customer, *, food_charge: float | None = None):
        """
        The move-in invoice: rent, optional food, and the deposit.

        Built through BillingService rather than by inserting rows here, so it
        gets the same numbering, tax handling, totalling and audit trail as
        every other invoice in the system.
        """
        from app.services.billing_service import BillingService, add_month  # cycle: billing imports residents

        items = [{
            "kind": InvoiceItemKind.RENT,
            "description": "Monthly rent",
            "amount": float(resident.monthly_rent),
        }]
        if food_charge:
            items.append({
                "kind": InvoiceItemKind.FOOD,
                "description": f"Food charges ({resident.meal_plan or 'meal plan'})",
                "amount": float(food_charge),
            })
        if resident.security_deposit and float(resident.security_deposit) > 0:
            items.append({
                "kind": InvoiceItemKind.DEPOSIT,
                "description": "Security deposit",
                "amount": float(resident.security_deposit),
            })

        joining = resident.joining_date or date.today()
        due_day = min(resident.rent_due_day or 5, 28)
        due = joining.replace(day=due_day)
        if due < joining:                       # joined after the due day
            due = add_month(joining).replace(day=due_day)

        return BillingService(self.db, self.scope).create_invoice({
            "resident_id": resident.id,
            "invoice_date": joining,
            "due_date": due,
            "period": joining.replace(day=1),
            "items": items,
            "notes": "Move-in invoice",
        })

    def reserve_bed(self, resident_id: uuid.UUID, bed_id: uuid.UUID) -> Customer:
        """A hold, not an occupancy - the bed is not sellable but nobody is in it."""
        resident = self.get(resident_id)
        bed = self._lock_bed(bed_id)
        if bed.status != BedStatus.AVAILABLE:
            raise ConflictError(f"That bed is {bed.status.lower()}, not available.")

        bed.status = BedStatus.RESERVED
        resident.status = CustomerStatus.RESERVED
        self._place(resident, bed)
        # current_customer_id stays null: the CHECK ties it to OCCUPIED only.
        self.audit.record(
            scope=self.scope, module="Residents", action=AuditAction.UPDATE,
            description=f"Reserved bed {bed.bed_code or bed.bed_number} for {resident.full_name}",
            entity_type="bed", entity_id=bed.id, branch_id=bed.branch_id)
        return resident

    def transfer(self, resident_id: uuid.UUID, to_bed_id: uuid.UUID,
                 reason: str | None = None) -> Customer:
        """
        Release the old bed and take the new one atomically.

        Both beds are locked before either is touched, ordered by id so two
        simultaneous transfers between the same pair cannot deadlock.
        """
        resident = self.get(resident_id)
        if resident.bed_id is None:
            raise ConflictError("This resident has no bed to transfer from.")
        if resident.bed_id == to_bed_id:
            raise ConflictError("The resident is already in that bed.")

        for bed_id in sorted([resident.bed_id, to_bed_id], key=str):
            self._lock_bed(bed_id)

        old = self.db.get(Bed, resident.bed_id)
        new = self.db.get(Bed, to_bed_id)
        self._assert_branch(new.branch_id)

        if new.status == BedStatus.OCCUPIED:
            raise ConflictError("The destination bed is already occupied.")
        if new.status in (BedStatus.MAINTENANCE, BedStatus.BLOCKED):
            raise ConflictError(
                f"The destination bed is marked {new.status.lower()}.")

        old.status = BedStatus.AVAILABLE
        old.current_customer_id = None
        new.status = BedStatus.OCCUPIED
        new.current_customer_id = resident.id
        self._place(resident, new)

        self.audit.record(
            scope=self.scope, module="Residents", action=AuditAction.TRANSFER,
            description=(f"Transferred {resident.full_name} from "
                         f"{old.bed_code or old.bed_number} to {new.bed_code or new.bed_number}"
                         + (f" ({reason})" if reason else "")),
            entity_type="resident", entity_id=resident.id, branch_id=new.branch_id)
        self.notify.to_resident(
            resident, "GATE_PASS" if False else "SYSTEM",
            "You have been moved",
            f"Your bed is now {new.bed_code or new.bed_number}.")
        return resident

    def checkout(self, resident_id: uuid.UUID, *, checkout_date: date | None = None,
                 notes: str | None = None) -> Customer:
        resident = self.get(resident_id)
        if resident.status == CustomerStatus.CHECKED_OUT:
            raise ConflictError("This resident has already checked out.")

        if resident.bed_id:
            bed = self._lock_bed(resident.bed_id)
            bed.status = BedStatus.AVAILABLE
            bed.current_customer_id = None

        # The placement is kept for history; only the live pointers are cleared.
        released = resident.bed_id
        self._place(resident, None)
        resident.status = CustomerStatus.CHECKED_OUT
        resident.actual_checkout_date = checkout_date or date.today()
        resident.is_active = False
        if notes:
            resident.notes = f"{resident.notes or ''}\nCheckout: {notes}".strip()

        self.audit.record(
            scope=self.scope, module="Residents", action=AuditAction.CHECKOUT,
            description=f"Checked out {resident.full_name}",
            entity_type="resident", entity_id=resident.id, branch_id=resident.branch_id)
        return resident

    def available_beds(self, branch_id: uuid.UUID | None = None, *,
                       for_resident: uuid.UUID | None = None) -> list[dict]:
        """
        Beds a resident could actually be put into, with their full address.

        `for_resident` widens the result to include the bed already reserved for
        that person. Without it a reservation is a trap: reserving a bed flips
        it out of AVAILABLE, so the resident it was held for could not then be
        checked into it - the one bed they are guaranteed would be the one bed
        missing from the list.
        """
        held_bed_id = None
        if for_resident is not None:
            resident = self.get(for_resident)
            if resident.status == CustomerStatus.RESERVED and resident.bed_id:
                held_bed_id = resident.bed_id

        availability = Bed.status == BedStatus.AVAILABLE
        if held_bed_id is not None:
            availability = or_(availability, Bed.id == held_bed_id)

        stmt = (
            select(Bed, Room, Floor, Building, Branch)
            .join(Room, Room.id == Bed.room_id)
            .join(Floor, Floor.id == Room.floor_id)
            .join(Building, Building.id == Room.building_id)
            .join(Branch, Branch.id == Bed.branch_id)
            .where(Bed.organization_id == self.org_id,
                   Bed.branch_id.in_(self.scope.branch_ids),
                   availability)
            .order_by(Branch.name, Building.name, Floor.floor_number, Room.room_number,
                      Bed.bed_number)
        )
        if branch_id:
            self._assert_branch(branch_id)
            stmt = stmt.where(Bed.branch_id == branch_id)

        return [
            {
                "id": str(bed.id), "bed_number": bed.bed_number, "bed_code": bed.bed_code,
                "rent_amount": float(bed.rent_amount),
                "status": str(bed.status),
                "reserved_for_this_resident": bed.id == held_bed_id,
                "room_id": str(room.id), "room_number": room.room_number,
                "room_type": room.room_type,
                "floor_name": floor.name, "building_name": building.name,
                "branch_id": str(branch.id), "branch_name": branch.name,
                "label": (f"{branch.code} · {building.name} · {floor.name} · "
                          f"Room {room.room_number} · Bed {bed.bed_number}"),
            }
            for bed, room, floor, building, branch in self.db.execute(stmt).all()
        ]

    # ----------------------------------------------------------------- KYC
    def list_kyc(self, resident_id: uuid.UUID, *, unmasked: bool = False) -> list[dict]:
        resident = self.get(resident_id)
        return [
            {
                "id": str(k.id), "id_type": k.id_type,
                # The full number is only ever returned to a caller holding
                # customers.kyc_view. Everyone else sees the last four digits.
                "id_number": k.id_number if unmasked else k.masked_number,
                "masked": not unmasked,
                "document_reference": k.document_reference, "status": k.status,
                "verified_at": k.verified_at.isoformat() if k.verified_at else None,
                "notes": k.notes,
            }
            for k in resident.kyc
        ]

    def add_kyc(self, resident_id: uuid.UUID, data: dict) -> ResidentKyc:
        resident = self.get(resident_id)
        existing = self.db.scalars(
            select(ResidentKyc).where(ResidentKyc.resident_id == resident.id,
                                      ResidentKyc.id_type == data["id_type"])).first()
        if existing:
            raise ConflictError(f"A {data['id_type']} record already exists for this resident.")

        row = ResidentKyc(
            organization_id=self.org_id, resident_id=resident.id,
            id_type=data["id_type"], id_number=data["id_number"].strip(),
            document_reference=data.get("document_reference"),
            status=KycStatus.SUBMITTED, notes=data.get("notes"))
        self.db.add(row)
        self.db.flush()
        # The number itself never reaches the audit log.
        self.audit.record(
            scope=self.scope, module="Residents", action=AuditAction.CREATE,
            description=f"Recorded {row.id_type} for {resident.full_name}",
            entity_type="resident_kyc", entity_id=row.id, branch_id=resident.branch_id)
        return row

    def verify_kyc(self, kyc_id: uuid.UUID, *, approved: bool,
                   notes: str | None = None) -> ResidentKyc:
        from datetime import datetime, timezone
        row = self.db.scalars(
            select(ResidentKyc).where(ResidentKyc.id == kyc_id,
                                      ResidentKyc.organization_id == self.org_id)).first()
        if row is None:
            raise NotFoundError("KYC record not found.")
        resident = self.get(row.resident_id)

        row.status = KycStatus.VERIFIED if approved else KycStatus.REJECTED
        row.verified_by_id = self.scope.user.id
        row.verified_at = datetime.now(timezone.utc)
        if notes:
            row.notes = notes

        self.audit.record(
            scope=self.scope, module="Residents", action=AuditAction.UPDATE,
            description=(f"{'Verified' if approved else 'Rejected'} {row.id_type} "
                         f"for {resident.full_name}"),
            entity_type="resident_kyc", entity_id=row.id, branch_id=resident.branch_id)
        return row

    def rotate_qr(self, resident_id: uuid.UUID) -> Customer:
        """Issue a new gate token. Used when a card is lost."""
        resident = self.get(resident_id)
        resident.qr_token = generate_qr_token()
        self.audit.record(
            scope=self.scope, module="Residents", action=AuditAction.UPDATE,
            description=f"Reissued gate QR for {resident.full_name}",
            entity_type="resident", entity_id=resident.id, branch_id=resident.branch_id)
        return resident
