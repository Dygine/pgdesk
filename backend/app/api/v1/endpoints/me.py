"""
The resident portal.

Every endpoint here derives the resident from the token and nothing else. There
is no `resident_id` parameter anywhere in this file - not even an optional one -
because the moment one exists, some handler will trust it. Isolation is
structural rather than checked.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select

from app.core.dependencies import CurrentCustomer, DbSession
from app.core.exceptions import ConflictError, NotFoundError
from app.core.responses import ok, paginated
from app.models import (
    Announcement, Attendance, Bed, Branch, Building, Complaint, ComplaintUpdate,
    Customer, Floor, FoodMenu, GateLog, GatePass, Invoice, LaundryRequest,
    LaundrySlot, MealAttendance, Organization, OrganizationSettings, Payment,
    QueryMessage, ResidentKyc, Room, SupportQuery, Visitor,
)
from app.models.enums import (
    AnnouncementAudience, ComplaintStatus, GatePassStatus, InvoiceStatus,
    LaundryRequestStatus, MealStatus, PaymentStatus, PublishStatus, QueryStatus,
    TicketPriority, VisitorStatus,
)
from app.schemas.operations import (
    ComplaintCreate, GatePassCreate, MealMark, QueryCreate, QueryReply,
    SlotBooking, VisitorCreate,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/me", tags=["resident portal"])


def _settings(db, organization_id) -> OrganizationSettings:
    row = db.scalars(select(OrganizationSettings).where(
        OrganizationSettings.organization_id == organization_id)).first()
    return row or OrganizationSettings(organization_id=organization_id)


# ---------------------------------------------------------------- my home
@router.get("/home", summary="Where I live and what needs my attention")
def my_home(db: DbSession, me: CurrentCustomer) -> dict:
    branch = db.get(Branch, me.branch_id) if me.branch_id else None
    room = db.get(Room, me.room_id) if me.room_id else None
    bed = db.get(Bed, me.bed_id) if me.bed_id else None

    outstanding = float(db.scalar(
        select(func.sum(Invoice.balance)).where(
            Invoice.resident_id == me.id, Invoice.balance > 0,
            Invoice.status != InvoiceStatus.CANCELLED)) or 0)
    next_due = db.scalars(
        select(Invoice).where(Invoice.resident_id == me.id, Invoice.balance > 0,
                              Invoice.status != InvoiceStatus.CANCELLED)
        .order_by(Invoice.due_date).limit(1)).first()

    open_complaints = db.scalar(
        select(func.count(Complaint.id)).where(
            Complaint.resident_id == me.id,
            Complaint.status.notin_([ComplaintStatus.RESOLVED,
                                     ComplaintStatus.CLOSED]))) or 0

    today = date.today()
    announcements = db.scalars(
        select(Announcement).where(
            Announcement.organization_id == me.organization_id,
            Announcement.status == PublishStatus.PUBLISHED,
            Announcement.audience.in_([AnnouncementAudience.ALL,
                                       AnnouncementAudience.RESIDENTS,
                                       AnnouncementAudience.BRANCH]),
            or_(Announcement.branch_id.is_(None), Announcement.branch_id == me.branch_id),
            or_(Announcement.ends_on.is_(None), Announcement.ends_on >= today))
        .order_by(Announcement.created_at.desc()).limit(5)).all()

    return ok({
        "resident": {
            "id": str(me.id), "name": me.full_name, "email": me.email,
            "phone": me.phone, "status": me.status,
            "joining_date": me.joining_date.isoformat() if me.joining_date else None,
            "monthly_rent": float(me.monthly_rent),
            "security_deposit": float(me.security_deposit),
        },
        "placement": {
            "branch": branch.name if branch else None,
            "building": (db.get(Building, me.building_id).name
                         if me.building_id else None),
            "floor": db.get(Floor, me.floor_id).name if me.floor_id else None,
            "room": room.room_number if room else None,
            "room_type": room.room_type if room else None,
            "bed": (bed.bed_code or bed.bed_number) if bed else None,
            "has_ac": room.has_ac if room else None,
        },
        "rent": {
            "outstanding": round(outstanding, 2),
            "next_due_date": next_due.due_date.isoformat() if next_due else None,
            "next_due_amount": float(next_due.balance) if next_due else 0,
        },
        "open_complaints": open_complaints,
        "unread_notifications": NotificationService(db).unread_count(
            me.organization_id, resident_id=me.id),
        "announcements": [
            {"id": str(a.id), "title": a.title, "message": a.message,
             "priority": a.priority, "created_at": a.created_at.isoformat()}
            for a in announcements],
    })


# -------------------------------------------------------------- my profile
@router.get("/profile", summary="My full record as the PG holds it")
def my_profile(db: DbSession, me: CurrentCustomer) -> dict:
    """
    Separate from /me/home, which is a dashboard.

    Only the KYC *status* is returned, never the document number. A resident
    already knows their own Aadhaar; echoing it back puts it in a response that
    gets logged, cached and screenshotted for no benefit.
    """
    branch = db.get(Branch, me.branch_id) if me.branch_id else None
    room = db.get(Room, me.room_id) if me.room_id else None
    bed = db.get(Bed, me.bed_id) if me.bed_id else None
    organization = db.get(Organization, me.organization_id)

    kyc = db.scalars(
        select(ResidentKyc)
        .where(ResidentKyc.resident_id == me.id)
        .order_by(ResidentKyc.created_at.desc())).all()

    return ok({
        "id": str(me.id),
        "name": me.full_name,
        "email": me.email,
        "phone": me.phone,
        "alternate_phone": me.alternate_phone,
        "status": me.status,
        "gender": me.gender,
        "date_of_birth": me.date_of_birth.isoformat() if me.date_of_birth else None,
        "occupation": me.occupation,
        "address": me.address,
        "city": me.city,
        "state": me.state,
        "pincode": me.pincode,
        "organization": organization.name if organization else None,
        "stay": {
            "branch": branch.name if branch else None,
            "building": (db.get(Building, me.building_id).name
                         if me.building_id else None),
            "floor": db.get(Floor, me.floor_id).name if me.floor_id else None,
            "room": room.room_number if room else None,
            "room_type": room.room_type if room else None,
            "has_ac": room.has_ac if room else None,
            "bed": (bed.bed_code or bed.bed_number) if bed else None,
            "joining_date": me.joining_date.isoformat() if me.joining_date else None,
            "monthly_rent": float(me.monthly_rent),
            "security_deposit": float(me.security_deposit),
            "meal_plan": me.meal_plan,
            "billing_cycle": me.billing_cycle,
            "rent_due_day": me.rent_due_day,
        },
        "emergency_contact": {
            "name": me.emergency_contact_name,
            "phone": me.emergency_contact_phone,
            "relation": me.emergency_contact_relation,
        },
        "identity": [
            {"id_type": k.id_type, "status": k.status,
             "verified_at": k.verified_at.isoformat() if k.verified_at else None}
            for k in kyc
        ],
    })


# ---------------------------------------------------------------- my rent
@router.get("/rent", summary="My invoices, payments and balance")
def my_rent(db: DbSession, me: CurrentCustomer) -> dict:
    invoices = db.scalars(
        select(Invoice).where(Invoice.resident_id == me.id)
        .order_by(Invoice.invoice_date.desc()).limit(24)).all()
    payments = db.scalars(
        select(Payment).where(Payment.resident_id == me.id)
        .order_by(Payment.payment_date.desc()).limit(24)).all()

    return ok({
        "summary": {
            "monthly_rent": float(me.monthly_rent),
            "security_deposit": float(me.security_deposit),
            "rent_due_day": me.rent_due_day,
            "outstanding": round(sum(
                float(i.balance) for i in invoices
                if i.status != InvoiceStatus.CANCELLED), 2),
            "paid_this_year": round(sum(
                float(p.amount) for p in payments
                if p.status == PaymentStatus.VERIFIED
                and p.payment_date.year == date.today().year), 2),
        },
        "invoices": [
            {"id": str(i.id), "invoice_number": i.invoice_number,
             "invoice_date": i.invoice_date.isoformat(),
             "due_date": i.due_date.isoformat(), "total": float(i.total),
             "paid_amount": float(i.paid_amount), "balance": float(i.balance),
             "status": i.status,
             "items": [{"description": it.description, "amount": float(it.amount)}
                       for it in i.items]}
            for i in invoices],
        "payments": [
            {"id": str(p.id), "payment_number": p.payment_number,
             "amount": float(p.amount), "method": p.method, "status": p.status,
             "payment_date": p.payment_date.isoformat(), "reference": p.reference}
            for p in payments],
    })


# ---------------------------------------------------------- my attendance
@router.get("/attendance", summary="My attendance history")
def my_attendance(db: DbSession, me: CurrentCustomer,
                  days: int = Query(default=60, ge=1, le=365)) -> dict:
    since = date.today() - timedelta(days=days)
    rows = db.scalars(
        select(Attendance).where(Attendance.resident_id == me.id,
                                 Attendance.on_date >= since)
        .order_by(Attendance.on_date.desc())).all()
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return ok({
        "summary": counts, "days": days,
        "records": [
            {"on_date": r.on_date.isoformat(), "status": r.status, "source": r.source,
             "check_in_at": r.check_in_at.isoformat() if r.check_in_at else None,
             "check_out_at": r.check_out_at.isoformat() if r.check_out_at else None}
            for r in rows],
    })


@router.get("/qr", summary="My gate QR and recent movements")
def my_qr(db: DbSession, me: CurrentCustomer) -> dict:
    """
    The token is returned only to its owner, over an authenticated request.

    It carries no personal information - it is a random string the gate looks
    up - so a photographed QR reveals nothing about the resident, and a lost
    card is fixed by reissuing rather than by changing anything else.
    """
    logs = db.scalars(
        select(GateLog).where(GateLog.resident_id == me.id)
        .order_by(GateLog.occurred_at.desc()).limit(30)).all()
    return ok({
        "token": me.qr_token,
        "active": me.status in ("ACTIVE", "NOTICE"),
        "logs": [
            {"id": str(g.id), "direction": g.direction, "allowed": g.allowed,
             "gate": g.gate, "reason": g.reason,
             "occurred_at": g.occurred_at.isoformat()}
            for g in logs],
    })


# ---------------------------------------------------------------- my food
@router.get("/food", summary="Menu and my meal choices")
def my_food(db: DbSession, me: CurrentCustomer,
            days: int = Query(default=7, ge=1, le=31)) -> dict:
    today = date.today()
    until = today + timedelta(days=days)
    menus = db.scalars(
        select(FoodMenu).where(FoodMenu.branch_id == me.branch_id,
                               FoodMenu.on_date.between(today - timedelta(days=1), until))
        .order_by(FoodMenu.on_date, FoodMenu.meal)).all()
    mine = db.scalars(
        select(MealAttendance).where(
            MealAttendance.resident_id == me.id,
            MealAttendance.on_date.between(today - timedelta(days=7), until))).all()
    chosen = {(m.on_date.isoformat(), m.meal): m.status for m in mine}

    return ok({
        "menus": [
            {"id": str(m.id), "on_date": m.on_date.isoformat(), "meal": m.meal,
             "items": m.items, "calories": m.calories,
             "serve_from": m.serve_from.isoformat() if m.serve_from else None,
             "my_status": chosen.get((m.on_date.isoformat(), m.meal))}
            for m in menus],
        "history": [
            {"on_date": m.on_date.isoformat(), "meal": m.meal, "status": m.status}
            for m in sorted(mine, key=lambda x: x.on_date, reverse=True)],
    })


@router.post("/food/opt", summary="Opt in or out of a meal")
def my_meal_choice(body: MealMark, db: DbSession, me: CurrentCustomer) -> dict:
    """
    The resident_id in the body is ignored - the row is always keyed to the
    signed-in resident, so this cannot be used to change somebody else's meal.
    """
    on_date = body.on_date or date.today()
    settings = _settings(db, me.organization_id)

    # A kitchen that has already bought the food cannot un-buy it.
    cutoff = datetime.combine(on_date, datetime.min.time(), tzinfo=timezone.utc) \
        - timedelta(hours=settings.meal_optout_cutoff_hours)
    if body.status == MealStatus.OPTED_OUT and datetime.now(timezone.utc) > cutoff \
            and on_date <= date.today():
        raise ConflictError(
            f"Opting out closes {settings.meal_optout_cutoff_hours} hours before the day "
            "starts. Please speak to the kitchen.")

    row = db.scalars(select(MealAttendance).where(
        MealAttendance.resident_id == me.id, MealAttendance.on_date == on_date,
        MealAttendance.meal == body.meal)).first()
    if row is None:
        row = MealAttendance(
            organization_id=me.organization_id, branch_id=me.branch_id,
            resident_id=me.id, on_date=on_date, meal=body.meal)
        db.add(row)
    row.status = body.status
    db.commit()
    return ok({"on_date": on_date.isoformat(), "meal": row.meal, "status": row.status},
              message="Saved.")


# ------------------------------------------------------------- my laundry
@router.get("/laundry", summary="Laundry slots and my bookings")
def my_laundry(db: DbSession, me: CurrentCustomer) -> dict:
    today = date.today()
    slots = db.scalars(
        select(LaundrySlot).where(LaundrySlot.branch_id == me.branch_id,
                                  LaundrySlot.on_date.between(today, today + timedelta(days=14)))
        .order_by(LaundrySlot.on_date, LaundrySlot.start_time)).all()
    mine = db.scalars(
        select(LaundryRequest).where(LaundryRequest.resident_id == me.id)
        .order_by(LaundryRequest.created_at.desc()).limit(20)).all()
    booked_slot_ids = {r.slot_id for r in mine
                       if r.status != LaundryRequestStatus.CANCELLED}
    return ok({
        "slots": [
            {"id": str(s.id), "on_date": s.on_date.isoformat(),
             "start_time": s.start_time.isoformat(), "end_time": s.end_time.isoformat(),
             "capacity": s.capacity, "booked": s.booked,
             "remaining": max(s.capacity - s.booked, 0), "status": s.status,
             "mine": s.id in booked_slot_ids}
            for s in slots],
        "requests": [
            {"id": str(r.id), "status": r.status, "item_count": r.item_count,
             "on_date": r.slot.on_date.isoformat() if r.slot else None,
             "start_time": r.slot.start_time.isoformat() if r.slot else None,
             "created_at": r.created_at.isoformat()}
            for r in mine],
    })


@router.post("/laundry/book", status_code=status.HTTP_201_CREATED,
             summary="Book a laundry slot")
def book_laundry(body: SlotBooking, db: DbSession, me: CurrentCustomer) -> dict:
    slot = db.scalars(
        select(LaundrySlot).where(LaundrySlot.id == body.slot_id,
                                  LaundrySlot.organization_id == me.organization_id)
        .with_for_update()).first()
    if slot is None:
        raise NotFoundError("That slot does not exist.")
    if slot.branch_id != me.branch_id:
        raise NotFoundError("That slot does not exist.")
    if slot.status in ("CLOSED", "CANCELLED"):
        raise ConflictError(f"That slot is {slot.status.lower()}.")

    existing = db.scalars(select(LaundryRequest).where(
        LaundryRequest.resident_id == me.id,
        LaundryRequest.slot_id == slot.id)).first()
    if existing and existing.status != LaundryRequestStatus.CANCELLED:
        raise ConflictError("You already have a booking in this slot.")

    booked = db.scalar(select(func.count(LaundryRequest.id)).where(
        LaundryRequest.slot_id == slot.id,
        LaundryRequest.status != LaundryRequestStatus.CANCELLED)) or 0
    if booked >= slot.capacity:
        raise ConflictError("That slot just filled up. Please pick another.")

    if existing:
        existing.status = LaundryRequestStatus.BOOKED
        existing.item_count = body.item_count
        request = existing
    else:
        request = LaundryRequest(
            organization_id=me.organization_id, branch_id=me.branch_id,
            resident_id=me.id, slot_id=slot.id, item_count=body.item_count,
            notes=body.notes, status=LaundryRequestStatus.BOOKED)
        db.add(request)
    if booked + 1 >= slot.capacity:
        slot.status = "FULL"
    db.commit()
    return ok({"id": str(request.id), "status": request.status}, message="Slot booked.")


@router.post("/laundry/{request_id}/cancel", summary="Cancel my booking")
def cancel_laundry(request_id: uuid.UUID, db: DbSession, me: CurrentCustomer) -> dict:
    request = db.scalars(select(LaundryRequest).where(
        LaundryRequest.id == request_id, LaundryRequest.resident_id == me.id)).first()
    if request is None:
        raise NotFoundError("Booking not found.")
    if request.status in (LaundryRequestStatus.COLLECTED, LaundryRequestStatus.PROCESSING):
        raise ConflictError("This laundry is already being handled.")
    request.status = LaundryRequestStatus.CANCELLED
    slot = db.get(LaundrySlot, request.slot_id)
    if slot and slot.status == "FULL":
        slot.status = "AVAILABLE"
    db.commit()
    return ok(None, message="Booking cancelled.")


# ---------------------------------------------------------- my complaints
@router.get("/complaints", summary="My complaints")
def my_complaints(db: DbSession, me: CurrentCustomer) -> dict:
    rows = db.scalars(
        select(Complaint).where(Complaint.resident_id == me.id)
        .order_by(Complaint.created_at.desc())).all()
    return ok([
        {"id": str(c.id), "ticket_number": c.ticket_number, "category": c.category,
         "subject": c.subject, "description": c.description, "priority": c.priority,
         "status": c.status, "resolution": c.resolution,
         "created_at": c.created_at.isoformat(),
         "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
         # Internal notes are filtered out here, not in the browser.
         "updates": [
             {"author": u.author_name, "message": u.message,
              "created_at": u.created_at.isoformat()}
             for u in sorted(c.updates, key=lambda x: x.created_at)
             if not u.is_internal]}
        for c in rows])


@router.post("/complaints", status_code=status.HTTP_201_CREATED,
             summary="Raise a complaint")
def raise_complaint(body: ComplaintCreate, db: DbSession, me: CurrentCustomer) -> dict:
    count = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.organization_id == me.organization_id)) or 0
    complaint = Complaint(
        organization_id=me.organization_id, branch_id=me.branch_id,
        resident_id=me.id, room_id=me.room_id,
        ticket_number=f"CMP-{count + 1:05d}",
        category=body.category, subject=body.subject, description=body.description,
        priority=body.priority or TicketPriority.MEDIUM, status=ComplaintStatus.OPEN)
    db.add(complaint)
    db.flush()
    if body.description:
        db.add(ComplaintUpdate(
            organization_id=me.organization_id, complaint_id=complaint.id,
            author_resident_id=me.id, author_name=me.full_name,
            message=body.description, status_after=ComplaintStatus.OPEN))
    NotificationService(db).to_permission_holders(
        me.organization_id, "complaints.manage", "COMPLAINT_UPDATED",
        f"New {complaint.priority.lower()} complaint",
        f"{complaint.ticket_number}: {complaint.subject}",
        branch_id=me.branch_id, entity_type="complaint", entity_id=complaint.id)
    db.commit()
    return ok({"id": str(complaint.id), "ticket_number": complaint.ticket_number},
              message=f"Complaint {complaint.ticket_number} raised.")


# ------------------------------------------------------------- my queries
@router.get("/queries", summary="My queries")
def my_queries(db: DbSession, me: CurrentCustomer) -> dict:
    rows = db.scalars(
        select(SupportQuery).where(SupportQuery.resident_id == me.id)
        .order_by(SupportQuery.created_at.desc())).all()
    return ok([
        {"id": str(q.id), "ticket_number": q.ticket_number, "subject": q.subject,
         "category": q.category, "status": q.status,
         "created_at": q.created_at.isoformat(),
         "messages": [
             {"author": m.author_name, "is_staff": m.is_staff, "message": m.message,
              "created_at": m.created_at.isoformat()}
             for m in sorted(q.messages, key=lambda x: x.created_at)]}
        for q in rows])


@router.post("/queries", status_code=status.HTTP_201_CREATED, summary="Ask a question")
def ask(body: QueryCreate, db: DbSession, me: CurrentCustomer) -> dict:
    count = db.scalar(select(func.count(SupportQuery.id)).where(
        SupportQuery.organization_id == me.organization_id)) or 0
    query = SupportQuery(
        organization_id=me.organization_id, branch_id=me.branch_id,
        resident_id=me.id, ticket_number=f"QRY-{count + 1:05d}",
        category=body.category, subject=body.subject, status=QueryStatus.OPEN)
    db.add(query)
    db.flush()
    db.add(QueryMessage(
        organization_id=me.organization_id, query_id=query.id,
        author_resident_id=me.id, author_name=me.full_name, is_staff=False,
        message=body.message or body.subject))
    db.commit()
    return ok({"id": str(query.id), "ticket_number": query.ticket_number},
              message="Query sent.")


@router.post("/queries/{query_id}/reply", summary="Reply on my query")
def reply(query_id: uuid.UUID, body: QueryReply, db: DbSession,
          me: CurrentCustomer) -> dict:
    query = db.scalars(select(SupportQuery).where(
        SupportQuery.id == query_id, SupportQuery.resident_id == me.id)).first()
    if query is None:
        raise NotFoundError("Query not found.")
    db.add(QueryMessage(
        organization_id=me.organization_id, query_id=query.id,
        author_resident_id=me.id, author_name=me.full_name, is_staff=False,
        message=body.message))
    query.status = QueryStatus.OPEN
    db.commit()
    return ok(None, message="Reply sent.")


# ------------------------------------------------------ visitors and passes
@router.get("/visitors", summary="My visitor requests")
def my_visitors(db: DbSession, me: CurrentCustomer) -> dict:
    rows = db.scalars(
        select(Visitor).where(Visitor.resident_id == me.id)
        .order_by(Visitor.created_at.desc())).all()
    return ok([
        {"id": str(v.id), "name": v.name, "phone": v.phone, "relation": v.relation,
         "purpose": v.purpose, "status": v.status,
         "expected_at": v.expected_at.isoformat() if v.expected_at else None,
         "entry_at": v.entry_at.isoformat() if v.entry_at else None,
         "exit_at": v.exit_at.isoformat() if v.exit_at else None,
         "created_at": v.created_at.isoformat()}
        for v in rows])


@router.post("/visitors", status_code=status.HTTP_201_CREATED,
             summary="Request a visitor")
def request_visitor(body: VisitorCreate, db: DbSession, me: CurrentCustomer) -> dict:
    settings = _settings(db, me.organization_id)
    visitor = Visitor(
        organization_id=me.organization_id, branch_id=me.branch_id,
        resident_id=me.id, name=body.name, phone=body.phone, relation=body.relation,
        purpose=body.purpose, expected_at=body.expected_at,
        status=(VisitorStatus.PENDING if settings.visitor_approval_required
                else VisitorStatus.APPROVED))
    db.add(visitor)
    db.flush()
    NotificationService(db).to_permission_holders(
        me.organization_id, "visitors.approve", "VISITOR_REQUEST",
        "Visitor awaiting approval", f"{visitor.name} to see {me.full_name}.",
        branch_id=me.branch_id, entity_type="visitor", entity_id=visitor.id)
    db.commit()
    return ok({"id": str(visitor.id), "status": visitor.status},
              message="Visitor request sent.")


@router.get("/gate-passes", summary="My gate passes")
def my_gate_passes(db: DbSession, me: CurrentCustomer) -> dict:
    rows = db.scalars(
        select(GatePass).where(GatePass.resident_id == me.id)
        .order_by(GatePass.created_at.desc())).all()
    return ok([
        {"id": str(g.id), "pass_number": g.pass_number, "reason": g.reason,
         "destination": g.destination, "status": g.status,
         "is_emergency": g.is_emergency,
         "from_at": g.from_at.isoformat(), "to_at": g.to_at.isoformat(),
         "decision_note": g.decision_note,
         "created_at": g.created_at.isoformat()}
        for g in rows])


@router.post("/gate-passes", status_code=status.HTTP_201_CREATED,
             summary="Request a gate pass")
def request_gate_pass(body: GatePassCreate, db: DbSession, me: CurrentCustomer) -> dict:
    if body.to_at <= body.from_at:
        raise ConflictError("The return time must be after the departure time.")
    settings = _settings(db, me.organization_id)
    count = db.scalar(select(func.count(GatePass.id)).where(
        GatePass.organization_id == me.organization_id)) or 0
    gate_pass = GatePass(
        organization_id=me.organization_id, branch_id=me.branch_id,
        resident_id=me.id, pass_number=f"GP-{count + 1:05d}",
        reason=body.reason, destination=body.destination,
        from_at=body.from_at, to_at=body.to_at, is_emergency=body.is_emergency,
        status=(GatePassStatus.PENDING if settings.gate_pass_approval_required
                else GatePassStatus.APPROVED))
    db.add(gate_pass)
    db.flush()
    NotificationService(db).to_permission_holders(
        me.organization_id, "gatepass.approve", "GATE_PASS",
        "Gate pass awaiting approval", f"{me.full_name}: {gate_pass.reason}",
        branch_id=me.branch_id, entity_type="gate_pass", entity_id=gate_pass.id)
    db.commit()
    return ok({"id": str(gate_pass.id), "pass_number": gate_pass.pass_number,
               "status": gate_pass.status}, message="Gate pass requested.")


# ------------------------------------------------------------ announcements
@router.get("/announcements", summary="Announcements for me")
def my_announcements(db: DbSession, me: CurrentCustomer) -> dict:
    today = date.today()
    rows = db.scalars(
        select(Announcement).where(
            Announcement.organization_id == me.organization_id,
            Announcement.status == PublishStatus.PUBLISHED,
            Announcement.audience.in_([AnnouncementAudience.ALL,
                                       AnnouncementAudience.RESIDENTS,
                                       AnnouncementAudience.BRANCH]),
            or_(Announcement.branch_id.is_(None), Announcement.branch_id == me.branch_id),
            or_(Announcement.ends_on.is_(None), Announcement.ends_on >= today))
        .order_by(Announcement.created_at.desc())).all()
    return ok([
        {"id": str(a.id), "title": a.title, "message": a.message,
         "priority": a.priority, "starts_on": a.starts_on.isoformat() if a.starts_on else None,
         "created_at": a.created_at.isoformat()}
        for a in rows])
