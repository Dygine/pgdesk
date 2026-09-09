"""
In-app notifications.

Deliberately the simplest thing that works: a row is written, and that is the
whole delivery mechanism for now. Email, SMS, WhatsApp and push all become
readers of this table later, so none of the producers scattered across the other
services will need to change when a channel is added - which is the reason to
write the record even though nothing yet sends it anywhere.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Customer, Notification, User
from app.models.enums import NotificationType


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------- writing
    def to_resident(self, resident: Customer, kind: str, title: str, message: str,
                    *, entity_type: str | None = None, entity_id: uuid.UUID | None = None,
                    link: str | None = None) -> Notification:
        row = Notification(
            organization_id=resident.organization_id, resident_id=resident.id,
            kind=kind, title=title, message=message,
            entity_type=entity_type, entity_id=entity_id, link=link)
        self.db.add(row)
        return row

    def to_user(self, user: User, kind: str, title: str, message: str,
                *, entity_type: str | None = None, entity_id: uuid.UUID | None = None,
                link: str | None = None) -> Notification:
        row = Notification(
            organization_id=user.organization_id, user_id=user.id,
            kind=kind, title=title, message=message,
            entity_type=entity_type, entity_id=entity_id, link=link)
        self.db.add(row)
        return row

    def to_permission_holders(self, organization_id: uuid.UUID, permission: str,
                              kind: str, title: str, message: str, *,
                              branch_id: uuid.UUID | None = None,
                              entity_type: str | None = None,
                              entity_id: uuid.UUID | None = None) -> int:
        """
        Notify whoever can act on this.

        Addressing by capability rather than by role name means a PG that
        invents its own roles still gets the right people told.
        """
        users = self.db.scalars(
            select(User).where(User.organization_id == organization_id,
                               User.is_active.is_(True))).all()
        sent = 0
        for user in users:
            if permission not in user.permission_codes:
                continue
            if branch_id and not user.all_branches:
                if branch_id not in {b.id for b in user.branches}:
                    continue
            self.to_user(user, kind, title, message,
                         entity_type=entity_type, entity_id=entity_id)
            sent += 1
        return sent

    # ------------------------------------------------------------- reading
    def _recipient_filter(self, *, user_id=None, resident_id=None):
        return (Notification.user_id == user_id if user_id
                else Notification.resident_id == resident_id)

    def list(self, organization_id: uuid.UUID, *, user_id=None, resident_id=None,
             unread_only: bool = False, page: int = 1, page_size: int = 25):
        stmt = select(Notification).where(
            Notification.organization_id == organization_id,
            self._recipient_filter(user_id=user_id, resident_id=resident_id))
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.db.scalars(
            stmt.order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)).all())
        return rows, total

    def unread_count(self, organization_id: uuid.UUID, *, user_id=None,
                     resident_id=None) -> int:
        return self.db.scalar(
            select(func.count(Notification.id)).where(
                Notification.organization_id == organization_id,
                Notification.read_at.is_(None),
                self._recipient_filter(user_id=user_id, resident_id=resident_id))) or 0

    def mark_read(self, notification_id: uuid.UUID, *, user_id=None,
                  resident_id=None) -> bool:
        row = self.db.scalars(
            select(Notification).where(
                Notification.id == notification_id,
                self._recipient_filter(user_id=user_id, resident_id=resident_id))).first()
        if row is None:
            # Silently false rather than 404: a notification you do not own
            # should not be distinguishable from one that does not exist.
            return False
        row.read_at = row.read_at or datetime.now(timezone.utc)
        return True

    def mark_all_read(self, organization_id: uuid.UUID, *, user_id=None,
                      resident_id=None) -> int:
        result = self.db.execute(
            update(Notification)
            .where(Notification.organization_id == organization_id,
                   Notification.read_at.is_(None),
                   self._recipient_filter(user_id=user_id, resident_id=resident_id))
            .values(read_at=datetime.now(timezone.utc)))
        return result.rowcount or 0
