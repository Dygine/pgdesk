"""Helpdesk, back office, notifications, announcements, settings and reports."""
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from sqlalchemy import func, or_, select

from app.core.dependencies import (
    CurrentScope, DbSession, get_current_principal, require, require_branch,
    require_tenant,
)
from app.core.responses import ok, paginated
from app.models import (
    Announcement, Asset, Complaint, Expense, InventoryItem, SupportQuery,
)
from app.schemas.operations import (
    AnnouncementCreate, AnnouncementUpdate, AssetCreate, AssetUpdate,
    ComplaintCreate, ComplaintUpdateIn, ExpenseCreate, ExpenseUpdate,
    InventoryCreate, QueryCreate, QueryReply, SettingsUpdate, StockAdjustment,
)
from app.services.notification_service import NotificationService
from app.services.report_service import REPORTS, ReportService
from app.services.search_service import SearchService
from app.services.support_service import (
    COMPLAINT_CATEGORIES, EXPENSE_CATEGORIES, SupportService,
)

router = APIRouter(tags=["support"])
Tenant = Annotated[CurrentScope, Depends(require_tenant)]


def _svc(db, scope) -> SupportService:
    return SupportService(db, scope)


def _complaint(c: Complaint, *, detail: bool = False) -> dict:
    payload = {
        "id": str(c.id), "ticket_number": c.ticket_number, "category": c.category,
        "subject": c.subject, "description": c.description, "priority": c.priority,
        "status": c.status, "branch_id": str(c.branch_id),
        "resident_id": str(c.resident_id) if c.resident_id else None,
        "resident": c.resident.full_name if c.resident else None,
        "assigned_to_id": str(c.assigned_to_id) if c.assigned_to_id else None,
        "resolution": c.resolution,
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        "created_at": c.created_at.isoformat(),
    }
    if detail:
        payload["updates"] = [
            {"id": str(u.id), "author": u.author_name, "message": u.message,
             "status_after": u.status_after, "is_internal": u.is_internal,
             "created_at": u.created_at.isoformat()}
            for u in sorted(c.updates, key=lambda x: x.created_at)]
    return payload


def _opened_by(q: SupportQuery) -> str:
    first = min(q.messages, key=lambda m: m.created_at) if q.messages else None
    return "staff" if (first is not None and first.is_staff) else "resident"


def _query(q: SupportQuery, *, detail: bool = False) -> dict:
    payload = {
        "id": str(q.id), "ticket_number": q.ticket_number, "category": q.category,
        "subject": q.subject, "status": q.status, "branch_id": str(q.branch_id),
        "resident_id": str(q.resident_id) if q.resident_id else None,
        "resident": q.resident.full_name if q.resident else None,
        "created_at": q.created_at.isoformat(),
        "message_count": len(q.messages),
        # Who started it: the office (a message sent to a resident) or the resident.
        "opened_by": _opened_by(q),
    }
    if detail:
        payload["messages"] = [
            {"id": str(m.id), "author": m.author_name, "is_staff": m.is_staff,
             "message": m.message, "created_at": m.created_at.isoformat()}
            for m in sorted(q.messages, key=lambda x: x.created_at)]
    return payload


def _expense(e: Expense) -> dict:
    return {
        "id": str(e.id), "expense_number": e.expense_number, "category": e.category,
        "amount": float(e.amount), "spent_on": e.spent_on.isoformat(),
        "vendor": e.vendor, "payment_method": e.payment_method,
        "reference": e.reference, "description": e.description,
        "branch_id": str(e.branch_id),
    }


def _item(i: InventoryItem) -> dict:
    return {
        "id": str(i.id), "sku": i.sku, "name": i.name, "category": i.category,
        "unit": i.unit, "quantity": float(i.quantity),
        "minimum_stock": float(i.minimum_stock), "is_low": i.is_low,
        "location": i.location, "supplier": i.supplier,
        "purchase_price": float(i.purchase_price), "branch_id": str(i.branch_id),
        "value": round(float(i.quantity) * float(i.purchase_price), 2),
    }


