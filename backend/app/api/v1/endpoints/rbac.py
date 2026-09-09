"""Roles, permissions, users and branch assignment."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.core.dependencies import CurrentScope, DbSession, require, require_tenant
from app.core.responses import ok, paginated
from app.models import Role, User
from app.permissions.catalog import ACTION_LABELS, PERMISSION_MODULES
from app.schemas.rbac import (
    BranchAssignment, RoleCreate, RoleUpdate, UserCreate, UserUpdate,
)
from app.services.rbac_service import RbacService

router = APIRouter(tags=["rbac"])
Tenant = Annotated[CurrentScope, Depends(require_tenant)]


def _svc(db, scope) -> RbacService:
    return RbacService(db, scope)


def _role(db, role: Role) -> dict:
    holders = db.scalar(
        select(func.count(User.id)).join(User.roles).where(Role.id == role.id)) or 0
    return {
        "id": str(role.id), "name": role.name, "description": role.description,
        "is_system_role": role.is_system_role, "all_branches": role.all_branches,
        "permissions": role.permission_codes, "user_count": holders,
    }


def _user(u: User) -> dict:
    return {
        "id": str(u.id), "name": u.name, "email": u.email, "phone": u.phone,
        "employee_id": u.employee_id, "status": u.status, "is_active": u.is_active,
        "must_change_password": u.must_change_password,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "created_at": u.created_at.isoformat(),
        "roles": [{"id": str(r.id), "name": r.name, "all_branches": r.all_branches}
                  for r in u.roles],
        "role": ({"id": str(u.roles[0].id), "name": u.roles[0].name} if u.roles else None),
        "branches": [{"id": str(b.id), "name": b.name, "code": b.code} for b in u.branches],
        "all_branches": u.all_branches,
        "permissions": sorted(u.permission_codes),
    }


# --------------------------------------------------------------- catalogue
@router.get("/permissions", summary="The permission catalogue")
def list_permissions(db: DbSession, scope: Tenant,
                     _: None = Depends(require("roles.view", "users.view"))) -> dict:
    """
    Grouped by module, which is how the role editor renders it.

    Identical to the React app's `src/data/permissions.js`; a test parses that
    file and fails if the two ever drift.
    """
    rows = _svc(db, scope).list_permissions()
    by_module = {}
    for p in rows:
        by_module.setdefault(p.module, []).append(
            {"id": str(p.id), "code": p.code, "action": p.action, "label": p.label})
    return ok({
        "modules": [
            {"key": m["key"], "label": m["label"], "actions": m["actions"],
             "permissions": by_module.get(m["key"], [])}
            for m in PERMISSION_MODULES
        ],
        "action_labels": ACTION_LABELS,
        "all": [p.code for p in rows],
        "count": len(rows),
    })


# ------------------------------------------------------------------- roles
@router.get("/roles", summary="List roles")
def list_roles(db: DbSession, scope: Tenant,
               _: None = Depends(require("roles.view"))) -> dict:
    return ok([_role(db, r) for r in _svc(db, scope).list_roles()])


@router.get("/roles/{role_id}", summary="Role detail")
def get_role(role_id: uuid.UUID, db: DbSession, scope: Tenant,
             _: None = Depends(require("roles.view"))) -> dict:
    return ok(_role(db, _svc(db, scope).get_role(role_id)))


@router.post("/roles", status_code=status.HTTP_201_CREATED, summary="Create a role")
def create_role(body: RoleCreate, db: DbSession, scope: Tenant,
                _: None = Depends(require("roles.create"))) -> dict:
    role = _svc(db, scope).create_role(body.model_dump())
    db.commit()
    return ok(_role(db, role), message=f"{role.name} created.")


@router.patch("/roles/{role_id}", summary="Edit a role or its permissions")
def update_role(role_id: uuid.UUID, body: RoleUpdate, db: DbSession, scope: Tenant,
                _: None = Depends(require("roles.edit"))) -> dict:
    """
    Permission changes take effect on the holders' next request - permissions are
    read from the database per request rather than baked into their token.
    """
    role = _svc(db, scope).update_role(role_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok(_role(db, role), message=f"{role.name} updated.")


@router.delete("/roles/{role_id}", summary="Delete a role")
def delete_role(role_id: uuid.UUID, db: DbSession, scope: Tenant,
                _: None = Depends(require("roles.delete"))) -> dict:
    _svc(db, scope).delete_role(role_id)
    db.commit()
    return ok(None, message="Role deleted.")


# ------------------------------------------------------------------- users
@router.get("/users", summary="List users")
def list_users(db: DbSession, scope: Tenant,
               _: None = Depends(require("users.view", "staff.view")),
               search: str | None = None,
               role_id: uuid.UUID | None = None,
               branch_id: uuid.UUID | None = None,
               status_filter: str | None = Query(default=None, alias="status"),
               page: int = Query(default=1, ge=1),
               page_size: int = Query(default=25, ge=1, le=100)) -> dict:
    rows, total = _svc(db, scope).list_users(
        search=search, role_id=role_id, branch_id=branch_id,
        status=status_filter, page=page, page_size=page_size)
    return paginated([_user(u) for u in rows], page, page_size, total)


@router.get("/users/{user_id}", summary="User detail")
def get_user(user_id: uuid.UUID, db: DbSession, scope: Tenant,
             _: None = Depends(require("users.view", "staff.view"))) -> dict:
    return ok(_user(_svc(db, scope).get_user(user_id)))


@router.post("/users", status_code=status.HTTP_201_CREATED, summary="Create a staff user")
def create_user(body: UserCreate, db: DbSession, scope: Tenant,
                _: None = Depends(require("users.create"))) -> dict:
    """
    Counts against the plan's user limit. The temporary password is returned
    once, here; the account is flagged `must_change_password`.
    """
    user, temporary = _svc(db, scope).create_user(body.model_dump())
    db.commit()
    payload = _user(user)
    payload["credentials"] = {
        "name": user.name, "email": user.email,
        "temporary_password": temporary, "must_change_password": True,
    }
    return ok(payload, message=f"{user.name} created. Share the password securely.")


@router.patch("/users/{user_id}", summary="Edit a user, their role or their branches")
def update_user(user_id: uuid.UUID, body: UserUpdate, db: DbSession, scope: Tenant,
                _: None = Depends(require("users.edit"))) -> dict:
    user = _svc(db, scope).update_user(user_id, body.model_dump(exclude_unset=True))
    db.commit()
    return ok(_user(user), message=f"{user.name} updated.")


@router.delete("/users/{user_id}", summary="Deactivate a user")
def deactivate_user(user_id: uuid.UUID, db: DbSession, scope: Tenant,
                    _: None = Depends(require("users.delete", "users.deactivate"))) -> dict:
    user = _svc(db, scope).deactivate_user(user_id)
    db.commit()
    return ok(_user(user), message=f"{user.name} deactivated.")


@router.post("/users/{user_id}/reset-password", summary="Issue a temporary password")
def reset_password(user_id: uuid.UUID, db: DbSession, scope: Tenant,
                   _: None = Depends(require("users.edit"))) -> dict:
    user, temporary = _svc(db, scope).reset_user_password(user_id)
    db.commit()
    return ok({"name": user.name, "email": user.email,
               "temporary_password": temporary, "must_change_password": True},
              message="Temporary password issued.")


# -------------------------------------------------------- branch assignment
@router.get("/user-branches/{user_id}", summary="A user's branch assignments")
def get_user_branches(user_id: uuid.UUID, db: DbSession, scope: Tenant,
                      _: None = Depends(require("users.view"))) -> dict:
    user = _svc(db, scope).get_user(user_id)
    return ok({
        "user_id": str(user.id), "all_branches": user.all_branches,
        "branches": [{"id": str(b.id), "name": b.name, "code": b.code}
                     for b in user.branches],
    })


@router.put("/user-branches/{user_id}", summary="Replace a user's branch assignments")
def set_user_branches(user_id: uuid.UUID, body: BranchAssignment, db: DbSession,
                      scope: Tenant, _: None = Depends(require("users.edit"))) -> dict:
    """
    A user may hold any number of branches. An owner can only hand out branches
    they can reach themselves.
    """
    user = _svc(db, scope).set_user_branches(user_id, body.branch_ids)
    db.commit()
    return ok(_user(user), message=f"{user.name}'s branch access updated.")
