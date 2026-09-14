"""
PG owners raising tickets with the platform, and the operator answering them.

Deliberately separate from `support_service`, which is a resident raising a
complaint with their PG. Those two look alike and run in opposite directions:
one is tenant data the PG owns, this one crosses the tenant boundary and is read
by the platform operator. Sharing a service would mean every master-admin query
needed an "and not really a tenant record" filter, and one missed filter leaks a
PG's private thread into another PG's inbox.

Notifications go both ways: the owner is told when the platform replies, and the
operator's dashboard counts what is waiting on them.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Organization, PlatformCharge, PlatformTicket, PlatformTicketMessage, User,
)
from app.models.enums import NotificationType
from app.services.notification_service import NotificationService

log = logging.getLogger("pgguru.platform_support")

OPEN_STATES = ("open", "in_progress", "waiting")

CATEGORIES = {"payment", "bug", "feature", "question", "other"}
PRIORITIES = {"low", "normal", "high", "urgent"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _reference() -> str:
    """
    Human-quotable and not sequential.

    An owner reads this out on a phone call, so it is short. It is random rather
    than counted because a sequential ticket number tells every customer how
    many support requests the platform has ever had.
    """
    return "TKT-" + secrets.token_hex(3).upper()


class PlatformSupportService:
    def __init__(self, db: Session):
        self.db = db
        self.notify = NotificationService(db)

    # ------------------------------------------------------------- owner --
    def raise_ticket(self, *, organization_id: uuid.UUID, user: User | None,
                     subject: str, body: str, category: str = "question",
                     priority: str = "normal",
                     charge_id: uuid.UUID | None = None) -> PlatformTicket:
        if category not in CATEGORIES:
            category = "other"
        if priority not in PRIORITIES:
            priority = "normal"

        ticket = PlatformTicket(
            reference=_reference(), organization_id=organization_id,
            raised_by_id=user.id if user else None,
            subject=subject.strip()[:200], category=category, priority=priority,
            status="open", charge_id=charge_id,
            last_reply_by="owner", last_reply_at=_now())
        self.db.add(ticket)
        self.db.flush()

        self.db.add(PlatformTicketMessage(
            ticket_id=ticket.id, author_side="owner",
            author_id=user.id if user else None,
            author_name=(user.name if user and user.name else "PG owner"),
            body=body.strip()))
        self.db.flush()
        log.info("ticket %s raised by org %s", ticket.reference, organization_id)
        return ticket

    def reply_as_owner(self, ticket: PlatformTicket, *, user: User | None,
                       body: str) -> PlatformTicketMessage:
        message = PlatformTicketMessage(
            ticket_id=ticket.id, author_side="owner",
            author_id=user.id if user else None,
            author_name=(user.name if user and user.name else "PG owner"),
            body=body.strip())
        self.db.add(message)

        # A reply reopens a resolved ticket. The alternative - making the owner
        # raise a new one because the fix did not work - loses the history at
        # exactly the moment it is most useful.
        if ticket.status in ("resolved", "closed"):
            ticket.status = "open"
        elif ticket.status == "waiting":
            ticket.status = "in_progress"
        ticket.last_reply_by = "owner"
        ticket.last_reply_at = _now()
        self.db.flush()
        return message

    def for_organization(self, organization_id: uuid.UUID,
                         limit: int = 50) -> list[PlatformTicket]:
        return list(self.db.scalars(
            select(PlatformTicket)
            .where(PlatformTicket.organization_id == organization_id)
            .order_by(PlatformTicket.created_at.desc())
            .limit(limit)))

    # ---------------------------------------------------------- platform --
    def reply_as_platform(self, ticket: PlatformTicket, *, user: User | None,
                          body: str, internal: bool = False,
                          status: str | None = None) -> PlatformTicketMessage:
        message = PlatformTicketMessage(
            ticket_id=ticket.id, author_side="platform",
            author_id=user.id if user else None,
            author_name=(user.name if user and user.name else "Support"),
            body=body.strip(), internal=internal)
        self.db.add(message)

        if status:
            self.set_status(ticket, status, user=user, notify=False)
        elif not internal and ticket.status == "open":
            ticket.status = "in_progress"

        if not internal:
            # An internal note must not look to the owner like an answer, and
            # must not flip whose turn it is.
            ticket.last_reply_by = "platform"
            ticket.last_reply_at = _now()
            self._notify_owner(
                ticket, f"Support replied to {ticket.reference}",
                body.strip()[:160])
        self.db.flush()
        return message

    def set_status(self, ticket: PlatformTicket, status: str, *,
                   user: User | None = None, notify: bool = True) -> PlatformTicket:
        if status not in ("open", "in_progress", "waiting", "resolved", "closed"):
            raise ValueError(f"Unknown ticket status: {status}")

        ticket.status = status
        if status in ("resolved", "closed"):
            ticket.resolved_at = _now()
            ticket.resolved_by_id = user.id if user else None
            if notify:
                self._notify_owner(
                    ticket, f"{ticket.reference} was marked {status}",
                    "Reply on the ticket if this is not sorted — it reopens "
                    "automatically.")
        else:
            ticket.resolved_at = None
            ticket.resolved_by_id = None
        self.db.flush()
        return ticket

    def queue(self, *, status: str | None = None,
              limit: int = 100) -> list[PlatformTicket]:
        q = select(PlatformTicket)
        if status:
            q = q.where(PlatformTicket.status == status)
        # Oldest first within the open states: a support queue sorted newest
        # first quietly starves the person who has waited longest.
        return list(self.db.scalars(
            q.order_by(PlatformTicket.last_reply_at.asc().nullslast())
            .limit(limit)))

    def counts(self) -> dict:
        rows = self.db.execute(
            select(PlatformTicket.status, func.count(PlatformTicket.id))
            .group_by(PlatformTicket.status)).all()
        by_status = {status: int(n) for status, n in rows}
        return {
            "by_status": by_status,
            "open": sum(by_status.get(s, 0) for s in OPEN_STATES),
            # What is actually waiting on the operator, which is the number
            # worth putting on a dashboard.
            "awaiting_reply": int(self.db.scalar(
                select(func.count(PlatformTicket.id)).where(
                    PlatformTicket.status.in_(OPEN_STATES),
                    PlatformTicket.last_reply_by == "owner")) or 0),
        }

    # ------------------------------------------------------------ helper --
    def _notify_owner(self, ticket: PlatformTicket, title: str,
                      message: str) -> None:
        try:
            self.notify.to_permission_holders(
                ticket.organization_id, "settings.manage",
                NotificationType.SYSTEM, title, message)
        except Exception:                        # noqa: BLE001
            log.exception("could not notify org %s about ticket %s",
                          ticket.organization_id, ticket.reference)


def payload(db: Session, ticket: PlatformTicket, *,
            include_internal: bool = False) -> dict:
    """
    Serialise a ticket.

    `include_internal` is False by default and must stay that way on every
    owner-facing path: an internal note is the operator talking to themselves,
    and the whole point is that the customer does not read it.
    """
    org = db.get(Organization, ticket.organization_id)
    return {
        "id": str(ticket.id),
        "reference": ticket.reference,
        "subject": ticket.subject,
        "category": ticket.category,
        "priority": ticket.priority,
        "status": ticket.status,
        "organization": org.name if org else "—",
        "organization_id": str(ticket.organization_id),
        "created_at": ticket.created_at.isoformat(),
        "last_reply_by": ticket.last_reply_by,
        "last_reply_at": (ticket.last_reply_at.isoformat()
                          if ticket.last_reply_at else None),
        "resolved_at": (ticket.resolved_at.isoformat()
                        if ticket.resolved_at else None),
        "messages": [{
            "id": str(m.id),
            "side": m.author_side,
            "author": m.author_name,
            "body": m.body,
            "internal": m.internal,
            "created_at": m.created_at.isoformat(),
        } for m in ticket.messages if include_internal or not m.internal],
    }
