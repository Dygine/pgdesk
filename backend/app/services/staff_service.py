"""
The workforce list and salaries.

A staff member is not a login. The Users screen manages who can sign in; this
manages who works here - including the cook and the cleaner who never will.
Paying a salary writes an ordinary expense (category "Salary"), so it appears in
Expenses and the P&L with no second ledger to reconcile, and is tagged with the
staff member and month so the same month cannot be paid twice by accident.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentScope
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models import Expense, StaffMember, User
from app.models.enums import AuditAction, StaffStatus
from app.services.audit import AuditService

EDITABLE = (
    "full_name", "phone", "designation", "shift", "monthly_salary", "joining_date",
    "id_proof_reference", "address", "emergency_contact_name",
    "emergency_contact_phone", "notes",
)
DESIGNATIONS = ["Manager", "Warden", "Cook", "Kitchen helper", "Cleaner",
                "Security guard", "Maintenance", "Laundry", "Driver", "Other"]


def month_start(d: date) -> date:
    return d.replace(day=1)


class StaffService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope
        self.audit = AuditService(db)

    @property
    def org_id(self) -> uuid.UUID:
        return self.scope.organization_id

    def _scoped(self):
        return select(StaffMember).where(
            StaffMember.organization_id == self.org_id,
            StaffMember.branch_id.in_(self.scope.branch_ids or [uuid.UUID(int=0)]))

    def _assert_branch(self, branch_id: uuid.UUID) -> None:
        if not self.scope.owns_branch(branch_id):
            raise PermissionDeniedError(
                "Branch access denied. You are not assigned to this branch.")

    def _check_user(self, user_id: uuid.UUID | None) -> None:
        if user_id is None:
            return
        user = self.db.scalars(select(User).where(
            User.id == user_id, User.organization_id == self.org_id)).first()
        if user is None:
            raise NotFoundError("That login does not exist.")

    def get(self, staff_id: uuid.UUID) -> StaffMember:
        row = self.db.scalars(self._scoped().where(StaffMember.id == staff_id)).first()
        if row is None:
            raise NotFoundError("Staff member not found.")
        return row

    def list(self, *, search=None, status=None, branch_id=None, designation=None):
        stmt = self._scoped()
        if branch_id:
            self._assert_branch(branch_id)
            stmt = stmt.where(StaffMember.branch_id == branch_id)
        if status and status != "all":
            stmt = stmt.where(StaffMember.status == status)
        if designation and designation != "all":
            stmt = stmt.where(StaffMember.designation == designation)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(StaffMember.full_name.ilike(like),
                                  StaffMember.phone.ilike(like),
                                  StaffMember.designation.ilike(like)))
        return list(self.db.scalars(stmt.order_by(StaffMember.full_name)).all())

    def salaries_for(self, staff_ids: list[uuid.UUID], period: date) -> dict:
        """{staff_id: expense} for salaries already recorded against `period`."""
        if not staff_ids:
            return {}
        rows = self.db.scalars(select(Expense).where(
            Expense.organization_id == self.org_id,
            Expense.staff_member_id.in_(staff_ids),
            Expense.salary_period == month_start(period))).all()
        return {r.staff_member_id: r for r in rows}

    def salary_history(self, staff_id: uuid.UUID, limit: int = 12) -> list[Expense]:
        member = self.get(staff_id)
        return list(self.db.scalars(
            select(Expense).where(Expense.organization_id == self.org_id,
                                  Expense.staff_member_id == member.id)
            .order_by(Expense.salary_period.desc(), Expense.spent_on.desc())
            .limit(limit)).all())

    def create(self, data: dict) -> StaffMember:
        self._assert_branch(data["branch_id"])
        self._check_user(data.get("user_id"))
        name = (data.get("full_name") or "").strip()
        if not name:
            raise ConflictError("Enter the staff member's name.")
        row = StaffMember(
            organization_id=self.org_id, branch_id=data["branch_id"],
            user_id=data.get("user_id"), full_name=name,
            designation=(data.get("designation") or "Other").strip(),
            monthly_salary=data.get("monthly_salary") or 0,
            joining_date=data.get("joining_date") or date.today(),
            status=StaffStatus.ACTIVE)
        for field in EDITABLE:
            if field not in ("full_name", "designation", "monthly_salary", "joining_date") \
                    and data.get(field) is not None:
                setattr(row, field, data[field])
        self.db.add(row)
        self.db.flush()
        self.audit.record(
            scope=self.scope, module="Staff", action=AuditAction.CREATE,
            description=f"Added {row.full_name} ({row.designation})",
            entity_type="staff", entity_id=row.id, branch_id=row.branch_id)
        return row

    def update(self, staff_id: uuid.UUID, data: dict) -> StaffMember:
        row = self.get(staff_id)
        for field in EDITABLE:
            if field in data and data[field] is not None:
                value = data[field].strip() if isinstance(data[field], str) else data[field]
                setattr(row, field, value)
        if data.get("branch_id") and data["branch_id"] != row.branch_id:
            self._assert_branch(data["branch_id"])
            row.branch_id = data["branch_id"]
        if "user_id" in data:
            self._check_user(data["user_id"])
            row.user_id = data["user_id"]
        if data.get("status") and data["status"] != row.status:
            row.status = data["status"]
            if row.status == StaffStatus.LEFT:
                row.left_on = data.get("left_on") or date.today()
            else:
                row.left_on = None
        if not (row.full_name or "").strip():
            raise ConflictError("A staff member needs a name.")
        self.audit.record(
            scope=self.scope, module="Staff", action=AuditAction.UPDATE,
            description=f"Updated {row.full_name}",
            entity_type="staff", entity_id=row.id, branch_id=row.branch_id)
        return row

    def pay_salary(self, staff_id: uuid.UUID, *, period: date, amount: float | None = None,
                   paid_on: date | None = None, payment_method: str | None = None,
                   reference: str | None = None, notes: str | None = None) -> Expense:
        from app.services.support_service import SupportService   # cycle-free at call time

        member = self.get(staff_id)
        period = month_start(period)
        existing = self.db.scalars(select(Expense).where(
            Expense.organization_id == self.org_id,
            Expense.staff_member_id == member.id,
            Expense.salary_period == period)).first()
        if existing:
            raise ConflictError(
                f"{member.full_name}'s salary for {period:%B %Y} is already recorded "
                f"({existing.expense_number}).")

        value = round(float(amount if amount is not None else member.monthly_salary or 0), 2)
        if value <= 0:
            raise ConflictError(
                "Enter the amount paid - this staff member has no monthly salary set.")

        description = f"Salary - {period:%B %Y} ({member.designation})"
        if notes:
            description += f". {notes.strip()}"
        expense = SupportService(self.db, self.scope).create_expense({
            "branch_id": member.branch_id, "category": "Salary", "amount": value,
            "spent_on": paid_on or date.today(), "vendor": member.full_name,
            "payment_method": payment_method, "reference": reference,
            "description": description,
        })
        expense.staff_member_id = member.id
        expense.salary_period = period
        self.db.flush()
        return expense
