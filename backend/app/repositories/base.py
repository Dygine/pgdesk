"""
Generic tenant-scoped repository.

Every read path for tenant data goes through `scoped()`, which applies the
organization filter unconditionally. A handler cannot forget it, because the
handler never builds the base query itself.
"""
import uuid
from typing import Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.dependencies import CurrentScope
from app.core.exceptions import TenantIsolationError
from app.models.base import BranchMixin, TenantMixin

ModelT = TypeVar("ModelT", bound=Base)


class TenantRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope
        if not issubclass(self.model, TenantMixin):
            raise TypeError(
                f"{self.model.__name__} is not tenant data; use a plain query instead."
            )

    # ------------------------------------------------------------------ read
    def scoped(self) -> Select:
        """The only entry point. Organization filter always; branch filter when applicable."""
        stmt = select(self.model).where(self.model.organization_id == self.scope.organization_id)
        if issubclass(self.model, BranchMixin):
            # branch_ids is already the full org list when the role grants every
            # branch, so this filter is applied unconditionally rather than being
            # skipped for owners. One code path is easier to keep correct than two.
            stmt = stmt.where(
                (self.model.branch_id.is_(None))
                | (self.model.branch_id.in_(self.scope.branch_ids))
            )
        return stmt

    def get_or_404(self, entity_id: uuid.UUID) -> ModelT:
        obj = self.db.scalars(self.scoped().where(self.model.id == entity_id)).first()
        if obj is None:
            # Deliberately indistinguishable from "does not exist" - see TenantIsolationError.
            raise TenantIsolationError(f"{self.model.__name__} not found.")
        return obj

    def count(self, stmt: Select | None = None) -> int:
        base = stmt if stmt is not None else self.scoped()
        return self.db.scalar(select(func.count()).select_from(base.subquery())) or 0

    def paginate(self, stmt: Select, page: int, page_size: int) -> tuple[list[ModelT], int]:
        total = self.count(stmt)
        rows = list(self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all())
        return rows, total

    # ----------------------------------------------------------------- write
    def add(self, obj: ModelT) -> ModelT:
        """Stamps the tenant from the session, never from the payload."""
        obj.organization_id = self.scope.organization_id
        self.db.add(obj)
        self.db.flush()
        return obj
