"""
Reporting.

Every figure here is computed by PostgreSQL, not by the browser. A report that
is assembled client-side is limited to whatever page of rows happened to be
fetched, which is how "total revenue" quietly becomes "revenue on page 1".

`REPORTS` is a registry: each entry knows how to produce rows and columns, so
the list endpoint, the detail endpoint and the CSV export all share one
definition and cannot drift apart.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentScope
from app.core.exceptions import NotFoundError
from app.models import (
    Asset, Attendance, Bed, Branch, Complaint, Customer, Expense, GatePass,
    InventoryItem, Invoice, LaundryRequest, MealAttendance, Payment, Room, Visitor,
)
from app.models.enums import (
    BedStatus, ComplaintStatus, CustomerStatus, InvoiceStatus, PaymentStatus,
)


class ReportService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope

    @property
    def org_id(self) -> uuid.UUID:
        return self.scope.organization_id

    def _branches(self, branch_id: uuid.UUID | None) -> list[uuid.UUID]:
        if branch_id:
            return [branch_id] if self.scope.owns_branch(branch_id) else []
        return list(self.scope.branch_ids)

    def _where(self, model, branch_ids):
        return [model.organization_id == self.org_id,
                model.branch_id.in_(branch_ids or [uuid.UUID(int=0)])]

    # ------------------------------------------------------------ catalogue
    def catalogue(self) -> list[dict]:
        return [
            {"key": k, "label": v["label"], "group": v["group"],
             "description": v["description"]}
            for k, v in REPORTS.items()
        ]

    def run(self, key: str, *, branch_id=None, from_date=None, to_date=None) -> dict:
        spec = REPORTS.get(key)
        if spec is None:
            raise NotFoundError(f"No report called {key}.")
        branch_ids = self._branches(branch_id)
        to_date = to_date or date.today()
        from_date = from_date or (to_date - timedelta(days=30))
        rows = spec["run"](self, branch_ids, from_date, to_date)
        return {
            "key": key, "label": spec["label"], "columns": spec["columns"],
            "from_date": from_date.isoformat(), "to_date": to_date.isoformat(),
            "rows": rows, "row_count": len(rows),
        }

    def to_csv(self, report: dict) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer, fieldnames=[c["key"] for c in report["columns"]],
            extrasaction="ignore")
        writer.writerow({c["key"]: c["label"] for c in report["columns"]})
        writer.writerows(report["rows"])
        return buffer.getvalue()

    # ------------------------------------------------------- report bodies
    def occupancy(self, branch_ids, from_date, to_date):
        out = []
        for branch in self.db.scalars(
            select(Branch).where(Branch.organization_id == self.org_id,
                                 Branch.id.in_(branch_ids or [uuid.UUID(int=0)]))
            .order_by(Branch.name)).all():
            total = self.db.scalar(select(func.count(Bed.id)).where(
                Bed.branch_id == branch.id)) or 0
            counts = dict(self.db.execute(
                select(Bed.status, func.count(Bed.id))
                .where(Bed.branch_id == branch.id).group_by(Bed.status)).all())
            occupied = counts.get(BedStatus.OCCUPIED, 0)
            out.append({
                "branch": branch.name,
                "rooms": self.db.scalar(select(func.count(Room.id)).where(
                    Room.branch_id == branch.id)) or 0,
                "beds": total, "occupied": occupied,
                "available": counts.get(BedStatus.AVAILABLE, 0),
                "reserved": counts.get(BedStatus.RESERVED, 0),
                "out_of_service": (counts.get(BedStatus.MAINTENANCE, 0)
                                   + counts.get(BedStatus.BLOCKED, 0)),
                "occupancy_rate": round(occupied / total * 100, 1) if total else 0.0,
            })
        return out

    def residents(self, branch_ids, from_date, to_date):
        rows = self.db.scalars(
            select(Customer)
            .where(Customer.organization_id == self.org_id,
                   Customer.branch_id.in_(branch_ids or [uuid.UUID(int=0)]))
            .order_by(Customer.full_name)).all()
        branches = {b.id: b.name for b in self.db.scalars(select(Branch).where(
            Branch.organization_id == self.org_id)).all()}
        rooms = {r.id: r.room_number for r in self.db.scalars(select(Room).where(
            Room.organization_id == self.org_id)).all()}
        return [{
            "name": r.full_name, "phone": r.phone, "email": r.email or "",
            "branch": branches.get(r.branch_id, ""),
            "room": rooms.get(r.room_id, ""),
            "status": r.status,
            "joining_date": r.joining_date.isoformat() if r.joining_date else "",
            "monthly_rent": float(r.monthly_rent),
        } for r in rows]

    def rent_collection(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(Invoice.status, func.count(Invoice.id), func.sum(Invoice.total),
                   func.sum(Invoice.paid_amount), func.sum(Invoice.balance))
            .where(*self._where(Invoice, branch_ids),
                   Invoice.invoice_date.between(from_date, to_date))
            .group_by(Invoice.status)).all()
        return [{"status": s, "invoices": n, "billed": float(t or 0),
                 "collected": float(p or 0), "outstanding": float(b or 0)}
                for s, n, t, p, b in rows]

    def outstanding(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(Invoice, Customer)
            .join(Customer, Customer.id == Invoice.resident_id)
            .where(*self._where(Invoice, branch_ids),
                   Invoice.balance > 0,
                   Invoice.status != InvoiceStatus.CANCELLED)
            .order_by(Invoice.due_date)).all()
        return [{
            "invoice": i.invoice_number, "resident": c.full_name, "phone": c.phone,
            "due_date": i.due_date.isoformat(), "total": float(i.total),
            "paid": float(i.paid_amount), "balance": float(i.balance),
            "days_overdue": max((date.today() - i.due_date).days, 0),
            "status": i.status,
        } for i, c in rows]

    def payments(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(Payment, Customer)
            .join(Customer, Customer.id == Payment.resident_id)
            .where(*self._where(Payment, branch_ids),
                   Payment.payment_date.between(from_date, to_date))
            .order_by(Payment.payment_date.desc())).all()
        return [{
            "payment": p.payment_number, "date": p.payment_date.isoformat(),
            "resident": c.full_name, "amount": float(p.amount), "method": p.method,
            "status": p.status, "reference": p.reference or "",
        } for p, c in rows]

    def invoices(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(Invoice, Customer)
            .join(Customer, Customer.id == Invoice.resident_id)
            .where(*self._where(Invoice, branch_ids),
                   Invoice.invoice_date.between(from_date, to_date))
            .order_by(Invoice.invoice_date.desc())).all()
        return [{
            "invoice": i.invoice_number, "date": i.invoice_date.isoformat(),
            "resident": c.full_name, "total": float(i.total),
            "paid": float(i.paid_amount), "balance": float(i.balance),
            "status": i.status,
        } for i, c in rows]

    def expenses(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(Expense.category, func.count(Expense.id), func.sum(Expense.amount))
            .where(*self._where(Expense, branch_ids),
                   Expense.spent_on.between(from_date, to_date))
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())).all()
        return [{"category": c, "entries": n, "amount": float(a or 0)}
                for c, n, a in rows]

    def profit_summary(self, branch_ids, from_date, to_date):
        collected = float(self.db.scalar(
            select(func.sum(Payment.amount)).where(
                *self._where(Payment, branch_ids),
                Payment.status == PaymentStatus.VERIFIED,
                Payment.payment_date.between(from_date, to_date))) or 0)
        billed = float(self.db.scalar(
            select(func.sum(Invoice.total)).where(
                *self._where(Invoice, branch_ids),
                Invoice.status != InvoiceStatus.CANCELLED,
                Invoice.invoice_date.between(from_date, to_date))) or 0)
        spent = float(self.db.scalar(
            select(func.sum(Expense.amount)).where(
                *self._where(Expense, branch_ids),
                Expense.spent_on.between(from_date, to_date))) or 0)
        return [
            {"metric": "Billed", "amount": round(billed, 2)},
            {"metric": "Collected", "amount": round(collected, 2)},
            {"metric": "Uncollected", "amount": round(billed - collected, 2)},
            {"metric": "Expenses", "amount": round(spent, 2)},
            {"metric": "Net (collected − expenses)", "amount": round(collected - spent, 2)},
        ]

    def complaints(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(Complaint.category, Complaint.status, func.count(Complaint.id))
            .where(*self._where(Complaint, branch_ids),
                   func.date(Complaint.created_at).between(from_date, to_date))
            .group_by(Complaint.category, Complaint.status)).all()
        merged: dict[str, dict] = {}
        for category, status, n in rows:
            entry = merged.setdefault(category, {"category": category, "total": 0,
                                                 "open": 0, "resolved": 0})
            entry["total"] += n
            if status in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED):
                entry["resolved"] += n
            else:
                entry["open"] += n
        return sorted(merged.values(), key=lambda r: -r["total"])

    def attendance(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(Attendance.on_date, Attendance.status, func.count(Attendance.id))
            .where(*self._where(Attendance, branch_ids),
                   Attendance.on_date.between(from_date, to_date))
            .group_by(Attendance.on_date, Attendance.status)
            .order_by(Attendance.on_date.desc())).all()
        merged: dict[date, dict] = {}
        for on_date, status, n in rows:
            entry = merged.setdefault(on_date, {"date": on_date.isoformat(),
                                                "present": 0, "absent": 0,
                                                "late": 0, "on_leave": 0})
            entry[status.lower()] = n
        return list(merged.values())

    def visitors(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(Visitor.status, func.count(Visitor.id))
            .where(*self._where(Visitor, branch_ids),
                   func.date(Visitor.created_at).between(from_date, to_date))
            .group_by(Visitor.status)).all()
        return [{"status": s, "count": n} for s, n in rows]

    def gate_passes(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(GatePass.status, func.count(GatePass.id))
            .where(*self._where(GatePass, branch_ids),
                   func.date(GatePass.created_at).between(from_date, to_date))
            .group_by(GatePass.status)).all()
        return [{"status": s, "count": n} for s, n in rows]

    def food(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(MealAttendance.meal, MealAttendance.status,
                   func.count(MealAttendance.id))
            .where(*self._where(MealAttendance, branch_ids),
                   MealAttendance.on_date.between(from_date, to_date))
            .group_by(MealAttendance.meal, MealAttendance.status)).all()
        merged: dict[str, dict] = {}
        for meal, status, n in rows:
            entry = merged.setdefault(meal, {"meal": meal, "expected": 0, "attended": 0,
                                             "skipped": 0, "opted_out": 0})
            entry[status.lower()] = n
        return list(merged.values())

    def laundry(self, branch_ids, from_date, to_date):
        rows = self.db.execute(
            select(LaundryRequest.status, func.count(LaundryRequest.id),
                   func.sum(LaundryRequest.item_count))
            .where(*self._where(LaundryRequest, branch_ids),
                   func.date(LaundryRequest.created_at).between(from_date, to_date))
            .group_by(LaundryRequest.status)).all()
        return [{"status": s, "requests": n, "items": int(i or 0)} for s, n, i in rows]

    def inventory(self, branch_ids, from_date, to_date):
        rows = self.db.scalars(
            select(InventoryItem).where(*self._where(InventoryItem, branch_ids))
            .order_by(InventoryItem.category, InventoryItem.name)).all()
        return [{
            "sku": i.sku, "name": i.name, "category": i.category,
            "quantity": float(i.quantity), "unit": i.unit,
            "minimum_stock": float(i.minimum_stock),
            "low_stock": "Yes" if i.is_low else "No",
            "value": round(float(i.quantity) * float(i.purchase_price), 2),
        } for i in rows]

    def assets(self, branch_ids, from_date, to_date):
        rows = self.db.scalars(
            select(Asset).where(*self._where(Asset, branch_ids))
            .order_by(Asset.category, Asset.name)).all()
        return [{
            "asset_code": a.asset_code, "name": a.name, "category": a.category,
            "status": a.status,
            "purchase_date": a.purchase_date.isoformat() if a.purchase_date else "",
            "purchase_price": float(a.purchase_price), "location": a.location or "",
        } for a in rows]


def _cols(*pairs) -> list[dict]:
    return [{"key": k, "label": l} for k, l in pairs]


REPORTS: dict[str, dict] = {
    "occupancy": {
        "label": "Occupancy by branch", "group": "Property",
        "description": "Beds, occupancy and out-of-service inventory per branch.",
        "run": ReportService.occupancy,
        "columns": _cols(("branch", "Branch"), ("rooms", "Rooms"), ("beds", "Beds"),
                         ("occupied", "Occupied"), ("available", "Available"),
                         ("reserved", "Reserved"), ("out_of_service", "Out of service"),
                         ("occupancy_rate", "Occupancy %")),
    },
    "residents": {
        "label": "Resident register", "group": "Residents",
        "description": "Every resident with placement, status and rent.",
        "run": ReportService.residents,
        "columns": _cols(("name", "Name"), ("phone", "Phone"), ("email", "Email"),
                         ("branch", "Branch"), ("room", "Room"), ("status", "Status"),
                         ("joining_date", "Joined"), ("monthly_rent", "Rent")),
    },
    "rent_collection": {
        "label": "Rent collection", "group": "Finance",
        "description": "Billed against collected, grouped by invoice status.",
        "run": ReportService.rent_collection,
        "columns": _cols(("status", "Status"), ("invoices", "Invoices"),
                         ("billed", "Billed"), ("collected", "Collected"),
                         ("outstanding", "Outstanding")),
    },
    "outstanding": {
        "label": "Outstanding rent", "group": "Finance",
        "description": "Every unpaid invoice, oldest first.",
        "run": ReportService.outstanding,
        "columns": _cols(("invoice", "Invoice"), ("resident", "Resident"),
                         ("phone", "Phone"), ("due_date", "Due"), ("total", "Total"),
                         ("paid", "Paid"), ("balance", "Balance"),
                         ("days_overdue", "Days overdue"), ("status", "Status")),
    },
    "payments": {
        "label": "Payments received", "group": "Finance",
        "description": "All payments in the period with method and status.",
        "run": ReportService.payments,
        "columns": _cols(("payment", "Payment"), ("date", "Date"),
                         ("resident", "Resident"), ("amount", "Amount"),
                         ("method", "Method"), ("status", "Status"),
                         ("reference", "Reference")),
    },
    "invoices": {
        "label": "Invoices raised", "group": "Finance",
        "description": "Invoices issued in the period.",
        "run": ReportService.invoices,
        "columns": _cols(("invoice", "Invoice"), ("date", "Date"),
                         ("resident", "Resident"), ("total", "Total"),
                         ("paid", "Paid"), ("balance", "Balance"), ("status", "Status")),
    },
    "expenses": {
        "label": "Expenses by category", "group": "Finance",
        "description": "Spending grouped by category.",
        "run": ReportService.expenses,
        "columns": _cols(("category", "Category"), ("entries", "Entries"),
                         ("amount", "Amount")),
    },
    "profit_summary": {
        "label": "Revenue summary", "group": "Finance",
        "description": "Billed, collected and spent for the period.",
        "run": ReportService.profit_summary,
        "columns": _cols(("metric", "Metric"), ("amount", "Amount")),
    },
    "complaints": {
        "label": "Complaints by category", "group": "Operations",
        "description": "Volume and resolution rate per category.",
        "run": ReportService.complaints,
        "columns": _cols(("category", "Category"), ("total", "Total"),
                         ("open", "Open"), ("resolved", "Resolved")),
    },
    "attendance": {
        "label": "Attendance by day", "group": "Operations",
        "description": "Daily present, absent, late and on-leave counts.",
        "run": ReportService.attendance,
        "columns": _cols(("date", "Date"), ("present", "Present"), ("absent", "Absent"),
                         ("late", "Late"), ("on_leave", "On leave")),
    },
    "visitors": {
        "label": "Visitors", "group": "Operations",
        "description": "Visitor requests grouped by status.",
        "run": ReportService.visitors,
        "columns": _cols(("status", "Status"), ("count", "Count")),
    },
    "gate_passes": {
        "label": "Gate passes", "group": "Operations",
        "description": "Gate pass requests grouped by status.",
        "run": ReportService.gate_passes,
        "columns": _cols(("status", "Status"), ("count", "Count")),
    },
    "food": {
        "label": "Meal counts", "group": "Operations",
        "description": "Expected against actual, per meal.",
        "run": ReportService.food,
        "columns": _cols(("meal", "Meal"), ("expected", "Expected"),
                         ("attended", "Attended"), ("skipped", "Skipped"),
                         ("opted_out", "Opted out")),
    },
    "laundry": {
        "label": "Laundry", "group": "Operations",
        "description": "Laundry requests and item counts by status.",
        "run": ReportService.laundry,
        "columns": _cols(("status", "Status"), ("requests", "Requests"),
                         ("items", "Items")),
    },
    "inventory": {
        "label": "Inventory valuation", "group": "Back office",
        "description": "Stock on hand, low-stock flag and value.",
        "run": ReportService.inventory,
        "columns": _cols(("sku", "SKU"), ("name", "Item"), ("category", "Category"),
                         ("quantity", "Quantity"), ("unit", "Unit"),
                         ("minimum_stock", "Minimum"), ("low_stock", "Low stock"),
                         ("value", "Value")),
    },
    "assets": {
        "label": "Asset register", "group": "Back office",
        "description": "Every asset with status and purchase detail.",
        "run": ReportService.assets,
        "columns": _cols(("asset_code", "Code"), ("name", "Asset"),
                         ("category", "Category"), ("status", "Status"),
                         ("purchase_date", "Purchased"),
                         ("purchase_price", "Price"), ("location", "Location")),
    },
}
