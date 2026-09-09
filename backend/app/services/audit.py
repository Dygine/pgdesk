"""
Audit writing.

Deliberately a service rather than something a router does inline: the audit row
must be written in the same transaction as the change it describes, so that a
rolled-back operation leaves no misleading log entry behind.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.dependencies import CurrentScope
from app.models import AuditLog
from app.models.enums import AuditAction


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        *,
        scope: CurrentScope | None,
        module: str,
        action: AuditAction,
        description: str,
        entity_type: str | None = None,
        entity_id: str | uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        user_name: str | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            organization_id=organization_id or (scope.organization_id if scope else None),
            branch_id=branch_id,
            user_id=scope.user.id if scope else None,
            user_name=user_name or (scope.user.name if scope else "system"),
            module=module,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            description=description,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:300] or None,
        )
        self.db.add(entry)
        # No commit here on purpose - the caller's transaction owns it.
        return entry
