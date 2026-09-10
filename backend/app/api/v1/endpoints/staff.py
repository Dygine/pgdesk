"""The workforce list and salaries. Logins live under /users, not here."""
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import CurrentScope, DbSession, require, require_tenant
from app.core.responses import ok
from app.models import Branch, StaffMember
from app.models.enums import StaffStatus
from app.schemas.operations import SalaryPayment, StaffCreate, StaffUpdate
from app.services.staff_service import DESIGNATIONS, StaffService, month_start

router = APIRouter(tags=["staff"])
Tenant = Annotated[CurrentScope, Depends(require_tenant)]


def _staff(db, m: StaffMember, paid=None) -> dict:
    branch = db.get(Branch, m.branch_id)
    return {
        "id": str(m.id), "full_name": m.full_name, "phone": m.phone,
        "designation": m.designation, "shift": m.shift,
        "monthly_salary": float(m.monthly_salary or 0), "status": m.status,
        "branch_id": str(m.branch_id), "branch": branch.name if branch else None,
        "joining_date": m.joining_date.isoformat() if m.joining_date else None,
        "left_on": m.left_on.isoformat() if m.left_on else None,
        "user_id": str(m.user_id) if m.user_id else None,
        "login_email": m.user.email if m.user else None,
        "id_proof_reference": m.id_proof_reference, "address": m.address,
        "emergency_contact_name": m.emergency_contact_name,
        "emergency_contact_phone": m.emergency_contact_phone, "notes": m.notes,
        "paid_this_period": paid is not None,
        "paid_expense_number": paid.expense_number if paid is not None else None,
    }


@router.get("/staff", summary="The workforce list, with this month's salary status")
def list_staff(db: DbSession, scope: Tenant, _: None = Depends(require("staff.view")),
               search: str | None = None,
               status_filter: str | None = Query(default=None, alias="status"),
               branch_id: uuid.UUID | None = None, designation: str | None = None,
               period: date | None = None) -> dict:
    svc = StaffService(db, scope)
    period = month_start(period or date.today())
    rows = svc.list(search=search, status=status_filter, branch_id=branch_id,
                    designation=designation)
    paid = svc.salaries_for([r.id for r in rows], period)
    active = [r for r in rows if r.status != StaffStatus.LEFT]
    return ok({
        "items": [_staff(db, r, paid.get(r.id)) for r in rows],
        "period": period.isoformat(), "designations": DESIGNATIONS,
        "summary": {
            "active": len([r for r in rows if r.status == StaffStatus.ACTIVE]),
            "on_leave": len([r for r in rows if r.status == StaffStatus.ON_LEAVE]),
            "monthly_payroll": round(sum(float(r.monthly_salary or 0) for r in active), 2),
            "paid_this_period": round(sum(float(e.amount) for e in paid.values()), 2),
            "unpaid_count": len([r for r in active if r.id not in paid
                                 and float(r.monthly_salary or 0) > 0]),
        },
    })


@router.get("/staff/{staff_id}", summary="One staff member with salary history")
def get_staff(staff_id: uuid.UUID, db: DbSession, scope: Tenant,
              _: None = Depends(require("staff.view"))) -> dict:
    svc = StaffService(db, scope)
    member = svc.get(staff_id)
    payload = _staff(db, member)
    payload["salaries"] = [
        {"id": str(e.id), "expense_number": e.expense_number, "amount": float(e.amount),
         "period": e.salary_period.isoformat() if e.salary_period else None,
         "paid_on": e.spent_on.isoformat(), "payment_method": e.payment_method,
         "reference": e.reference}
        for e in svc.salary_history(staff_id)]
    return ok(payload)


@router.post("/staff", status_code=status.HTTP_201_CREATED, summary="Add a staff member")
def create_staff(body: StaffCreate, db: DbSession, scope: Tenant,
                 _: None = Depends(require("staff.create"))) -> dict:
    member = StaffService(db, scope).create(body.model_dump())
    db.commit()
    db.refresh(member)
    return ok(_staff(db, member), message=f"{member.full_name} added.")


@router.patch("/staff/{staff_id}", summary="Edit a staff member")
def update_staff(staff_id: uuid.UUID, body: StaffUpdate, db: DbSession, scope: Tenant,
                 _: None = Depends(require("staff.edit", "staff.deactivate"))) -> dict:
    member = StaffService(db, scope).update(staff_id, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(member)
    return ok(_staff(db, member), message=f"{member.full_name} updated.")


@router.post("/staff/{staff_id}/salary", status_code=status.HTTP_201_CREATED,
             summary="Record a month's salary as paid")
def pay_salary(staff_id: uuid.UUID, body: SalaryPayment, db: DbSession, scope: Tenant,
               _v: None = Depends(require("staff.view", "staff.edit")),
               _m: None = Depends(require("expenses.create"))) -> dict:
    """Writes an ordinary Salary expense, so it shows in Expenses and the P&L."""
    expense = StaffService(db, scope).pay_salary(
        staff_id, period=body.period, amount=body.amount, paid_on=body.paid_on,
        payment_method=body.payment_method, reference=body.reference, notes=body.notes)
    db.commit()
    return ok({"id": str(expense.id), "expense_number": expense.expense_number,
               "amount": float(expense.amount),
               "period": expense.salary_period.isoformat()},
              message=f"Salary recorded as {expense.expense_number}.")