def _asset(a: Asset) -> dict:
    return {
        "id": str(a.id), "asset_code": a.asset_code, "name": a.name,
        "category": a.category, "status": a.status, "location": a.location,
        "purchase_date": a.purchase_date.isoformat() if a.purchase_date else None,
        "purchase_price": float(a.purchase_price),
        "warranty_until": a.warranty_until.isoformat() if a.warranty_until else None,
        "assigned_to_id": str(a.assigned_to_id) if a.assigned_to_id else None,
        "branch_id": str(a.branch_id), "notes": a.notes,
    }


def _announcement(a: Announcement) -> dict:
    return {
        "id": str(a.id), "title": a.title, "message": a.message,
        "audience": a.audience, "priority": a.priority, "status": a.status,
        "branch_id": str(a.branch_id) if a.branch_id else None,
        "starts_on": a.starts_on.isoformat() if a.starts_on else None,
        "ends_on": a.ends_on.isoformat() if a.ends_on else None,
        "created_at": a.created_at.isoformat(),
    }


# --------------------------------------------------------------- complaints
@router.get("/complaints", summary="List complaints")
def list_complaints(db: DbSession, scope: Tenant,
                    _: None = Depends(require("complaints.view")),
                    status_filter: str | None = Query(default=None, alias="status"),
                    priority: str | None = None, category: str | None = None,
                    branch_id: uuid.UUID | None = None,
                    resident_id: uuid.UUID | None = None,
                    assigned_to_id: uuid.UUID | None = None,
                    search: str | None = None,
                    page: int = Query(default=1, ge=1),
                    page_size: int = Query(default=25, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_complaints(
        status=status_filter, priority=priority, category=category,
        branch_id=branch_id, resident_id=resident_id, assigned_to_id=assigned_to_id,
        search=search, page=page, page_size=page_size)
    return paginated([_complaint(c) for c in rows], page, page_size, total)


@router.get("/complaints/categories", summary="Suggested complaint categories")
def complaint_categories(scope: Tenant) -> dict:
    return ok(COMPLAINT_CATEGORIES)


@router.get("/complaints/{complaint_id}", summary="Complaint detail with its thread")
def get_complaint(complaint_id: uuid.UUID, db: DbSession, scope: Tenant,
                  _: None = Depends(require("complaints.view"))) -> dict:
    return ok(_complaint(_svc(db, scope).get_complaint(complaint_id), detail=True))


@router.post("/complaints", status_code=status.HTTP_201_CREATED, summary="Raise a complaint")
def create_complaint(body: ComplaintCreate, db: DbSession, scope: Tenant,
                     _: None = Depends(require("complaints.create",
                                               "complaints.manage"))) -> dict:
    complaint = _svc(db, scope).create_complaint(body.model_dump())
    db.commit()
    db.refresh(complaint)
    return ok(_complaint(complaint, detail=True),
              message=f"Complaint {complaint.ticket_number} raised.")


@router.patch("/complaints/{complaint_id}", summary="Assign, update or resolve")
def update_complaint(complaint_id: uuid.UUID, body: ComplaintUpdateIn, db: DbSession,
                     scope: Tenant,
                     _: None = Depends(require("complaints.update", "complaints.assign",
                                               "complaints.manage"))) -> dict:
    complaint = _svc(db, scope).update_complaint(
        complaint_id, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(complaint)
    return ok(_complaint(complaint, detail=True), message="Complaint updated.")


# ------------------------------------------------------------------ queries
@router.get("/queries", summary="List support queries")
def list_queries(db: DbSession, scope: Tenant,
                 _: None = Depends(require("queries.view")),
                 status_filter: str | None = Query(default=None, alias="status"),
                 branch_id: uuid.UUID | None = None,
                 resident_id: uuid.UUID | None = None,
                 search: str | None = None,
                 page: int = Query(default=1, ge=1),
                 page_size: int = Query(default=25, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_queries(
        status=status_filter, branch_id=branch_id, resident_id=resident_id,
        search=search, page=page, page_size=page_size)
    return paginated([_query(q) for q in rows], page, page_size, total)


@router.get("/queries/{query_id}", summary="Query with its conversation")
def get_query(query_id: uuid.UUID, db: DbSession, scope: Tenant,
              _: None = Depends(require("queries.view"))) -> dict:
    return ok(_query(_svc(db, scope).get_query(query_id), detail=True))


@router.post("/queries", status_code=status.HTTP_201_CREATED, summary="Open a query")
def create_query(body: QueryCreate, db: DbSession, scope: Tenant,
                 _: None = Depends(require("queries.create", "queries.manage"))) -> dict:
    query = _svc(db, scope).create_query(body.model_dump())
    db.commit()
    db.refresh(query)
    return ok(_query(query, detail=True), message=f"Query {query.ticket_number} opened.")


@router.post("/queries/{query_id}/reply", summary="Reply to a query")
def reply_to_query(query_id: uuid.UUID, body: QueryReply, db: DbSession, scope: Tenant,
                   _: None = Depends(require("queries.respond", "queries.manage"))) -> dict:
    query = _svc(db, scope).reply_to_query(query_id, body.message, close=body.close)
    db.commit()
    db.refresh(query)
    return ok(_query(query, detail=True), message="Reply sent.")


# ----------------------------------------------------------------- expenses
@router.get("/expenses", summary="List expenses")
def list_expenses(db: DbSession, scope: Tenant,
                  _: None = Depends(require("expenses.view")),
                  category: str | None = None,
                  branch_id: uuid.UUID | None = None,
                  from_date: date | None = None, to_date: date | None = None,
                  search: str | None = None,
                  page: int = Query(default=1, ge=1),
                  page_size: int = Query(default=25, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_expenses(
        category=category, branch_id=branch_id, from_date=from_date,
        to_date=to_date, search=search, page=page, page_size=page_size)
    return paginated([_expense(e) for e in rows], page, page_size, total)


@router.get("/expenses/summary", summary="Expense totals")
def expense_summary(db: DbSession, scope: Tenant,
                    _: None = Depends(require("expenses.view")),
                    branch_id: uuid.UUID | None = None) -> dict:
    return ok({**_svc(db, scope).expense_summary(branch_id=branch_id),
               "categories": EXPENSE_CATEGORIES})


@router.post("/expenses", status_code=status.HTTP_201_CREATED, summary="Record an expense")
def create_expense(body: ExpenseCreate, db: DbSession, scope: Tenant,
                   _: None = Depends(require("expenses.create"))) -> dict:
    expense = _svc(db, scope).create_expense(body.model_dump())
    db.commit()
    return ok(_expense(expense), message=f"Expense {expense.expense_number} recorded.")


@router.patch("/expenses/{expense_id}", summary="Edit an expense")
def update_expense(expense_id: uuid.UUID, body: ExpenseUpdate, db: DbSession,
                   scope: Tenant, _: None = Depends(require("expenses.edit"))) -> dict:
    expense = _svc(db, scope).update_expense(
        expense_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok(_expense(expense), message="Expense updated.")


@router.delete("/expenses/{expense_id}", summary="Delete an expense")
def delete_expense(expense_id: uuid.UUID, db: DbSession, scope: Tenant,
                   _: None = Depends(require("expenses.delete"))) -> dict:
    _svc(db, scope).delete_expense(expense_id)
    db.commit()
    return ok(None, message="Expense deleted.")


# ---------------------------------------------------------------- inventory
@router.get("/inventory", summary="List inventory")
def list_inventory(db: DbSession, scope: Tenant,
                   _: None = Depends(require("inventory.view")),
                   category: str | None = None,
                   branch_id: uuid.UUID | None = None,
                   low_only: bool = False, search: str | None = None,
                   page: int = Query(default=1, ge=1),
                   page_size: int = Query(default=50, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_inventory(
        category=category, branch_id=branch_id, low_only=low_only,
        search=search, page=page, page_size=page_size)
    return paginated([_item(i) for i in rows], page, page_size, total)


@router.post("/inventory", status_code=status.HTTP_201_CREATED, summary="Add an item")
def create_item(body: InventoryCreate, db: DbSession, scope: Tenant,
                _: None = Depends(require("inventory.create", "inventory.manage"))) -> dict:
    item = _svc(db, scope).create_inventory_item(body.model_dump())
    db.commit()
    return ok(_item(item), message=f"{item.name} added.")


@router.post("/inventory/{item_id}/adjust", summary="Move stock")
def adjust_stock(item_id: uuid.UUID, body: StockAdjustment, db: DbSession,
                 scope: Tenant,
                 _: None = Depends(require("inventory.adjust", "inventory.manage"))) -> dict:
    """
    Locks the row before checking availability, so two simultaneous stock-outs
    cannot both pass. Stock can never go negative.
    """
    item = _svc(db, scope).adjust_stock(item_id, body.model_dump())
    db.commit()
    return ok(_item(item), message=f"{item.name}: now {item.quantity} {item.unit}.")


@router.get("/inventory/{item_id}/transactions", summary="Stock ledger for an item")
def item_transactions(item_id: uuid.UUID, db: DbSession, scope: Tenant,
                      _: None = Depends(require("inventory.view"))) -> dict:
    rows = _svc(db, scope).item_transactions(item_id)
    return ok([
        {"id": str(t.id), "txn_type": t.txn_type,
         "quantity_delta": float(t.quantity_delta),
         "balance_after": float(t.balance_after), "reference": t.reference,
         "notes": t.notes, "created_at": t.created_at.isoformat()}
        for t in rows])


# ------------------------------------------------------------------- assets
@router.get("/assets", summary="List assets")
def list_assets(db: DbSession, scope: Tenant,
                _: None = Depends(require("assets.view")),
                category: str | None = None,
                status_filter: str | None = Query(default=None, alias="status"),
                branch_id: uuid.UUID | None = None, search: str | None = None,
                page: int = Query(default=1, ge=1),
                page_size: int = Query(default=50, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_assets(
        category=category, status=status_filter, branch_id=branch_id,
        search=search, page=page, page_size=page_size)
    return paginated([_asset(a) for a in rows], page, page_size, total)


@router.post("/assets", status_code=status.HTTP_201_CREATED, summary="Add an asset")
def create_asset(body: AssetCreate, db: DbSession, scope: Tenant,
                 _: None = Depends(require("assets.create", "assets.manage"))) -> dict:
    asset = _svc(db, scope).create_asset(body.model_dump())
    db.commit()
    return ok(_asset(asset), message=f"{asset.name} added.")


@router.patch("/assets/{asset_id}", summary="Edit an asset")
def update_asset(asset_id: uuid.UUID, body: AssetUpdate, db: DbSession, scope: Tenant,
                 _: None = Depends(require("assets.manage"))) -> dict:
    asset = _svc(db, scope).update_asset(asset_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok(_asset(asset), message="Asset updated.")


# ------------------------------------------------------------ announcements
@router.get("/announcements", summary="List announcements")
def list_announcements(db: DbSession, scope: Tenant,
                       _: None = Depends(require("announcements.view")),
                       status_filter: str | None = Query(default=None, alias="status"),
                       audience: str | None = None,
                       branch_id: uuid.UUID | None = None,
                       page: int = Query(default=1, ge=1),
                       page_size: int = Query(default=25, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_announcements(
        status=status_filter, audience=audience, branch_id=branch_id,
        page=page, page_size=page_size)
    return paginated([_announcement(a) for a in rows], page, page_size, total)


@router.post("/announcements", status_code=status.HTTP_201_CREATED,
             summary="Publish an announcement")
def create_announcement(body: AnnouncementCreate, db: DbSession, scope: Tenant,
                        _: None = Depends(require("announcements.create"))) -> dict:
    """Publishing writes one notification per recipient, so read state is per person."""
    row = _svc(db, scope).create_announcement(body.model_dump())
    db.commit()
    return ok(_announcement(row), message="Announcement published.")


@router.patch("/announcements/{announcement_id}", summary="Edit an announcement")
def update_announcement(announcement_id: uuid.UUID, body: AnnouncementUpdate,
                        db: DbSession, scope: Tenant,
                        _: None = Depends(require("announcements.edit"))) -> dict:
    row = _svc(db, scope).update_announcement(
        announcement_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok(_announcement(row), message="Announcement updated.")


@router.delete("/announcements/{announcement_id}", summary="Delete an announcement")
def delete_announcement(announcement_id: uuid.UUID, db: DbSession, scope: Tenant,
                        _: None = Depends(require("announcements.delete"))) -> dict:
    _svc(db, scope).delete_announcement(announcement_id)
    db.commit()
    return ok(None, message="Announcement deleted.")


# -------------------------------------------------------------- audit log
@router.get("/audit", summary="Audit log for this organisation")
def organisation_audit(db: DbSession, scope: Tenant,
                       _: None = Depends(require("audit.view")),
                       module: str | None = None,
                       branch_id: uuid.UUID | None = None,
                       page: int = Query(default=1, ge=1),
                       page_size: int = Query(default=25, ge=1, le=100)) -> dict:
    """
    The tenant's own audit trail.

    Distinct from /master/audit, which spans every organisation and is master
    only. This one is filtered to the caller's organisation AND to the branches
    they are assigned to: an audit trail is a description of what happened in a
    branch, so a manager confined to one branch reading another's history would
    be the same leak as reading its residents.
    """
    from app.models import AuditLog

    stmt = select(AuditLog).where(AuditLog.organization_id == scope.organization_id)

    if branch_id:
        require_branch(scope, branch_id)
        stmt = stmt.where(AuditLog.branch_id == branch_id)
    elif not scope.all_branches:
        # Branch-less entries (org-wide actions) stay visible to everyone in the
        # tenant; branch-tagged ones only to people assigned to that branch.
        stmt = stmt.where(or_(AuditLog.branch_id.is_(None),
                              AuditLog.branch_id.in_(scope.branch_ids or [])))

    if module and module != "all":
        stmt = stmt.where(AuditLog.module == module)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)).all()

    return paginated([
        {"id": str(a.id), "module": a.module, "action": a.action,
         "description": a.description, "user_name": a.user_name,
         "entity_type": a.entity_type, "entity_id": a.entity_id,
         "branch_id": str(a.branch_id) if a.branch_id else None,
         "ip_address": a.ip_address,
         "created_at": a.created_at.isoformat()}
        for a in rows], page, page_size, total)


# ------------------------------------------------------------------- search
@router.get("/search", summary="Search across the organisation")
def global_search(db: DbSession, scope: Tenant,
                  q: str = Query(min_length=2, max_length=120,
                                 description="At least two characters."),
                  limit: int = Query(5, ge=1, le=8),
                  types: str | None = Query(
                      None, description="Comma-separated: resident, staff, room, "
                                        "bed, branch, invoice, payment, complaint, "
                                        "query, visitor. Omit for everything.")) -> dict:
    """
    One box, several tables.

    Each entity is gated by its own module permission and filtered by the
    caller's branch list, so this returns strictly a subset of what the caller
    could already reach by opening the individual pages. It is not a privileged
    view - it is a shortcut to an unprivileged one.
    """
    wanted = None
    if types:
        wanted = {t.strip() for t in types.split(",") if t.strip()}
    results = SearchService(db, scope).search(q, limit=limit, types=wanted)
    return ok({"query": q, "count": len(results), "results": results})


# ----------------------------------------------------------------- settings
@router.get("/settings", summary="Organisation settings")
def get_settings(db: DbSession, scope: Tenant,
                 _: None = Depends(require("settings.view"))) -> dict:
    s = _svc(db, scope).get_settings()
    return ok({
        "currency": s.currency, "timezone": s.timezone,
        "contact_email": s.contact_email, "contact_phone": s.contact_phone,
        "rent_due_day": s.rent_due_day, "late_fee_amount": float(s.late_fee_amount),
        "late_fee_after_days": s.late_fee_after_days,
        "invoice_prefix": s.invoice_prefix,
        "gate_duplicate_window_seconds": s.gate_duplicate_window_seconds,
        "visitor_approval_required": s.visitor_approval_required,
        "gate_pass_approval_required": s.gate_pass_approval_required,
        "food_enabled": s.food_enabled, "laundry_enabled": s.laundry_enabled,
        "meal_optout_cutoff_hours": s.meal_optout_cutoff_hours,
        "checkout_notice_days": s.checkout_notice_days,
        "extra": s.extra or {},
    })


@router.patch("/settings", summary="Update organisation settings")
def update_settings(body: SettingsUpdate, db: DbSession, scope: Tenant,
                    _: None = Depends(require("settings.manage"))) -> dict:
    _svc(db, scope).update_settings(body.model_dump(exclude_unset=True))
    db.commit()
    return ok(None, message="Settings saved.")


# ------------------------------------------------------------ notifications
@router.get("/notifications", summary="Your notifications")
def list_notifications(db: DbSession, principal=Depends(get_current_principal),
                       unread_only: bool = False,
                       page: int = Query(default=1, ge=1),
                       page_size: int = Query(default=25, ge=1, le=100)) -> dict:
    """
    Scoped to the caller by identity, not by a query parameter - there is no way
    to ask for somebody else's notifications.
    """
    service = NotificationService(db)
    kwargs = ({"user_id": principal.id} if principal.is_user
              else {"resident_id": principal.id})
    rows, total = service.list(
        principal.organization_id, unread_only=unread_only,
        page=page, page_size=page_size, **kwargs)
    payload = paginated([
        {"id": str(n.id), "kind": n.kind, "title": n.title, "message": n.message,
         "link": n.link, "entity_type": n.entity_type,
         "read": n.read_at is not None,
         "created_at": n.created_at.isoformat()}
        for n in rows], page, page_size, total)
    payload["unread_count"] = service.unread_count(
        principal.organization_id, **kwargs)
    return payload


@router.post("/notifications/{notification_id}/read", summary="Mark one as read")
def mark_read(notification_id: uuid.UUID, db: DbSession,
              principal=Depends(get_current_principal)) -> dict:
    service = NotificationService(db)
    kwargs = ({"user_id": principal.id} if principal.is_user
              else {"resident_id": principal.id})
    service.mark_read(notification_id, **kwargs)
    db.commit()
    return ok(None)


@router.post("/notifications/read-all", summary="Mark everything as read")
def mark_all_read(db: DbSession, principal=Depends(get_current_principal)) -> dict:
    service = NotificationService(db)
    kwargs = ({"user_id": principal.id} if principal.is_user
              else {"resident_id": principal.id})
    count = service.mark_all_read(principal.organization_id, **kwargs)
    db.commit()
    return ok({"updated": count}, message=f"{count} marked as read.")


# ------------------------------------------------------------------ reports
@router.get("/reports", summary="Available reports")
def list_reports(db: DbSession, scope: Tenant,
                 _: None = Depends(require("reports.view"))) -> dict:
    return ok(ReportService(db, scope).catalogue())


@router.get("/reports/{key}", summary="Run a report")
def run_report(key: str, db: DbSession, scope: Tenant,
               _: None = Depends(require("reports.view")),
               branch_id: uuid.UUID | None = None,
               from_date: date | None = None, to_date: date | None = None) -> dict:
    """Aggregated by PostgreSQL, so the totals cover the whole set, not one page."""
    return ok(ReportService(db, scope).run(
        key, branch_id=branch_id, from_date=from_date, to_date=to_date))


@router.get("/reports/{key}/export", summary="Download a report as CSV")
def export_report(key: str, db: DbSession, scope: Tenant,
                  _: None = Depends(require("reports.export")),
                  branch_id: uuid.UUID | None = None,
                  from_date: date | None = None, to_date: date | None = None):
    service = ReportService(db, scope)
    report = service.run(key, branch_id=branch_id, from_date=from_date, to_date=to_date)
    return Response(
        content=service.to_csv(report), media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="pgdesk-{key}-{date.today()}.csv"'})
