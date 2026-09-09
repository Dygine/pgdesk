"""Attendance, the QR gate, visitors, gate passes, food and laundry."""
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import CurrentScope, DbSession, require, require_tenant
from app.core.responses import ok, paginated
from app.models import (
    Attendance, FoodMenu, GateLog, GatePass, LaundryRequest, LaundrySlot, Visitor,
)
from app.schemas.operations import (
    ApprovalDecision, AttendanceMark, GatePassCreate, MealMark, MenuUpsert,
    ScanRequest, SlotBooking, SlotCreate, StatusChange, VisitorCreate,
)
from app.services.operations_service import OperationsService

router = APIRouter(tags=["operations"])
Tenant = Annotated[CurrentScope, Depends(require_tenant)]


def _svc(db, scope) -> OperationsService:
    return OperationsService(db, scope)


def _attendance(a: Attendance) -> dict:
    return {
        "id": str(a.id), "subject": a.subject, "on_date": a.on_date.isoformat(),
        "status": a.status, "source": a.source,
        "resident_id": str(a.resident_id) if a.resident_id else None,
        "user_id": str(a.user_id) if a.user_id else None,
        "person": (a.resident.full_name if a.resident
                   else a.user.name if a.user else None),
        "check_in_at": a.check_in_at.isoformat() if a.check_in_at else None,
        "check_out_at": a.check_out_at.isoformat() if a.check_out_at else None,
        "notes": a.notes, "branch_id": str(a.branch_id),
    }


def _visitor(v: Visitor) -> dict:
    return {
        "id": str(v.id), "name": v.name, "phone": v.phone, "relation": v.relation,
        "purpose": v.purpose, "status": v.status,
        "resident_id": str(v.resident_id),
        "resident": v.resident.full_name if v.resident else None,
        "branch_id": str(v.branch_id),
        "expected_at": v.expected_at.isoformat() if v.expected_at else None,
        "entry_at": v.entry_at.isoformat() if v.entry_at else None,
        "exit_at": v.exit_at.isoformat() if v.exit_at else None,
        "id_proof_reference": v.id_proof_reference, "notes": v.notes,
        "created_at": v.created_at.isoformat(),
    }


def _gate_pass(g: GatePass) -> dict:
    return {
        "id": str(g.id), "pass_number": g.pass_number, "reason": g.reason,
        "destination": g.destination, "status": g.status,
        "is_emergency": g.is_emergency,
        "resident_id": str(g.resident_id),
        "resident": g.resident.full_name if g.resident else None,
        "branch_id": str(g.branch_id),
        "from_at": g.from_at.isoformat(), "to_at": g.to_at.isoformat(),
        "approved_at": g.approved_at.isoformat() if g.approved_at else None,
        "decision_note": g.decision_note,
        "created_at": g.created_at.isoformat(),
    }


def _laundry(r: LaundryRequest) -> dict:
    return {
        "id": str(r.id), "status": r.status, "item_count": r.item_count,
        "notes": r.notes, "resident_id": str(r.resident_id),
        "resident": r.resident.full_name if r.resident else None,
        "slot_id": str(r.slot_id), "branch_id": str(r.branch_id),
        "slot": ({"on_date": r.slot.on_date.isoformat(),
                  "start_time": r.slot.start_time.isoformat(),
                  "end_time": r.slot.end_time.isoformat()} if r.slot else None),
        "created_at": r.created_at.isoformat(),
    }


# --------------------------------------------------------------- attendance
@router.get("/attendance", summary="Attendance register")
def list_attendance(db: DbSession, scope: Tenant,
                    _: None = Depends(require("attendance.view")),
                    on_date: date | None = None,
                    subject: str | None = None,
                    branch_id: uuid.UUID | None = None,
                    resident_id: uuid.UUID | None = None,
                    status_filter: str | None = Query(default=None, alias="status"),
                    page: int = Query(default=1, ge=1),
                    page_size: int = Query(default=100, ge=1, le=500)) -> dict:
    rows, total = _svc(db, scope).list_attendance(
        on_date=on_date, subject=subject, branch_id=branch_id,
        resident_id=resident_id, status=status_filter, page=page, page_size=page_size)
    return paginated([_attendance(a) for a in rows], page, page_size, total)


