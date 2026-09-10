"""
Helpdesk and back-office: complaints, queries, expenses, inventory, assets,
announcements and organisation settings.

The inventory methods take a row lock before adjusting stock. A CHECK constraint
stops the quantity going negative, but a constraint failure surfaces as a
database error rather than "not enough stock" - the lock lets the service give
the real answer.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import CurrentScope
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models import (
    Announcement, Asset, Complaint, ComplaintUpdate, Customer, Expense,
    InventoryItem, InventoryTransaction, OrganizationSettings, QueryMessage,
    SupportQuery, User,
)
from app.models.enums import (
    AnnouncementAudience, AssetStatus, AuditAction, ComplaintStatus,
    InventoryTxnType, NotificationType, PublishStatus, QueryStatus, TicketPriority,
)
from app.services.audit import AuditService
from app.services.notification_service import NotificationService

COMPLAINT_CATEGORIES = [
    "Maintenance", "Electrical", "Plumbing", "Housekeeping", "Food",
    "Internet", "Security", "Room", "Payment", "Other",
]
EXPENSE_CATEGORIES = [
    "Rent", "Electricity", "Water", "Internet", "Food", "Maintenance",
    "Housekeeping", "Salary", "Laundry", "Other",
]


class SupportService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope
        self.audit = AuditService(db)
        self.notify = NotificationService(db)

    @property
    def org_id(self) -> uuid.UUID:
        return self.scope.organization_id

    def _scoped(self, model):
        stmt = select(model).where(model.organization_id == self.org_id)
        if hasattr(model, "branch_id"):
            stmt = stmt.where(or_(model.branch_id.is_(None),
                                  model.branch_id.in_(self.scope.branch_ids)))
        return stmt

    def _page(self, stmt, order, page, page_size):
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.db.scalars(
            stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)).all())
        return rows, total

    def _next_number(self, model, column, prefix: str) -> str:
        n = self.db.scalar(select(func.count(model.id)).where(
            model.organization_id == self.org_id)) or 0
        return f"{prefix}-{n + 1:05d}"

    def _resident(self, resident_id: uuid.UUID) -> Customer:
        row = self.db.scalars(select(Customer).where(
            Customer.id == resident_id, Customer.organization_id == self.org_id)).first()
        if row is None:
            raise NotFoundError("Resident not found.")
        if row.branch_id and not self.scope.owns_branch(row.branch_id):
            raise PermissionDeniedError("Branch access denied.")
        return row

    # --------------------------------------------------------- complaints
    def list_complaints(self, *, status=None, priority=None, category=None,
                        branch_id=None, resident_id=None, assigned_to_id=None,
                        search=None, page=1, page_size=25):
        stmt = self._scoped(Complaint).options(selectinload(Complaint.resident))
        if status and status != "all":
            stmt = stmt.where(Complaint.status == status)
        if priority and priority != "all":
            stmt = stmt.where(Complaint.priority == priority)
        if category and category != "all":
            stmt = stmt.where(Complaint.category == category)
        if branch_id:
            stmt = stmt.where(Complaint.branch_id == branch_id)
        if resident_id:
            stmt = stmt.where(Complaint.resident_id == resident_id)
        if assigned_to_id:
            stmt = stmt.where(Complaint.assigned_to_id == assigned_to_id)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(Complaint.subject.ilike(like),
                                  Complaint.ticket_number.ilike(like)))
        return self._page(stmt, Complaint.created_at.desc(), page, page_size)

    def get_complaint(self, complaint_id: uuid.UUID) -> Complaint:
        row = self.db.scalars(
            self._scoped(Complaint).where(Complaint.id == complaint_id)).first()
        if row is None:
            raise NotFoundError("Complaint not found.")
        return row

    def create_complaint(self, data: dict, *, author_name: str | None = None,
                         author_resident_id: uuid.UUID | None = None) -> Complaint:
        branch_id = data.get("branch_id")
        resident = None
        if data.get("resident_id"):
            resident = self._resident(data["resident_id"])
            branch_id = resident.branch_id
        if branch_id is None:
            branch_id = self.scope.branch_ids[0]
        if not self.scope.owns_branch(branch_id):
            raise PermissionDeniedError("Branch access denied.")

        complaint = Complaint(
            organization_id=self.org_id, branch_id=branch_id,
            resident_id=resident.id if resident else None,
            room_id=resident.room_id if resident else data.get("room_id"),
            ticket_number=self._next_number(Complaint, Complaint.ticket_number, "CMP"),
            category=data.get("category") or "Other",
            subject=data["subject"], description=data.get("description"),
            priority=data.get("priority") or TicketPriority.MEDIUM,
            status=ComplaintStatus.OPEN)
        self.db.add(complaint)
        self.db.flush()

        if data.get("description"):
            self.db.add(ComplaintUpdate(
                organization_id=self.org_id, complaint_id=complaint.id,
                author_resident_id=author_resident_id,
                author_user_id=None if author_resident_id else (
                    self.scope.user.id if self.scope.user else None),
                author_name=author_name or (
                    resident.full_name if resident else self.scope.user.name),
                message=data["description"], status_after=ComplaintStatus.OPEN))

        self.audit.record(
            scope=self.scope, module="Complaints", action=AuditAction.CREATE,
            description=f"{complaint.ticket_number}: {complaint.subject}",
            entity_type="complaint", entity_id=complaint.id, branch_id=branch_id)
        self.notify.to_permission_holders(
            self.org_id, "complaints.manage", NotificationType.COMPLAINT_UPDATED,
            f"New {complaint.priority.lower()} complaint",
            f"{complaint.ticket_number}: {complaint.subject}",
            branch_id=branch_id, entity_type="complaint", entity_id=complaint.id)
        return complaint

    def update_complaint(self, complaint_id: uuid.UUID, data: dict) -> Complaint:
        complaint = self.get_complaint(complaint_id)
        changes = []

        if data.get("assigned_to_id") is not None:
            user = self.db.scalars(select(User).where(
                User.id == data["assigned_to_id"],
                User.organization_id == self.org_id)).first()
            if user is None:
                raise NotFoundError("That staff member does not exist.")
            complaint.assigned_to_id = user.id
            if complaint.status == ComplaintStatus.OPEN:
                complaint.status = ComplaintStatus.IN_PROGRESS
            changes.append(f"assigned to {user.name}")
            self.notify.to_user(
                user, NotificationType.COMPLAINT_UPDATED, "Complaint assigned to you",
                f"{complaint.ticket_number}: {complaint.subject}",
                entity_type="complaint", entity_id=complaint.id)

        for field in ("priority", "category", "subject", "description"):
            if data.get(field) is not None:
                setattr(complaint, field, data[field])

        if data.get("status") is not None and data["status"] != complaint.status:
            complaint.status = data["status"]
            changes.append(f"status {data['status']}")
            if data["status"] in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED):
                complaint.resolved_at = datetime.now(timezone.utc)
                complaint.resolution = data.get("resolution") or complaint.resolution

        if data.get("message"):
            self.db.add(ComplaintUpdate(
                organization_id=self.org_id, complaint_id=complaint.id,
                author_user_id=self.scope.user.id, author_name=self.scope.user.name,
                message=data["message"], status_after=complaint.status,
                is_internal=bool(data.get("is_internal"))))

        self.audit.record(
            scope=self.scope, module="Complaints", action=AuditAction.UPDATE,
            description=f"{complaint.ticket_number}: " + (", ".join(changes) or "updated"),
            entity_type="complaint", entity_id=complaint.id, branch_id=complaint.branch_id)

        if complaint.resident_id and not data.get("is_internal"):
            resident = self.db.get(Customer, complaint.resident_id)
            if resident:
                self.notify.to_resident(
                    resident, NotificationType.COMPLAINT_UPDATED,
                    f"Complaint {complaint.status.lower().replace('_', ' ')}",
                    f"{complaint.ticket_number}: {complaint.subject}",
                    entity_type="complaint", entity_id=complaint.id,
                    link="/me/complaints")
        return complaint

    # ------------------------------------------------------------ queries
    def list_queries(self, *, status=None, branch_id=None, resident_id=None,
                     search=None, page=1, page_size=25):
        stmt = self._scoped(SupportQuery).options(selectinload(SupportQuery.resident))
        if status and status != "all":
            stmt = stmt.where(SupportQuery.status == status)
        if branch_id:
            stmt = stmt.where(SupportQuery.branch_id == branch_id)
        if resident_id:
            stmt = stmt.where(SupportQuery.resident_id == resident_id)
        if search:
            stmt = stmt.where(SupportQuery.subject.ilike(f"%{search.strip()}%"))
        return self._page(stmt, SupportQuery.created_at.desc(), page, page_size)

    def get_query(self, query_id: uuid.UUID) -> SupportQuery:
        row = self.db.scalars(
            self._scoped(SupportQuery).where(SupportQuery.id == query_id)).first()
        if row is None:
            raise NotFoundError("Query not found.")
        return row

    def create_query(self, data: dict, *, author_name: str | None = None,
                     author_resident_id: uuid.UUID | None = None) -> SupportQuery:
        resident = None
        branch_id = data.get("branch_id")
        if data.get("resident_id"):
            resident = self._resident(data["resident_id"])
            branch_id = resident.branch_id
        if branch_id is None:
            branch_id = self.scope.branch_ids[0]

        query = SupportQuery(
            organization_id=self.org_id, branch_id=branch_id,
            resident_id=resident.id if resident else None,
            ticket_number=self._next_number(SupportQuery, SupportQuery.ticket_number, "QRY"),
            category=data.get("category") or "General",
            subject=data["subject"],
            # Opened by the office TO a resident, the next move is theirs:
            # ANSWERED is "waiting on the resident" everywhere else in this module.
            status=QueryStatus.ANSWERED if (resident and author_resident_id is None)
            else QueryStatus.OPEN)
        self.db.add(query)
        self.db.flush()

        from_resident = author_resident_id is not None
        self.db.add(QueryMessage(
            organization_id=self.org_id, query_id=query.id,
            author_resident_id=author_resident_id,
            author_user_id=None if from_resident else (
                self.scope.user.id if self.scope.user else None),
            # The author is whoever typed it. This used to put the resident's
            # name on a message the office wrote, so in the resident's app it
            # looked as though they had asked it themselves.
            author_name=author_name or (
                resident.full_name if (from_resident and resident) else self.scope.user.name),
            is_staff=not from_resident,
            message=data.get("message") or data["subject"]))

        if resident and not from_resident:
            # Without this the resident had no way of knowing a query existed.
            self.notify.to_resident(
                resident, NotificationType.SYSTEM, "Message from the office",
                f"{query.ticket_number}: {query.subject}",
                entity_type="query", entity_id=query.id, link="/me/queries")

        self.audit.record(
            scope=self.scope, module="Queries", action=AuditAction.CREATE,
            description=f"{query.ticket_number}: {query.subject}",
            entity_type="query", entity_id=query.id, branch_id=branch_id)
        return query

    def reply_to_query(self, query_id: uuid.UUID, message: str, *,
                       from_staff: bool = True, author_name: str | None = None,
                       author_resident_id: uuid.UUID | None = None,
                       close: bool = False) -> SupportQuery:
        query = self.get_query(query_id)
        self.db.add(QueryMessage(
            organization_id=self.org_id, query_id=query.id,
            author_user_id=self.scope.user.id if from_staff else None,
            author_resident_id=author_resident_id,
            author_name=author_name or (self.scope.user.name if from_staff else "Resident"),
            is_staff=from_staff, message=message))

        if close:
            query.status = QueryStatus.CLOSED
            query.closed_at = datetime.now(timezone.utc)
        elif from_staff:
            query.status = QueryStatus.ANSWERED
            query.assigned_to_id = self.scope.user.id
        else:
            query.status = QueryStatus.OPEN

        if from_staff and query.resident_id:
            resident = self.db.get(Customer, query.resident_id)
            if resident:
                self.notify.to_resident(
                    resident, NotificationType.SYSTEM, "Reply to your query",
                    f"{query.ticket_number}: {query.subject}",
                    entity_type="query", entity_id=query.id, link="/me/queries")
        return query

    # ----------------------------------------------------------- expenses
    def list_expenses(self, *, category=None, branch_id=None, from_date=None,
                      to_date=None, search=None, page=1, page_size=25):
        stmt = self._scoped(Expense)
        if category and category != "all":
            stmt = stmt.where(Expense.category == category)
        if branch_id:
            stmt = stmt.where(Expense.branch_id == branch_id)
        if from_date:
            stmt = stmt.where(Expense.spent_on >= from_date)
        if to_date:
            stmt = stmt.where(Expense.spent_on <= to_date)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(Expense.vendor.ilike(like),
                                  Expense.description.ilike(like),
                                  Expense.expense_number.ilike(like)))
        return self._page(stmt, Expense.spent_on.desc(), page, page_size)

    def create_expense(self, data: dict) -> Expense:
        if not self.scope.owns_branch(data["branch_id"]):
            raise PermissionDeniedError("Branch access denied.")
        if float(data["amount"]) <= 0:
            raise ConflictError("An expense must be more than zero.")

        expense = Expense(
            organization_id=self.org_id, branch_id=data["branch_id"],
            expense_number=self._next_number(Expense, Expense.expense_number, "EXP"),
            category=data.get("category") or "Other", amount=data["amount"],
            spent_on=data.get("spent_on") or date.today(), vendor=data.get("vendor"),
            payment_method=data.get("payment_method"), reference=data.get("reference"),
            description=data.get("description"),
            attachment_reference=data.get("attachment_reference"),
            created_by_id=self.scope.user.id)
        self.db.add(expense)
        self.db.flush()
        self.audit.record(
            scope=self.scope, module="Expenses", action=AuditAction.CREATE,
            description=f"{expense.category} expense {expense.amount} ({expense.vendor or '—'})",
            entity_type="expense", entity_id=expense.id, branch_id=expense.branch_id)
        return expense

    def update_expense(self, expense_id: uuid.UUID, data: dict) -> Expense:
        expense = self.db.scalars(
            self._scoped(Expense).where(Expense.id == expense_id)).first()
        if expense is None:
            raise NotFoundError("Expense not found.")
        for field in ("category", "amount", "spent_on", "vendor", "payment_method",
                      "reference", "description"):
            if data.get(field) is not None:
                setattr(expense, field, data[field])
        return expense

    def delete_expense(self, expense_id: uuid.UUID) -> None:
        expense = self.db.scalars(
            self._scoped(Expense).where(Expense.id == expense_id)).first()
        if expense is None:
            raise NotFoundError("Expense not found.")
        self.audit.record(
            scope=self.scope, module="Expenses", action=AuditAction.DELETE,
            description=f"Deleted expense {expense.expense_number}",
            entity_type="expense", entity_id=expense.id, branch_id=expense.branch_id)
        self.db.delete(expense)

    def expense_summary(self, *, branch_id=None) -> dict:
        branch_ids = [branch_id] if branch_id else list(self.scope.branch_ids)
        today = date.today()
        base = [Expense.organization_id == self.org_id,
                Expense.branch_id.in_(branch_ids or [uuid.UUID(int=0)])]

        def total(*extra) -> float:
            return float(self.db.scalar(
                select(func.sum(Expense.amount)).where(*base, *extra)) or 0)

        by_category = [
            {"category": c, "amount": float(a or 0), "count": n}
            for c, a, n in self.db.execute(
                select(Expense.category, func.sum(Expense.amount), func.count(Expense.id))
                .where(*base, Expense.spent_on >= today.replace(day=1))
                .group_by(Expense.category)
                .order_by(func.sum(Expense.amount).desc())).all()
        ]
        return {
            "today": total(Expense.spent_on == today),
            "this_month": total(Expense.spent_on >= today.replace(day=1)),
            "this_year": total(Expense.spent_on >= today.replace(month=1, day=1)),
            "by_category": by_category,
        }

    # ---------------------------------------------------------- inventory
    def list_inventory(self, *, category=None, branch_id=None, low_only=False,
                       search=None, page=1, page_size=50):
        stmt = self._scoped(InventoryItem)
        if category and category != "all":
            stmt = stmt.where(InventoryItem.category == category)
        if branch_id:
            stmt = stmt.where(InventoryItem.branch_id == branch_id)
        if low_only:
            stmt = stmt.where(InventoryItem.quantity <= InventoryItem.minimum_stock)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(InventoryItem.name.ilike(like),
                                  InventoryItem.sku.ilike(like)))
        return self._page(stmt, InventoryItem.name, page, page_size)

    def create_inventory_item(self, data: dict) -> InventoryItem:
        if not self.scope.owns_branch(data["branch_id"]):
            raise PermissionDeniedError("Branch access denied.")
        sku = data["sku"].strip().upper()
        if self.db.scalars(select(InventoryItem).where(
            InventoryItem.branch_id == data["branch_id"],
            InventoryItem.sku == sku)).first():
            raise ConflictError(f"SKU {sku} already exists in this branch.")

        item = InventoryItem(
            organization_id=self.org_id, branch_id=data["branch_id"], sku=sku,
            name=data["name"].strip(), category=data.get("category") or "Other",
            unit=data.get("unit") or "pcs", quantity=data.get("quantity") or 0,
            minimum_stock=data.get("minimum_stock") or 0,
            location=data.get("location"), supplier=data.get("supplier"),
            purchase_price=data.get("purchase_price") or 0)
        self.db.add(item)
        self.db.flush()

        if float(item.quantity) > 0:
            self.db.add(InventoryTransaction(
                organization_id=self.org_id, item_id=item.id, branch_id=item.branch_id,
                txn_type=InventoryTxnType.STOCK_IN, quantity_delta=item.quantity,
                balance_after=item.quantity, notes="Opening stock",
                created_by_id=self.scope.user.id))
        return item

    def adjust_stock(self, item_id: uuid.UUID, data: dict) -> InventoryItem:
        """
        Move stock. Locks the row first so two concurrent stock-outs cannot both
        pass the availability check.
        """
        item = self.db.scalars(
            select(InventoryItem)
            .where(InventoryItem.id == item_id,
                   InventoryItem.organization_id == self.org_id)
            .with_for_update()).first()
        if item is None:
            raise NotFoundError("Inventory item not found.")
        if not self.scope.owns_branch(item.branch_id):
            raise PermissionDeniedError("Branch access denied.")

        txn_type = data["txn_type"]
        quantity = abs(float(data["quantity"]))
        if quantity <= 0:
            raise ConflictError("The quantity must be more than zero.")

        if txn_type == InventoryTxnType.STOCK_IN:
            delta = quantity
        elif txn_type in (InventoryTxnType.STOCK_OUT, InventoryTxnType.TRANSFER):
            delta = -quantity
        else:
            # ADJUSTMENT sets an absolute count - a stock take, not a movement.
            delta = quantity - float(item.quantity)

        new_quantity = float(item.quantity) + delta
        if new_quantity < 0:
            raise ConflictError(
                f"Only {item.quantity} {item.unit} of {item.name} in stock — "
                f"cannot remove {quantity}.")

        item.quantity = round(new_quantity, 2)
        self.db.add(InventoryTransaction(
            organization_id=self.org_id, item_id=item.id, branch_id=item.branch_id,
            txn_type=txn_type, quantity_delta=round(delta, 2),
            balance_after=item.quantity, reference=data.get("reference"),
            notes=data.get("notes"), created_by_id=self.scope.user.id))
        self.db.flush()

        self.audit.record(
            scope=self.scope, module="Inventory", action=AuditAction.UPDATE,
            description=(f"{txn_type} {quantity} {item.unit} of {item.name} "
                         f"(now {item.quantity})"),
            entity_type="inventory_item", entity_id=item.id, branch_id=item.branch_id)

        if item.is_low:
            self.notify.to_permission_holders(
                self.org_id, "inventory.manage", NotificationType.SYSTEM,
                "Low stock",
                f"{item.name} is down to {item.quantity} {item.unit}.",
                branch_id=item.branch_id, entity_type="inventory_item", entity_id=item.id)
        return item

    def item_transactions(self, item_id: uuid.UUID, limit: int = 50):
        return list(self.db.scalars(
            select(InventoryTransaction)
            .where(InventoryTransaction.item_id == item_id,
                   InventoryTransaction.organization_id == self.org_id)
            .order_by(InventoryTransaction.created_at.desc()).limit(limit)).all())

    # ------------------------------------------------------------- assets
    def list_assets(self, *, category=None, status=None, branch_id=None,
                    search=None, page=1, page_size=50):
        stmt = self._scoped(Asset)
        if category and category != "all":
            stmt = stmt.where(Asset.category == category)
        if status and status != "all":
            stmt = stmt.where(Asset.status == status)
        if branch_id:
            stmt = stmt.where(Asset.branch_id == branch_id)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(Asset.name.ilike(like), Asset.asset_code.ilike(like)))
        return self._page(stmt, Asset.name, page, page_size)

    def create_asset(self, data: dict) -> Asset:
        if not self.scope.owns_branch(data["branch_id"]):
            raise PermissionDeniedError("Branch access denied.")
        code = (data.get("asset_code")
                or self._next_number(Asset, Asset.asset_code, "AST")).strip().upper()
        if self.db.scalars(select(Asset).where(
            Asset.organization_id == self.org_id, Asset.asset_code == code)).first():
            raise ConflictError(f"Asset code {code} already exists.")

        asset = Asset(
            organization_id=self.org_id, branch_id=data["branch_id"], asset_code=code,
            name=data["name"].strip(), category=data.get("category") or "Other",
            purchase_date=data.get("purchase_date"),
            purchase_price=data.get("purchase_price") or 0,
            warranty_until=data.get("warranty_until"), location=data.get("location"),
            room_id=data.get("room_id"), assigned_to_id=data.get("assigned_to_id"),
            status=data.get("status") or AssetStatus.ACTIVE, notes=data.get("notes"))
        self.db.add(asset)
        self.db.flush()
        self.audit.record(
            scope=self.scope, module="Assets", action=AuditAction.CREATE,
            description=f"Added asset {asset.name} ({code})",
            entity_type="asset", entity_id=asset.id, branch_id=asset.branch_id)
        return asset

    def update_asset(self, asset_id: uuid.UUID, data: dict) -> Asset:
        asset = self.db.scalars(self._scoped(Asset).where(Asset.id == asset_id)).first()
        if asset is None:
            raise NotFoundError("Asset not found.")
        for field in ("name", "category", "purchase_date", "purchase_price",
                      "warranty_until", "location", "room_id", "assigned_to_id",
                      "status", "notes"):
            if data.get(field) is not None:
                setattr(asset, field, data[field])
        return asset

    # ------------------------------------------------------ announcements
    def list_announcements(self, *, status=None, audience=None, branch_id=None,
                           page=1, page_size=25):
        stmt = self._scoped(Announcement)
        if status and status != "all":
            stmt = stmt.where(Announcement.status == status)
        if audience and audience != "all":
            stmt = stmt.where(Announcement.audience == audience)
        if branch_id:
            stmt = stmt.where(or_(Announcement.branch_id == branch_id,
                                  Announcement.branch_id.is_(None)))
        return self._page(stmt, Announcement.created_at.desc(), page, page_size)

    def create_announcement(self, data: dict) -> Announcement:
        row = Announcement(
            organization_id=self.org_id, branch_id=data.get("branch_id"),
            title=data["title"], message=data["message"],
            audience=data.get("audience") or AnnouncementAudience.ALL,
            priority=data.get("priority") or TicketPriority.MEDIUM,
            status=data.get("status") or PublishStatus.PUBLISHED,
            starts_on=data.get("starts_on") or date.today(),
            ends_on=data.get("ends_on"), created_by_id=self.scope.user.id)
        self.db.add(row)
        self.db.flush()

        if row.status == PublishStatus.PUBLISHED:
            self._fan_out(row)
        self.audit.record(
            scope=self.scope, module="Announcements", action=AuditAction.CREATE,
            description=f"Announcement: {row.title}",
            entity_type="announcement", entity_id=row.id, branch_id=row.branch_id)
        return row

    def _fan_out(self, announcement: Announcement) -> int:
        """
        Write one notification per recipient.

        A fan-out at write time rather than a join at read time: an announcement
        is published once and read constantly, and this way "mark as read" works
        per person without a second table.
        """
        sent = 0
        if announcement.audience in (AnnouncementAudience.ALL,
                                     AnnouncementAudience.RESIDENTS,
                                     AnnouncementAudience.BRANCH):
            stmt = select(Customer).where(
                Customer.organization_id == self.org_id,
                Customer.is_active.is_(True))
            if announcement.branch_id:
                stmt = stmt.where(Customer.branch_id == announcement.branch_id)
            for resident in self.db.scalars(stmt).all():
                self.notify.to_resident(
                    resident, NotificationType.ANNOUNCEMENT, announcement.title,
                    announcement.message, entity_type="announcement",
                    entity_id=announcement.id, link="/me/announcements")
                sent += 1

        if announcement.audience in (AnnouncementAudience.ALL, AnnouncementAudience.STAFF):
            for user in self.db.scalars(select(User).where(
                    User.organization_id == self.org_id,
                    User.is_active.is_(True))).all():
                self.notify.to_user(
                    user, NotificationType.ANNOUNCEMENT, announcement.title,
                    announcement.message, entity_type="announcement",
                    entity_id=announcement.id)
                sent += 1
        return sent

    def update_announcement(self, announcement_id: uuid.UUID, data: dict) -> Announcement:
        row = self.db.scalars(
            self._scoped(Announcement).where(Announcement.id == announcement_id)).first()
        if row is None:
            raise NotFoundError("Announcement not found.")
        was_draft = row.status != PublishStatus.PUBLISHED
        for field in ("title", "message", "audience", "priority", "status",
                      "starts_on", "ends_on", "branch_id"):
            if data.get(field) is not None:
                setattr(row, field, data[field])
        if was_draft and row.status == PublishStatus.PUBLISHED:
            self._fan_out(row)
        return row

    def delete_announcement(self, announcement_id: uuid.UUID) -> None:
        row = self.db.scalars(
            self._scoped(Announcement).where(Announcement.id == announcement_id)).first()
        if row is None:
            raise NotFoundError("Announcement not found.")
        self.db.delete(row)

    # ----------------------------------------------------------- settings
    def get_settings(self) -> OrganizationSettings:
        row = self.db.scalars(select(OrganizationSettings).where(
            OrganizationSettings.organization_id == self.org_id)).first()
        if row is None:
            row = OrganizationSettings(organization_id=self.org_id)
            self.db.add(row)
            self.db.flush()
        return row

    def update_settings(self, data: dict) -> OrganizationSettings:
        row = self.get_settings()
        for field in ("currency", "timezone", "contact_email", "contact_phone",
                      "rent_due_day", "late_fee_amount", "late_fee_after_days",
                      "invoice_prefix", "gate_duplicate_window_seconds",
                      "visitor_approval_required", "gate_pass_approval_required",
                      "food_enabled", "laundry_enabled", "meal_optout_cutoff_hours",
                      "checkout_notice_days"):
            if data.get(field) is not None:
                setattr(row, field, data[field])
        if data.get("extra") is not None:
            row.extra = {**(row.extra or {}), **data["extra"]}
        self.audit.record(
            scope=self.scope, module="Settings", action=AuditAction.UPDATE,
            description="Updated organisation settings",
            entity_type="settings", entity_id=row.id)
        return row
