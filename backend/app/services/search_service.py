"""
Global search.

Three rules shape this module:

  1. Every entity is gated by the permission that guards its own module. Search
     is a side door into the data; if a receptionist cannot open the expenses
     page they must not be able to read expense descriptions by typing in the
     search box.
  2. Every query is filtered by organisation AND by the caller's branch list -
     never by organisation alone. A manager restricted to one branch searching
     for "Kumar" must not learn that a Kumar lives in the branch across town.
  3. Every query is bounded. `LIMIT` per entity is not a nicety: an unbounded
     ILIKE '%a%' across nine tables on every keystroke is a denial of service
     the user does not even know they are causing.

Matching is ILIKE on a small set of columns per entity. Trigram or full-text
indexes would be faster, but they are an optimisation to make once real query
volume shows which entity is actually hot - not a thing to guess at now.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentScope
from app.models import (
    Bed, Branch, Complaint, Customer, Invoice, Payment, Room, SupportQuery,
    User, Visitor,
)

#: Hard ceiling per entity, whatever the caller asks for.
MAX_PER_TYPE = 8
#: Below this a search matches most of the table and is not useful.
MIN_TERM_LENGTH = 2


@dataclass
class Hit:
    type: str
    id: uuid.UUID
    title: str
    subtitle: str | None = None
    badge: str | None = None
    link: str | None = None

    def as_dict(self) -> dict:
        return {
            "type": self.type, "id": str(self.id), "title": self.title,
            "subtitle": self.subtitle, "badge": self.badge, "link": self.link,
        }


class SearchService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope

    @property
    def org_id(self) -> uuid.UUID:
        return self.scope.organization_id

    def _branch_filter(self, column):
        """
        Rows whose branch the caller can see, plus org-wide rows (branch NULL).

        `scope.branch_ids` is already the expanded concrete list - an owner with
        `all_branches` had it resolved to every branch in their organisation at
        request start, so this needs no special case for them.
        """
        if not self.scope.branch_ids:
            return column.is_(None)
        return or_(column.in_(self.scope.branch_ids), column.is_(None))

    def _rows(self, stmt, limit: int):
        return list(self.db.scalars(stmt.limit(limit)).all())

    def search(self, term: str, *, limit: int = 5,
               types: set[str] | None = None) -> list[dict]:
        term = (term or "").strip()
        if len(term) < MIN_TERM_LENGTH:
            return []
        per_type = max(1, min(limit, MAX_PER_TYPE))
        like = f"%{term}%"
        can = self.scope.can
        want = lambda t: types is None or t in types   # noqa: E731

        hits: list[Hit] = []

        # ------------------------------------------------------------ people
        if want("resident") and can(["customers.view"]):
            stmt = (select(Customer)
                    .where(Customer.organization_id == self.org_id,
                           self._branch_filter(Customer.branch_id),
                           or_(Customer.full_name.ilike(like),
                               Customer.email.ilike(like),
                               Customer.phone.ilike(like)))
                    .order_by(Customer.full_name))
            for r in self._rows(stmt, per_type):
                room = self.db.get(Room, r.room_id) if r.room_id else None
                hits.append(Hit(
                    "resident", r.id, r.full_name,
                    subtitle=(f"Room {room.room_number} · {r.status}"
                              if room else str(r.status)),
                    badge=str(r.status), link=f"/app/residents/{r.id}"))

        if want("staff") and can(["users.view", "staff.view"]):
            stmt = (select(User)
                    .where(User.organization_id == self.org_id,
                           or_(User.name.ilike(like), User.email.ilike(like)))
                    .order_by(User.name))
            for u in self._rows(stmt, per_type):
                hits.append(Hit("staff", u.id, u.name, subtitle=u.email,
                                badge=str(u.status), link="/app/staff"))

        # --------------------------------------------------------- property
        if want("room") and can(["rooms.view"]):
            stmt = (select(Room)
                    .where(Room.organization_id == self.org_id,
                           self._branch_filter(Room.branch_id),
                           Room.room_number.ilike(like))
                    .order_by(Room.room_number))
            for r in self._rows(stmt, per_type):
                branch = self.db.get(Branch, r.branch_id) if r.branch_id else None
                bits = [x for x in (r.room_type, branch.name if branch else None) if x]
                hits.append(Hit("room", r.id, f"Room {r.room_number}",
                                subtitle=" · ".join(bits) or None,
                                badge=str(r.status), link=f"/app/rooms?room={r.id}"))

        if want("bed") and can(["beds.view", "rooms.view"]):
            stmt = (select(Bed)
                    .where(Bed.organization_id == self.org_id,
                           self._branch_filter(Bed.branch_id),
                           or_(Bed.bed_code.ilike(like), Bed.bed_number.ilike(like)))
                    .order_by(Bed.bed_number))
            for b in self._rows(stmt, per_type):
                room = self.db.get(Room, b.room_id) if b.room_id else None
                hits.append(Hit("bed", b.id, f"Bed {b.bed_code or b.bed_number}",
                                subtitle=f"Room {room.room_number}" if room else None,
                                badge=str(b.status), link="/app/beds"))

        if want("branch") and can(["branches.view"]):
            stmt = (select(Branch)
                    .where(Branch.organization_id == self.org_id,
                           self._branch_filter(Branch.id),
                           or_(Branch.name.ilike(like), Branch.code.ilike(like)))
                    .order_by(Branch.name))
            for b in self._rows(stmt, per_type):
                hits.append(Hit("branch", b.id, b.name, subtitle=b.code,
                                badge=str(b.status), link="/app/branches"))

        # ---------------------------------------------------------- finance
        if want("invoice") and can(["invoices.view"]):
            stmt = (select(Invoice)
                    .where(Invoice.organization_id == self.org_id,
                           self._branch_filter(Invoice.branch_id),
                           Invoice.invoice_number.ilike(like))
                    .order_by(Invoice.invoice_date.desc()))
            for i in self._rows(stmt, per_type):
                resident = self.db.get(Customer, i.resident_id) if i.resident_id else None
                hits.append(Hit("invoice", i.id, i.invoice_number,
                                subtitle=(f"{resident.full_name} · {i.total}"
                                          if resident else str(i.total)),
                                badge=str(i.status), link="/app/invoices"))

        if want("payment") and can(["payments.view"]):
            stmt = (select(Payment)
                    .where(Payment.organization_id == self.org_id,
                           self._branch_filter(Payment.branch_id),
                           or_(Payment.payment_number.ilike(like),
                               Payment.reference.ilike(like)))
                    .order_by(Payment.payment_date.desc()))
            for p in self._rows(stmt, per_type):
                hits.append(Hit("payment", p.id, p.payment_number,
                                subtitle=f"{p.amount} · {p.method}",
                                badge=str(p.status), link="/app/payments"))

        # ---------------------------------------------------------- support
        if want("complaint") and can(["complaints.view"]):
            stmt = (select(Complaint)
                    .where(Complaint.organization_id == self.org_id,
                           self._branch_filter(Complaint.branch_id),
                           or_(Complaint.subject.ilike(like),
                               Complaint.category.ilike(like),
                               Complaint.ticket_number.ilike(like)))
                    .order_by(Complaint.created_at.desc()))
            for c in self._rows(stmt, per_type):
                hits.append(Hit("complaint", c.id, c.subject, subtitle=c.category,
                                badge=str(c.status), link="/app/complaints"))

        if want("query") and can(["queries.view", "complaints.view"]):
            stmt = (select(SupportQuery)
                    .where(SupportQuery.organization_id == self.org_id,
                           self._branch_filter(SupportQuery.branch_id),
                           SupportQuery.subject.ilike(like))
                    .order_by(SupportQuery.created_at.desc()))
            for q in self._rows(stmt, per_type):
                hits.append(Hit("query", q.id, q.subject, subtitle=q.category,
                                badge=str(q.status), link="/app/queries"))

        if want("visitor") and can(["visitors.view"]):
            stmt = (select(Visitor)
                    .where(Visitor.organization_id == self.org_id,
                           self._branch_filter(Visitor.branch_id),
                           or_(Visitor.name.ilike(like), Visitor.phone.ilike(like)))
                    .order_by(Visitor.created_at.desc()))
            for v in self._rows(stmt, per_type):
                hits.append(Hit("visitor", v.id, v.name, subtitle=v.phone,
                                badge=str(v.status), link="/app/visitors"))

        return [h.as_dict() for h in hits]