@router.post("/attendance", summary="Mark attendance")
def mark_attendance(body: AttendanceMark, db: DbSession, scope: Tenant,
                    _: None = Depends(require("attendance.manage", "attendance.mark"))) -> dict:
    """Upserts by person and day, so a second submission corrects rather than duplicates."""
    row = _svc(db, scope).mark_attendance(body.model_dump())
    db.commit()
    return ok(_attendance(row), message="Attendance recorded.")


# ------------------------------------------------------------------ QR gate
@router.post("/scan", summary="Scan a resident QR at the gate")
def scan(body: ScanRequest, db: DbSession, scope: Tenant,
         _: None = Depends(require("scan.manage", "scan.view"))) -> dict:
    """
    Always answers 200 with a result, including refusals.

    A guard needs to see *which* resident was refused and why; an error envelope
    with no resident attached is useless at a gate. Every outcome is written to
    the gate log either way.
    """
    result = _svc(db, scope).scan(
        body.token, direction=body.direction, gate=body.gate)
    db.commit()
    return ok(result, message=result["message"])


@router.get("/gate-logs", summary="Entry and exit log")
def gate_logs(db: DbSession, scope: Tenant,
              _: None = Depends(require("scan.view")),
              branch_id: uuid.UUID | None = None,
              resident_id: uuid.UUID | None = None,
              on_date: date | None = None,
              direction: str | None = None,
              page: int = Query(default=1, ge=1),
              page_size: int = Query(default=50, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_gate_logs(
        branch_id=branch_id, resident_id=resident_id, on_date=on_date,
        direction=direction, page=page, page_size=page_size)
    return paginated([
        {"id": str(g.id), "direction": g.direction,
         "occurred_at": g.occurred_at.isoformat(), "gate": g.gate,
         "source": g.source, "allowed": g.allowed, "reason": g.reason,
         "resident_id": str(g.resident_id) if g.resident_id else None,
         "resident": g.resident.full_name if g.resident else None,
         "branch_id": str(g.branch_id)}
        for g in rows], page, page_size, total)


# ----------------------------------------------------------------- visitors
@router.get("/visitors", summary="List visitors")
def list_visitors(db: DbSession, scope: Tenant,
                  _: None = Depends(require("visitors.view")),
                  status_filter: str | None = Query(default=None, alias="status"),
                  branch_id: uuid.UUID | None = None,
                  resident_id: uuid.UUID | None = None,
                  search: str | None = None,
                  page: int = Query(default=1, ge=1),
                  page_size: int = Query(default=25, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_visitors(
        status=status_filter, branch_id=branch_id, resident_id=resident_id,
        search=search, page=page, page_size=page_size)
    return paginated([_visitor(v) for v in rows], page, page_size, total)


@router.post("/visitors", status_code=status.HTTP_201_CREATED, summary="Log a visitor")
def create_visitor(body: VisitorCreate, db: DbSession, scope: Tenant,
                   _: None = Depends(require("visitors.create", "visitors.manage"))) -> dict:
    visitor = _svc(db, scope).create_visitor(body.model_dump())
    db.commit()
    return ok(_visitor(visitor), message=f"{visitor.name} logged.")


@router.post("/visitors/{visitor_id}/decision", summary="Approve or reject a visitor")
def decide_visitor(visitor_id: uuid.UUID, body: ApprovalDecision, db: DbSession,
                   scope: Tenant, _: None = Depends(require("visitors.approve"))) -> dict:
    visitor = _svc(db, scope).decide_visitor(
        visitor_id, approved=body.approved, note=body.note)
    db.commit()
    return ok(_visitor(visitor), message=f"Visitor {visitor.status.lower()}.")


@router.post("/visitors/{visitor_id}/entry", summary="Record visitor entry")
def visitor_entry(visitor_id: uuid.UUID, db: DbSession, scope: Tenant,
                  _: None = Depends(require("visitors.manage"))) -> dict:
    """Refused unless the visit was approved - which is the point of approval."""
    visitor = _svc(db, scope).visitor_movement(visitor_id, entering=True)
    db.commit()
    return ok(_visitor(visitor), message="Entry recorded.")


@router.post("/visitors/{visitor_id}/exit", summary="Record visitor exit")
def visitor_exit(visitor_id: uuid.UUID, db: DbSession, scope: Tenant,
                 _: None = Depends(require("visitors.manage"))) -> dict:
    visitor = _svc(db, scope).visitor_movement(visitor_id, entering=False)
    db.commit()
    return ok(_visitor(visitor), message="Exit recorded.")


# -------------------------------------------------------------- gate passes
@router.get("/gate-passes", summary="List gate passes")
def list_gate_passes(db: DbSession, scope: Tenant,
                     _: None = Depends(require("gatepass.view")),
                     status_filter: str | None = Query(default=None, alias="status"),
                     branch_id: uuid.UUID | None = None,
                     resident_id: uuid.UUID | None = None,
                     page: int = Query(default=1, ge=1),
                     page_size: int = Query(default=25, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_gate_passes(
        status=status_filter, branch_id=branch_id, resident_id=resident_id,
        page=page, page_size=page_size)
    return paginated([_gate_pass(g) for g in rows], page, page_size, total)


@router.post("/gate-passes", status_code=status.HTTP_201_CREATED,
             summary="Raise a gate pass")
def create_gate_pass(body: GatePassCreate, db: DbSession, scope: Tenant,
                     _: None = Depends(require("gatepass.create", "gatepass.manage"))) -> dict:
    gate_pass = _svc(db, scope).create_gate_pass(body.model_dump())
    db.commit()
    return ok(_gate_pass(gate_pass), message=f"Gate pass {gate_pass.pass_number} raised.")


@router.post("/gate-passes/{pass_id}/decision", summary="Approve or reject a gate pass")
def decide_gate_pass(pass_id: uuid.UUID, body: ApprovalDecision, db: DbSession,
                     scope: Tenant, _: None = Depends(require("gatepass.approve"))) -> dict:
    gate_pass = _svc(db, scope).decide_gate_pass(
        pass_id, approved=body.approved, note=body.note)
    db.commit()
    return ok(_gate_pass(gate_pass), message=f"Pass {gate_pass.status.lower()}.")


@router.patch("/gate-passes/{pass_id}/status", summary="Mark departure or return")
def set_gate_pass_status(pass_id: uuid.UUID, body: StatusChange, db: DbSession,
                         scope: Tenant,
                         _: None = Depends(require("gatepass.manage"))) -> dict:
    """Security can only act on an approved pass."""
    gate_pass = _svc(db, scope).set_gate_pass_status(pass_id, body.status)
    db.commit()
    return ok(_gate_pass(gate_pass), message="Gate pass updated.")


# ---------------------------------------------------------------------- food
@router.get("/food/menus", summary="Food menu")
def list_menus(db: DbSession, scope: Tenant,
               _: None = Depends(require("food.view")),
               branch_id: uuid.UUID | None = None,
               from_date: date | None = None, to_date: date | None = None) -> dict:
    rows = _svc(db, scope).list_menus(
        branch_id=branch_id, from_date=from_date, to_date=to_date)
    return ok([
        {"id": str(m.id), "branch_id": str(m.branch_id),
         "on_date": m.on_date.isoformat(), "meal": m.meal, "items": m.items,
         "calories": m.calories, "notes": m.notes,
         "serve_from": m.serve_from.isoformat() if m.serve_from else None,
         "serve_to": m.serve_to.isoformat() if m.serve_to else None}
        for m in rows])


@router.put("/food/menus", summary="Set a menu for a meal")
def upsert_menu(body: MenuUpsert, db: DbSession, scope: Tenant,
                _: None = Depends(require("food.manage"))) -> dict:
    """Upsert by branch, day and meal - editing today's lunch twice is normal."""
    row = _svc(db, scope).upsert_menu(body.model_dump())
    db.commit()
    return ok({"id": str(row.id), "on_date": row.on_date.isoformat(),
               "meal": row.meal, "items": row.items}, message="Menu saved.")


@router.post("/food/meals", summary="Mark a meal")
def mark_meal(body: MealMark, db: DbSession, scope: Tenant,
              _: None = Depends(require("food.mark", "food.manage"))) -> dict:
    row = _svc(db, scope).set_meal(body.model_dump())
    db.commit()
    return ok({"id": str(row.id), "meal": row.meal, "status": row.status,
               "on_date": row.on_date.isoformat()}, message="Meal recorded.")


@router.get("/food/counts", summary="Meal counts for a day")
def meal_counts(db: DbSession, scope: Tenant,
                _: None = Depends(require("food.view")),
                on_date: date | None = None,
                branch_id: uuid.UUID | None = None) -> dict:
    """What the kitchen needs to cook, and what was actually eaten."""
    return ok(_svc(db, scope).meal_counts(on_date=on_date, branch_id=branch_id))


# ------------------------------------------------------------------ laundry
@router.get("/laundry/slots", summary="Laundry slots")
def list_slots(db: DbSession, scope: Tenant,
               _: None = Depends(require("laundry.view")),
               branch_id: uuid.UUID | None = None,
               from_date: date | None = None, to_date: date | None = None) -> dict:
    rows = _svc(db, scope).list_slots(
        branch_id=branch_id, from_date=from_date, to_date=to_date)
    return ok([
        {"id": str(s.id), "branch_id": str(s.branch_id),
         "on_date": s.on_date.isoformat(),
         "start_time": s.start_time.isoformat(), "end_time": s.end_time.isoformat(),
         "capacity": s.capacity, "booked": s.booked,
         "remaining": max(s.capacity - s.booked, 0), "status": s.status}
        for s in rows])


@router.post("/laundry/slots", status_code=status.HTTP_201_CREATED,
             summary="Create a laundry slot")
def create_slot(body: SlotCreate, db: DbSession, scope: Tenant,
                _: None = Depends(require("laundry.manage"))) -> dict:
    slot = _svc(db, scope).create_slot(body.model_dump())
    db.commit()
    return ok({"id": str(slot.id), "on_date": slot.on_date.isoformat()},
              message="Slot created.")


@router.post("/laundry/bookings", status_code=status.HTTP_201_CREATED,
             summary="Book a laundry slot")
def book_slot(body: SlotBooking, db: DbSession, scope: Tenant,
              _: None = Depends(require("laundry.book", "laundry.manage"))) -> dict:
    """Locks the slot, so capacity cannot be oversold by simultaneous bookings."""
    data = body.model_dump()
    request = _svc(db, scope).book_slot(data)
    db.commit()
    return ok(_laundry(request), message="Slot booked.")


@router.get("/laundry/requests", summary="Laundry requests")
def list_laundry(db: DbSession, scope: Tenant,
                 _: None = Depends(require("laundry.view")),
                 status_filter: str | None = Query(default=None, alias="status"),
                 branch_id: uuid.UUID | None = None,
                 resident_id: uuid.UUID | None = None,
                 page: int = Query(default=1, ge=1),
                 page_size: int = Query(default=25, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_laundry(
        status=status_filter, branch_id=branch_id, resident_id=resident_id,
        page=page, page_size=page_size)
    return paginated([_laundry(r) for r in rows], page, page_size, total)


@router.patch("/laundry/requests/{request_id}", summary="Advance a laundry request")
def set_laundry_status(request_id: uuid.UUID, body: StatusChange, db: DbSession,
                       scope: Tenant, _: None = Depends(require("laundry.manage"))) -> dict:
    request = _svc(db, scope).set_laundry_status(request_id, body.status)
    db.commit()
    return ok(_laundry(request), message=f"Marked {body.status.lower()}.")
