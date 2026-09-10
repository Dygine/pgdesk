"""
Attendance, the QR gate, visitors, gate passes, food and laundry.

One idea runs through all of them: the person using these screens is standing at
a gate or a serving counter with a phone, and they will double-tap. So every
write here is idempotent by a natural key - resident+day for attendance,
resident+day+meal for food, resident+slot for laundry - and the gate suppresses
repeat scans inside a configurable window rather than trusting the button.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import CurrentScope
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models import (
    Attendance, Branch, Customer, FoodMenu, GateLog, GatePass, LaundryRequest,
    LaundrySlot, MealAttendance, OrganizationSettings, User, Visitor,
)
from app.models.enums import (
    AttendanceStatus, AttendanceSubject, AuditAction, CustomerStatus, GateDirection,
    GatePassStatus, LaundryRequestStatus, LaundrySlotStatus, MealStatus, MealType,
    NotificationType, VisitorStatus,
)
from app.services.audit import AuditService
from app.services.notification_service import NotificationService
from app.utils import qr_payload


class OperationsService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope
        self.audit = AuditService(db)
        self.notify = NotificationService(db)

    @property
    def org_id(self) -> uuid.UUID:
        return self.scope.organization_id

    def settings(self) -> OrganizationSettings:
        row = self.db.scalars(select(OrganizationSettings).where(
            OrganizationSettings.organization_id == self.org_id)).first()
        if row is None:
            row = OrganizationSettings(organization_id=self.org_id)
            self.db.add(row)
            self.db.flush()
        return row

    def _scoped(self, model):
        stmt = select(model).where(model.organization_id == self.org_id)
        if hasattr(model, "branch_id"):
            stmt = stmt.where(model.branch_id.in_(self.scope.branch_ids))
        return stmt

    def _resident(self, resident_id: uuid.UUID) -> Customer:
        row = self.db.scalars(select(Customer).where(
            Customer.id == resident_id, Customer.organization_id == self.org_id)).first()
        if row is None:
            raise NotFoundError("Resident not found.")
        if row.branch_id and not self.scope.owns_branch(row.branch_id):
            raise PermissionDeniedError("Branch access denied.")
        return row

    def _page(self, stmt, order, page, page_size):
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.db.scalars(
            stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)).all())
        return rows, total

    # ---------------------------------------------------------- attendance
    def list_attendance(self, *, on_date=None, subject=None, branch_id=None,
                        resident_id=None, status=None, page=1, page_size=50):
        stmt = self._scoped(Attendance).options(
            selectinload(Attendance.resident), selectinload(Attendance.user))
        if on_date:
            stmt = stmt.where(Attendance.on_date == on_date)
        if subject and subject != "all":
            stmt = stmt.where(Attendance.subject == subject)
        if branch_id:
            stmt = stmt.where(Attendance.branch_id == branch_id)
        if resident_id:
            stmt = stmt.where(Attendance.resident_id == resident_id)
        if status and status != "all":
            stmt = stmt.where(Attendance.status == status)
        return self._page(stmt, Attendance.on_date.desc(), page, page_size)

    def mark_attendance(self, data: dict) -> Attendance:
        """Upsert by (subject, day) so a second tap corrects rather than duplicates."""
        on_date = data.get("on_date") or date.today()
        resident = user = None

        if data.get("resident_id"):
            resident = self._resident(data["resident_id"])
            branch_id = resident.branch_id
            existing = self.db.scalars(select(Attendance).where(
                Attendance.resident_id == resident.id,
                Attendance.on_date == on_date)).first()
        elif data.get("user_id"):
            user = self.db.scalars(select(User).where(
                User.id == data["user_id"],
                User.organization_id == self.org_id)).first()
            if user is None:
                raise NotFoundError("Staff member not found.")
            branch_id = (user.branches[0].id if user.branches
                         else self.scope.branch_ids[0])
            existing = self.db.scalars(select(Attendance).where(
                Attendance.user_id == user.id,
                Attendance.on_date == on_date)).first()
        else:
            raise ConflictError("Attendance needs a resident or a staff member.")

        row = existing or Attendance(
            organization_id=self.org_id, branch_id=branch_id, on_date=on_date,
            subject=AttendanceSubject.RESIDENT if resident else AttendanceSubject.STAFF,
            resident_id=resident.id if resident else None,
            user_id=user.id if user else None)
        row.status = data.get("status") or AttendanceStatus.PRESENT
        row.source = data.get("source") or "manual"
        if data.get("check_in_at"):
            row.check_in_at = data["check_in_at"]
        if data.get("check_out_at"):
            row.check_out_at = data["check_out_at"]
        if data.get("notes"):
            row.notes = data["notes"]
        if existing is None:
            self.db.add(row)
        self.db.flush()
        return row

    # ------------------------------------------------------------ QR gate
    def scan(self, token: str, *, direction: str | None = None,
             gate: str | None = None) -> dict:
        """
        The gate flow.

        Always returns a result rather than raising, because the security guard
        needs to see *why* a scan failed on the screen in front of them, and an
        error envelope with no resident on it is useless at a gate. Every
        outcome, including a refusal, is written to the gate log.
        """
        settings = self.settings()
        now = datetime.now(timezone.utc)

        # A camera and a barcode gun both deliver the whole symbol, which now
        # carries a "PGD1:R:" marker; cards printed before the format existed,
        # and anything typed by hand, deliver the bare token. Both are accepted.
        kind, token = qr_payload.parse(token)

        if kind == qr_payload.KIND_GATE:
            # The guard pointed the scanner at the gate's own poster. Named
            # explicitly because "not recognised" would send them hunting for a
            # broken card that is working perfectly.
            gate = self.db.scalars(select(Branch).where(
                Branch.gate_qr_token == token,
                Branch.organization_id == self.org_id)).first()
            return {"result": "invalid", "allowed": False,
                    "message": (f"That is the gate code for {gate.name}, not a "
                                "resident's card." if gate else
                                "That is a gate code, not a resident's card.")}

        resident = self.db.scalars(select(Customer).where(
            Customer.qr_token == token,
            Customer.organization_id == self.org_id)).first()

        if resident is None:
            return {"result": "invalid", "allowed": False,
                    "message": "That QR code is not recognised."}
        if not self.scope.owns_branch(resident.branch_id):
            return {"result": "wrong_branch", "allowed": False,
                    "message": "This resident belongs to a branch you are not assigned to."}

        detail = {
            "resident": {
                "id": str(resident.id), "name": resident.full_name,
                "phone": resident.phone, "status": resident.status,
                "room": None, "bed": None, "branch_id": str(resident.branch_id),
            }
        }
        if resident.room_id:
            from app.models import Bed, Room
            room = self.db.get(Room, resident.room_id)
            bed = self.db.get(Bed, resident.bed_id) if resident.bed_id else None
            detail["resident"]["room"] = room.room_number if room else None
            detail["resident"]["bed"] = (bed.bed_code or bed.bed_number) if bed else None

        def log(direction_value, allowed, reason=None):
            self.db.add(GateLog(
                organization_id=self.org_id, branch_id=resident.branch_id,
                resident_id=resident.id, direction=direction_value,
                occurred_at=now, gate=gate, source="qr", allowed=allowed,
                reason=reason, recorded_by_id=self.scope.user.id))

        if resident.status == CustomerStatus.CHECKED_OUT:
            log(GateDirection.ENTRY, False, "checked out")
            return {**detail, "result": "checked_out", "allowed": False,
                    "message": f"{resident.full_name} has checked out."}
        if resident.status not in (CustomerStatus.ACTIVE, CustomerStatus.NOTICE):
            log(GateDirection.ENTRY, False, f"status {resident.status}")
            return {**detail, "result": "inactive", "allowed": False,
                    "message": f"{resident.full_name} is not an active resident."}

        # `occurred_at <= now` excludes future-dated rows. They can only reach
        # the table by import or seeding, since the write path always stamps
        # server time - but one is enough to sit permanently at the top of this
        # ordering, which would both invert the inferred direction and stop the
        # duplicate window ever comparing against the real previous scan.
        last = self.db.scalars(
            select(GateLog).where(GateLog.resident_id == resident.id,
                                  GateLog.allowed.is_(True),
                                  GateLog.occurred_at <= now)
            .order_by(GateLog.occurred_at.desc()).limit(1)).first()

        # Direction is inferred from the last accepted scan unless the caller
        # states it - the guard should not have to press a mode button.
        if direction is None:
            direction = (GateDirection.EXIT
                         if last and last.direction == GateDirection.ENTRY
                         else GateDirection.ENTRY)

        # Absolute gap: a gate log dated in the future makes the signed
        # difference negative, which is below any window and would refuse every
        # future scan as a duplicate - permanently, and with a nonsensical
        # "scanned -4867s ago" on the guard's screen.
        gap = abs((now - last.occurred_at).total_seconds()) if last else None
        if last and gap < settings.gate_duplicate_window_seconds:
            return {**detail, "result": "duplicate", "allowed": False,
                    "direction": last.direction,
                    "message": f"Already scanned {int(gap)}s ago — ignored."}

        log(direction, True)

        # An entry scan is also the day's attendance. One action, one record.
        if direction == GateDirection.ENTRY:
            self.mark_attendance({
                "resident_id": resident.id, "on_date": now.date(),
                "status": AttendanceStatus.PRESENT, "source": "gate",
                "check_in_at": now,
            })
        else:
            existing = self.db.scalars(select(Attendance).where(
                Attendance.resident_id == resident.id,
                Attendance.on_date == now.date())).first()
            if existing:
                existing.check_out_at = now

        return {**detail, "result": "ok", "allowed": True, "direction": direction,
                "occurred_at": now.isoformat(),
                "message": ("Entry recorded" if direction == GateDirection.ENTRY
                            else "Exit recorded")}

    def list_gate_logs(self, *, branch_id=None, resident_id=None, on_date=None,
                       direction=None, page=1, page_size=50):
        stmt = self._scoped(GateLog).options(selectinload(GateLog.resident))
        if branch_id:
            stmt = stmt.where(GateLog.branch_id == branch_id)
        if resident_id:
            stmt = stmt.where(GateLog.resident_id == resident_id)
        if direction and direction != "all":
            stmt = stmt.where(GateLog.direction == direction)
        if on_date:
            stmt = stmt.where(func.date(GateLog.occurred_at) == on_date)
        return self._page(stmt, GateLog.occurred_at.desc(), page, page_size)

    # ----------------------------------------------------------- visitors
    def list_visitors(self, *, status=None, branch_id=None, resident_id=None,
                      search=None, page=1, page_size=25):
        stmt = self._scoped(Visitor).options(selectinload(Visitor.resident))
        if status and status != "all":
            stmt = stmt.where(Visitor.status == status)
        if branch_id:
            stmt = stmt.where(Visitor.branch_id == branch_id)
        if resident_id:
            stmt = stmt.where(Visitor.resident_id == resident_id)
        if search:
            stmt = stmt.where(Visitor.name.ilike(f"%{search.strip()}%"))
        return self._page(stmt, Visitor.created_at.desc(), page, page_size)

    def create_visitor(self, data: dict, *, requested_by_resident: bool = False) -> Visitor:
        resident = self._resident(data["resident_id"])
        settings = self.settings()

        visitor = Visitor(
            organization_id=self.org_id, branch_id=resident.branch_id,
            resident_id=resident.id, name=data["name"].strip(),
            phone=data.get("phone"), relation=data.get("relation"),
            purpose=data.get("purpose"), expected_at=data.get("expected_at"),
            id_proof_reference=data.get("id_proof_reference"),
            notes=data.get("notes"),
            # When approval is switched off, a logged visitor is approved on
            # arrival; otherwise staff must act before entry.
            status=(VisitorStatus.PENDING if settings.visitor_approval_required
                    else VisitorStatus.APPROVED))
        if not settings.visitor_approval_required:
            visitor.approved_by_id = self.scope.user.id
        self.db.add(visitor)
        self.db.flush()

        self.audit.record(
            scope=self.scope, module="Visitors", action=AuditAction.CREATE,
            description=f"Visitor {visitor.name} for {resident.full_name}",
            entity_type="visitor", entity_id=visitor.id, branch_id=visitor.branch_id)
        if visitor.status == VisitorStatus.PENDING:
            self.notify.to_permission_holders(
                self.org_id, "visitors.approve", NotificationType.VISITOR_REQUEST,
                "Visitor awaiting approval",
                f"{visitor.name} to see {resident.full_name}.",
                branch_id=visitor.branch_id, entity_type="visitor", entity_id=visitor.id)
        return visitor

    def decide_visitor(self, visitor_id: uuid.UUID, *, approved: bool,
                       note: str | None = None) -> Visitor:
        visitor = self.db.scalars(
            self._scoped(Visitor).where(Visitor.id == visitor_id)).first()
        if visitor is None:
            raise NotFoundError("Visitor not found.")
        if visitor.status in (VisitorStatus.INSIDE, VisitorStatus.COMPLETED):
            raise ConflictError("This visit has already started.")

        visitor.status = VisitorStatus.APPROVED if approved else VisitorStatus.REJECTED
        visitor.approved_by_id = self.scope.user.id
        if note:
            visitor.notes = f"{visitor.notes or ''}\n{note}".strip()

        self.audit.record(
            scope=self.scope, module="Visitors", action=AuditAction.APPROVE,
            description=f"{'Approved' if approved else 'Rejected'} visitor {visitor.name}",
            entity_type="visitor", entity_id=visitor.id, branch_id=visitor.branch_id)
        resident = self.db.get(Customer, visitor.resident_id)
        if resident:
            self.notify.to_resident(
                resident, NotificationType.VISITOR_REQUEST,
                f"Visitor {'approved' if approved else 'rejected'}",
                f"{visitor.name} was {'approved' if approved else 'not approved'}.",
                entity_type="visitor", entity_id=visitor.id, link="/me/visitors")
        return visitor

    def visitor_movement(self, visitor_id: uuid.UUID, *, entering: bool) -> Visitor:
        visitor = self.db.scalars(
            self._scoped(Visitor).where(Visitor.id == visitor_id)).first()
        if visitor is None:
            raise NotFoundError("Visitor not found.")
        now = datetime.now(timezone.utc)

        if entering:
            if visitor.status != VisitorStatus.APPROVED:
                raise ConflictError(
                    "This visitor has not been approved. Approve the request first.")
            visitor.status = VisitorStatus.INSIDE
            visitor.entry_at = now
        else:
            if visitor.status != VisitorStatus.INSIDE:
                raise ConflictError("This visitor is not currently inside.")
            visitor.status = VisitorStatus.COMPLETED
            visitor.exit_at = now

        self.db.add(GateLog(
            organization_id=self.org_id, branch_id=visitor.branch_id,
            visitor_id=visitor.id,
            direction=GateDirection.ENTRY if entering else GateDirection.EXIT,
            occurred_at=now, source="desk", allowed=True,
            recorded_by_id=self.scope.user.id))
        return visitor

    # --------------------------------------------------------- gate passes
    def list_gate_passes(self, *, status=None, branch_id=None, resident_id=None,
                         page=1, page_size=25):
        stmt = self._scoped(GatePass).options(selectinload(GatePass.resident))
        if status and status != "all":
            stmt = stmt.where(GatePass.status == status)
        if branch_id:
            stmt = stmt.where(GatePass.branch_id == branch_id)
        if resident_id:
            stmt = stmt.where(GatePass.resident_id == resident_id)
        return self._page(stmt, GatePass.created_at.desc(), page, page_size)

    def create_gate_pass(self, data: dict) -> GatePass:
        resident = self._resident(data["resident_id"])
        settings = self.settings()
        if data["to_at"] <= data["from_at"]:
            raise ConflictError("The return time must be after the departure time.")

        last = self.db.scalar(select(func.count(GatePass.id)).where(
            GatePass.organization_id == self.org_id))
        gate_pass = GatePass(
            organization_id=self.org_id, branch_id=resident.branch_id,
            resident_id=resident.id, pass_number=f"GP-{(last or 0) + 1:05d}",
            reason=data["reason"], destination=data.get("destination"),
            from_at=data["from_at"], to_at=data["to_at"],
            is_emergency=bool(data.get("is_emergency")),
            status=(GatePassStatus.PENDING if settings.gate_pass_approval_required
                    else GatePassStatus.APPROVED))
        self.db.add(gate_pass)
        self.db.flush()

        self.audit.record(
            scope=self.scope, module="Gate passes", action=AuditAction.CREATE,
            description=f"Gate pass {gate_pass.pass_number} for {resident.full_name}",
            entity_type="gate_pass", entity_id=gate_pass.id, branch_id=gate_pass.branch_id)
        if gate_pass.status == GatePassStatus.PENDING:
            self.notify.to_permission_holders(
                self.org_id, "gatepass.approve", NotificationType.GATE_PASS,
                "Gate pass awaiting approval",
                f"{resident.full_name}: {gate_pass.reason}",
                branch_id=gate_pass.branch_id,
                entity_type="gate_pass", entity_id=gate_pass.id)
        return gate_pass

    def decide_gate_pass(self, pass_id: uuid.UUID, *, approved: bool,
                         note: str | None = None) -> GatePass:
        gate_pass = self.db.scalars(
            self._scoped(GatePass).where(GatePass.id == pass_id)).first()
        if gate_pass is None:
            raise NotFoundError("Gate pass not found.")
        if gate_pass.status not in (GatePassStatus.PENDING,):
            raise ConflictError(f"This pass is already {gate_pass.status.lower()}.")

        gate_pass.status = GatePassStatus.APPROVED if approved else GatePassStatus.REJECTED
        gate_pass.approved_by_id = self.scope.user.id
        gate_pass.approved_at = datetime.now(timezone.utc)
        gate_pass.decision_note = note

        self.audit.record(
            scope=self.scope, module="Gate passes", action=AuditAction.APPROVE,
            description=(f"{'Approved' if approved else 'Rejected'} gate pass "
                         f"{gate_pass.pass_number}"),
            entity_type="gate_pass", entity_id=gate_pass.id, branch_id=gate_pass.branch_id)
        resident = self.db.get(Customer, gate_pass.resident_id)
        if resident:
            self.notify.to_resident(
                resident, NotificationType.GATE_PASS,
                f"Gate pass {'approved' if approved else 'rejected'}",
                gate_pass.reason, entity_type="gate_pass", entity_id=gate_pass.id,
                link="/me/gate-pass")
        return gate_pass

    def set_gate_pass_status(self, pass_id: uuid.UUID, status: str) -> GatePass:
        """Security marks a pass ACTIVE on departure and COMPLETED on return."""
        gate_pass = self.db.scalars(
            self._scoped(GatePass).where(GatePass.id == pass_id)).first()
        if gate_pass is None:
            raise NotFoundError("Gate pass not found.")
        if status in (GatePassStatus.ACTIVE, GatePassStatus.COMPLETED) \
                and gate_pass.status not in (GatePassStatus.APPROVED, GatePassStatus.ACTIVE):
            raise ConflictError(
                "Security can only act on an approved pass. This one is "
                f"{gate_pass.status.lower()}.")
        gate_pass.status = status
        return gate_pass

    # --------------------------------------------------------------- food
    def list_menus(self, *, branch_id=None, from_date=None, to_date=None):
        stmt = self._scoped(FoodMenu)
        if branch_id:
            stmt = stmt.where(FoodMenu.branch_id == branch_id)
        if from_date:
            stmt = stmt.where(FoodMenu.on_date >= from_date)
        if to_date:
            stmt = stmt.where(FoodMenu.on_date <= to_date)
        return list(self.db.scalars(stmt.order_by(FoodMenu.on_date, FoodMenu.meal)).all())

    def upsert_menu(self, data: dict) -> FoodMenu:
        branch_id = data["branch_id"]
        if not self.scope.owns_branch(branch_id):
            raise PermissionDeniedError("Branch access denied.")
        row = self.db.scalars(select(FoodMenu).where(
            FoodMenu.branch_id == branch_id, FoodMenu.on_date == data["on_date"],
            FoodMenu.meal == data["meal"])).first()
        if row is None:
            row = FoodMenu(organization_id=self.org_id, branch_id=branch_id,
                           on_date=data["on_date"], meal=data["meal"])
            self.db.add(row)
        row.items = data["items"]
        row.calories = data.get("calories")
        row.serve_from = data.get("serve_from")
        row.serve_to = data.get("serve_to")
        row.notes = data.get("notes")
        self.db.flush()
        return row

    def set_meal(self, data: dict) -> MealAttendance:
        """Upsert by (resident, day, meal). Opt-outs and attendance share a row."""
        resident = self._resident(data["resident_id"])
        on_date = data.get("on_date") or date.today()
        row = self.db.scalars(select(MealAttendance).where(
            MealAttendance.resident_id == resident.id,
            MealAttendance.on_date == on_date,
            MealAttendance.meal == data["meal"])).first()
        if row is None:
            row = MealAttendance(
                organization_id=self.org_id, branch_id=resident.branch_id,
                resident_id=resident.id, on_date=on_date, meal=data["meal"])
            self.db.add(row)
        row.status = data.get("status") or MealStatus.EXPECTED
        row.marked_by_id = self.scope.user.id if self.scope.user else None
        self.db.flush()
        return row

    def meal_counts(self, *, on_date: date | None = None,
                    branch_id: uuid.UUID | None = None) -> dict:
        on_date = on_date or date.today()
        branch_ids = [branch_id] if branch_id else list(self.scope.branch_ids)
        rows = self.db.execute(
            select(MealAttendance.meal, MealAttendance.status, func.count())
            .where(MealAttendance.organization_id == self.org_id,
                   MealAttendance.branch_id.in_(branch_ids or [uuid.UUID(int=0)]),
                   MealAttendance.on_date == on_date)
            .group_by(MealAttendance.meal, MealAttendance.status)).all()

        out = {m.value: {s.value.lower(): 0 for s in MealStatus} for m in MealType}
        for meal, status, n in rows:
            out[meal][status.lower()] = n
        for meal, counts in out.items():
            counts["expected_total"] = (
                counts["expected"] + counts["attended"] + counts["skipped"])
        return {"date": on_date.isoformat(), "meals": out}

    # ------------------------------------------------------------ laundry
    def list_slots(self, *, branch_id=None, from_date=None, to_date=None):
        stmt = self._scoped(LaundrySlot).options(selectinload(LaundrySlot.requests))
        if branch_id:
            stmt = stmt.where(LaundrySlot.branch_id == branch_id)
        if from_date:
            stmt = stmt.where(LaundrySlot.on_date >= from_date)
        if to_date:
            stmt = stmt.where(LaundrySlot.on_date <= to_date)
        return list(self.db.scalars(
            stmt.order_by(LaundrySlot.on_date, LaundrySlot.start_time)).all())

    def create_slot(self, data: dict) -> LaundrySlot:
        if not self.scope.owns_branch(data["branch_id"]):
            raise PermissionDeniedError("Branch access denied.")
        clash = self.db.scalars(select(LaundrySlot).where(
            LaundrySlot.branch_id == data["branch_id"],
            LaundrySlot.on_date == data["on_date"],
            LaundrySlot.start_time == data["start_time"])).first()
        if clash:
            raise ConflictError("A slot already starts at that time on that day.")

        slot = LaundrySlot(
            organization_id=self.org_id, branch_id=data["branch_id"],
            on_date=data["on_date"], start_time=data["start_time"],
            end_time=data["end_time"], capacity=data.get("capacity") or 10,
            status=data.get("status") or LaundrySlotStatus.AVAILABLE)
        self.db.add(slot)
        self.db.flush()
        return slot

    def book_slot(self, data: dict) -> LaundryRequest:
        """
        Booking takes a row lock on the slot.

        Capacity is the whole point of a slot; without the lock two residents
        can both read "9 of 10 booked" and both take the last place.
        """
        resident = self._resident(data["resident_id"])
        slot = self.db.scalars(
            select(LaundrySlot)
            .where(LaundrySlot.id == data["slot_id"],
                   LaundrySlot.organization_id == self.org_id)
            .with_for_update()).first()
        if slot is None:
            raise NotFoundError("Laundry slot not found.")
        if not self.scope.owns_branch(slot.branch_id):
            raise PermissionDeniedError("Branch access denied.")
        if slot.status in (LaundrySlotStatus.CLOSED, LaundrySlotStatus.CANCELLED):
            raise ConflictError(f"That slot is {slot.status.lower()}.")

        existing = self.db.scalars(select(LaundryRequest).where(
            LaundryRequest.resident_id == resident.id,
            LaundryRequest.slot_id == slot.id)).first()
        if existing and existing.status != LaundryRequestStatus.CANCELLED:
            raise ConflictError("You already have a booking in this slot.")

        booked = self.db.scalar(select(func.count(LaundryRequest.id)).where(
            LaundryRequest.slot_id == slot.id,
            LaundryRequest.status != LaundryRequestStatus.CANCELLED)) or 0
        if booked >= slot.capacity:
            raise ConflictError("That slot is full. Please choose another.")

        if existing:
            existing.status = LaundryRequestStatus.BOOKED
            existing.item_count = data.get("item_count") or 1
            request = existing
        else:
            request = LaundryRequest(
                organization_id=self.org_id, branch_id=slot.branch_id,
                resident_id=resident.id, slot_id=slot.id,
                item_count=data.get("item_count") or 1,
                notes=data.get("notes"), status=LaundryRequestStatus.BOOKED)
            self.db.add(request)
        self.db.flush()

        if booked + 1 >= slot.capacity:
            slot.status = LaundrySlotStatus.FULL
        return request

    def list_laundry(self, *, status=None, branch_id=None, resident_id=None,
                     page=1, page_size=25):
        stmt = self._scoped(LaundryRequest).options(
            selectinload(LaundryRequest.resident), selectinload(LaundryRequest.slot))
        if status and status != "all":
            stmt = stmt.where(LaundryRequest.status == status)
        if branch_id:
            stmt = stmt.where(LaundryRequest.branch_id == branch_id)
        if resident_id:
            stmt = stmt.where(LaundryRequest.resident_id == resident_id)
        return self._page(stmt, LaundryRequest.created_at.desc(), page, page_size)

    def set_laundry_status(self, request_id: uuid.UUID, status: str) -> LaundryRequest:
        request = self.db.scalars(
            self._scoped(LaundryRequest).where(LaundryRequest.id == request_id)).first()
        if request is None:
            raise NotFoundError("Laundry request not found.")
        request.status = status
        if status == LaundryRequestStatus.COLLECTED:
            request.collected_at = datetime.now(timezone.utc)
        if status == LaundryRequestStatus.CANCELLED:
            slot = self.db.get(LaundrySlot, request.slot_id)
            if slot and slot.status == LaundrySlotStatus.FULL:
                slot.status = LaundrySlotStatus.AVAILABLE
        return request
