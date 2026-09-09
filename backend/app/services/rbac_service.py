"""
Roles, permissions, users and branch assignment - the owner's side of RBAC.

The permission catalogue is platform-wide and read-only. Roles are tenant data
and fully editable, which is the point: a PG owner invents whatever roles their
operation needs rather than choosing from Admin/Manager/Staff.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import CurrentScope
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.models import Branch, Permission, Role, User
from app.models.enums import AuditAction, UserStatus
from app.permissions.engine import expand, unknown_permissions
from app.services.audit import AuditService
from app.services.organization_service import generate_temporary_password
from app.services.subscription_limits import SubscriptionLimitService


class RbacService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope
        self.audit = AuditService(db)
        self.limits = SubscriptionLimitService(db)

    @property
    def org_id(self) -> uuid.UUID:
        return self.scope.organization_id

    # --------------------------------------------------------- permissions
    def list_permissions(self) -> list[Permission]:
        return list(self.db.scalars(
            select(Permission).where(Permission.is_master.is_(False))
            .order_by(Permission.module, Permission.action)
        ).all())

    def _resolve_permissions(self, codes: list[str]) -> list[Permission]:
        bad = unknown_permissions(codes)
        if bad:
            raise ConflictError(f"Unknown permissions: {', '.join(sorted(bad))}")
        wanted = expand(codes)
        rows = list(self.db.scalars(
            select(Permission).where(Permission.code.in_(wanted),
                                     Permission.is_master.is_(False))
        ).all())
        # A tenant role can never hold a master.* permission, so silently
        # dropping them here is deliberate rather than lossy.
        return rows

    # --------------------------------------------------------------- roles
    def list_roles(self) -> list[Role]:
        return list(self.db.scalars(
            select(Role).options(selectinload(Role.permissions))
            .where(Role.organization_id == self.org_id).order_by(Role.name)
        ).all())

    def get_role(self, role_id: uuid.UUID) -> Role:
        role = self.db.scalars(
            select(Role).options(selectinload(Role.permissions))
            .where(Role.id == role_id, Role.organization_id == self.org_id)
        ).first()
        if role is None:
            raise NotFoundError("Role not found.")
        return role

    def create_role(self, data: dict) -> Role:
        name = data["name"].strip()
        if self.db.scalars(select(Role).where(
            Role.organization_id == self.org_id, func.lower(Role.name) == name.lower()
        )).first():
            raise ConflictError(f"A role called {name} already exists.")

        role = Role(
            organization_id=self.org_id, name=name,
            description=data.get("description"),
            all_branches=bool(data.get("all_branches")),
            is_system_role=False,
        )
        role.permissions = self._resolve_permissions(data.get("permissions") or [])
        self.db.add(role)
        self.db.flush()
        self.audit.record(
            scope=self.scope, module="Roles", action=AuditAction.CREATE,
            description=f"Created role {name} with {len(role.permissions)} permissions",
            entity_type="role", entity_id=role.id,
        )
        return role

    def update_role(self, role_id: uuid.UUID, data: dict) -> Role:
        role = self.get_role(role_id)

        if role.is_system_role and ("permissions" in data or "all_branches" in data):
            # The Owner role is what stops an organisation locking itself out.
            raise PermissionDeniedError(
                "The owner role is a system role. Its permissions cannot be changed - "
                "duplicate it if you need a version you can trim."
            )

        if data.get("name"):
            new_name = data["name"].strip()
            clash = self.db.scalars(select(Role).where(
                Role.organization_id == self.org_id,
                func.lower(Role.name) == new_name.lower(), Role.id != role.id,
            )).first()
            if clash:
                raise ConflictError(f"A role called {new_name} already exists.")
            role.name = new_name

        if "description" in data and data["description"] is not None:
            role.description = data["description"]
        if "all_branches" in data and data["all_branches"] is not None:
            role.all_branches = bool(data["all_branches"])
        if "permissions" in data and data["permissions"] is not None:
            role.permissions = self._resolve_permissions(data["permissions"])

        holders = self.db.scalar(
            select(func.count(User.id)).join(User.roles).where(Role.id == role.id)) or 0
        self.audit.record(
            scope=self.scope, module="Roles", action=AuditAction.UPDATE,
            description=(f"Updated role {role.name} "
                         f"({len(role.permissions)} permissions, {holders} holders)"),
            entity_type="role", entity_id=role.id,
        )
        return role

    def delete_role(self, role_id: uuid.UUID) -> None:
        role = self.get_role(role_id)
        if role.is_system_role:
            raise PermissionDeniedError("System roles cannot be deleted.")
        holders = self.db.scalar(
            select(func.count(User.id)).join(User.roles).where(Role.id == role.id)) or 0
        if holders:
            raise ConflictError(
                f"{holders} user{'s' if holders != 1 else ''} still hold this role. "
                "Move them to another role first."
            )
        self.audit.record(
            scope=self.scope, module="Roles", action=AuditAction.DELETE,
            description=f"Deleted role {role.name}", entity_type="role", entity_id=role.id,
        )
        self.db.delete(role)

    # --------------------------------------------------------------- users
    def list_users(self, *, search=None, role_id=None, status=None,
                   branch_id=None, page=1, page_size=25):
        stmt = (
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions),
                     selectinload(User.branches))
            .where(User.organization_id == self.org_id)
        )
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(User.name.ilike(like), User.email.ilike(like),
                                  User.phone.ilike(like)))
        if status and status != "all":
            stmt = stmt.where(User.status == status)
        if role_id:
            stmt = stmt.where(User.id.in_(
                select(User.id).join(User.roles).where(Role.id == role_id)))
        if branch_id:
            stmt = stmt.where(User.id.in_(
                select(User.id).join(User.branches).where(Branch.id == branch_id)))

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(self.db.scalars(
            stmt.order_by(User.name).offset((page - 1) * page_size).limit(page_size)
        ).all())
        return rows, total

    def get_user(self, user_id: uuid.UUID) -> User:
        user = self.db.scalars(
            select(User).options(selectinload(User.roles), selectinload(User.branches))
            .where(User.id == user_id, User.organization_id == self.org_id)
        ).first()
        if user is None:
            raise NotFoundError("User not found.")
        return user

    def _resolve_branches(self, branch_ids: list[uuid.UUID]) -> list[Branch]:
        if not branch_ids:
            return []
        rows = list(self.db.scalars(
            select(Branch).where(Branch.organization_id == self.org_id,
                                 Branch.id.in_(branch_ids))
        ).all())
        if len(rows) != len(set(branch_ids)):
            raise NotFoundError("One or more of those branches do not exist.")
        # An owner may only hand out branches they themselves can reach.
        for branch in rows:
            if not self.scope.owns_branch(branch.id):
                raise PermissionDeniedError(
                    f"Branch access denied. You are not assigned to {branch.name}."
                )
        return rows

    def create_user(self, data: dict) -> tuple[User, str]:
        self.limits.can_create_user(self.org_id)

        email = data["email"].strip().lower()
        if self.db.scalars(select(User).where(User.email == email)).first():
            raise ConflictError("An account with that email address already exists.")

        role = self.get_role(data["role_id"])
        branches = self._resolve_branches(data.get("branch_ids") or [])
        if not role.all_branches and not branches:
            raise ConflictError(
                "This role does not see every branch, so the user needs at least "
                "one branch assignment."
            )

        temporary_password = data.get("password") or generate_temporary_password()
        user = User(
            organization_id=self.org_id, name=data["name"].strip(), email=email,
            phone=data.get("phone"), employee_id=data.get("employee_id"),
            password_hash=hash_password(temporary_password),
            must_change_password=True,
            status=data.get("status") or UserStatus.ACTIVE,
            is_active=(data.get("status") or UserStatus.ACTIVE) == UserStatus.ACTIVE,
        )
        user.roles = [role]
        user.branches = branches
        self.db.add(user)
        self.db.flush()

        self.audit.record(
            scope=self.scope, module="Users", action=AuditAction.CREATE,
            description=(f"Created user {user.name} as {role.name} "
                         f"({'all branches' if role.all_branches else f'{len(branches)} branches'})"),
            entity_type="user", entity_id=user.id,
        )
        return user, temporary_password

    def update_user(self, user_id: uuid.UUID, data: dict) -> User:
        user = self.get_user(user_id)
        changes = []

        for field in ("name", "phone", "employee_id"):
            if data.get(field) is not None:
                setattr(user, field, data[field])

        if data.get("status") is not None:
            user.status = data["status"]
            user.is_active = data["status"] == UserStatus.ACTIVE
            changes.append(f"status \u2192 {data['status']}")

        if data.get("role_id") is not None:
            role = self.get_role(data["role_id"])
            if user.id == self.scope.user.id and not role.all_branches:
                # Removing your own org-wide access mid-session is the classic
                # way an owner locks themselves out.
                raise ConflictError("You cannot move yourself to a narrower role.")
            user.roles = [role]
            changes.append(f"role \u2192 {role.name}")

        if data.get("branch_ids") is not None:
            branches = self._resolve_branches(data["branch_ids"])
            user.branches = branches
            changes.append(f"branches \u2192 {len(branches)}")

        self.audit.record(
            scope=self.scope, module="Users", action=AuditAction.UPDATE,
            description=f"Updated {user.name}" + (f": {', '.join(changes)}" if changes else ""),
            entity_type="user", entity_id=user.id,
        )
        return user

    def set_user_branches(self, user_id: uuid.UUID, branch_ids: list[uuid.UUID]) -> User:
        user = self.get_user(user_id)
        branches = self._resolve_branches(branch_ids)
        user.branches = branches
        self.audit.record(
            scope=self.scope, module="Users", action=AuditAction.ASSIGN,
            description=(f"{user.name} assigned to "
                         + (", ".join(b.name for b in branches) or "no branches")),
            entity_type="user", entity_id=user.id,
        )
        return user

    def deactivate_user(self, user_id: uuid.UUID) -> User:
        user = self.get_user(user_id)
        if user.id == self.scope.user.id:
            raise ConflictError("You cannot deactivate your own account.")
        user.status = UserStatus.DEACTIVATED
        user.is_active = False
        self.audit.record(
            scope=self.scope, module="Users", action=AuditAction.UPDATE,
            description=f"Deactivated {user.name}", entity_type="user", entity_id=user.id,
        )
        return user

    def reset_user_password(self, user_id: uuid.UUID) -> tuple[User, str]:
        user = self.get_user(user_id)
        temporary_password = generate_temporary_password()
        user.password_hash = hash_password(temporary_password)
        user.must_change_password = True
        self.audit.record(
            scope=self.scope, module="Users", action=AuditAction.UPDATE,
            description=f"Issued a temporary password for {user.name}",
            entity_type="user", entity_id=user.id,
        )
        return user, temporary_password
