"""
Request-scoped identity, tenant scope and authorisation.

The shape of this module is the whole security model:

    get_current_user   decodes the bearer token, loads the user
    get_current_scope  resolves organization_id + visible branch_ids + permissions
    require(...)       a dependency factory that 403s without the permission
    require_master     master-admin-only endpoints
    require_branch     rejects a branch_id the caller is not assigned to

Two rules that hold everywhere:

  1. organization_id is NEVER read from the request body, path or query. It comes
     from the authenticated identity only. `CurrentScope.organization_id` is the
     single source.
  2. A row belonging to another tenant is answered 404, never 403 - saying
     "forbidden" would confirm the row exists.

Milestone 2 added the issuing side (app/services/auth_service.py) and the
resident principal. Staff and residents authenticate through the same endpoint
but resolve to different dependencies, so a resident token can never satisfy
`get_current_user` and reach a staff endpoint.
"""
import uuid
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.models import Branch, Customer, Organization, User
from app.models.enums import CustomerStatus, OrganizationStatus, PrincipalKind, UserStatus
from app.permissions.catalog import MASTER_PERMISSIONS

# auto_error=False so a missing header raises our own envelope, not FastAPI's.
bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


@dataclass
class CurrentScope:
    """Everything a handler needs to answer safely. Built once per request."""

    user: User
    organization_id: uuid.UUID | None
    branch_ids: list[uuid.UUID] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)
    is_master: bool = False
    all_branches: bool = False

    def can(self, permission: str | list[str]) -> bool:
        if isinstance(permission, list):
            return any(p in self.permissions for p in permission)
        return permission in self.permissions

    def owns_branch(self, branch_id: uuid.UUID | None) -> bool:
        """
        Membership in `branch_ids`, always.

        `all_branches` is NOT a shortcut here. It means "every branch in my
        organisation", and `get_current_scope` has already expanded it to that
        concrete list. Treating the flag as a bypass would let an owner satisfy
        the branch guard for an arbitrary id - including one belonging to a
        different tenant - which is precisely the leak this method exists to
        prevent. The flag is a display hint; the list is the authority.
        """
        if branch_id is None:
            return True
        return branch_id in self.branch_ids


def _decode_access(credentials: HTTPAuthorizationCredentials | None) -> tuple[uuid.UUID, str]:
    """Shared first half of every authenticated request."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Not authenticated.")

    payload = decode_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise AuthenticationError("Your session has expired. Sign in again.")

    try:
        subject = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise AuthenticationError("That token is not valid.") from None

    # Defaults to "user" so tokens minted before the claim existed still work.
    return subject, payload.get("principal", PrincipalKind.USER.value)


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    """
    Staff and master admins only.

    A resident's token is rejected here rather than merely failing a permission
    check later: residents have no roles, so an empty permission set would 403
    anyway, but refusing at the identity layer means a resident token can never
    be mistaken for a staff one by code that forgets to check.
    """
    subject, kind = _decode_access(credentials)
    if kind != PrincipalKind.USER.value:
        raise PermissionDeniedError("This endpoint is not available to resident accounts.")

    user = db.get(User, subject)
    if user is None or not user.is_active or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("This account is no longer active.")
    return user


def get_current_customer(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Customer:
    """Resident-portal endpoints. A staff token is refused symmetrically."""
    subject, kind = _decode_access(credentials)
    if kind != PrincipalKind.CUSTOMER.value:
        raise PermissionDeniedError("This endpoint is only available to resident accounts.")

    customer = db.get(Customer, subject)
    if customer is None or not customer.can_sign_in:
        raise AuthenticationError("This account is no longer active.")
    return customer


def get_current_principal(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
):
    """
    Either kind. Used by the handful of endpoints both portals share - /auth/me,
    /auth/logout, /auth/change-password - and by nothing else.
    """
    from app.services.auth_service import Principal   # local import avoids a cycle

    subject, kind = _decode_access(credentials)

    if kind == PrincipalKind.CUSTOMER.value:
        customer = db.get(Customer, subject)
        if customer is None or not customer.can_sign_in:
            raise AuthenticationError("This account is no longer active.")
        return Principal(PrincipalKind.CUSTOMER, customer.id, customer.email or "",
                         customer.full_name, customer.organization_id, customer)

    user = db.get(User, subject)
    if user is None or not user.is_active or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("This account is no longer active.")
    return Principal(PrincipalKind.USER, user.id, user.email, user.name,
                     user.organization_id, user)


def get_current_scope(db: DbSession, user: Annotated[User, Depends(get_current_user)]) -> CurrentScope:
    if user.is_master_admin:
        # Master admins hold no Role row: `roles` is tenant data (organization_id
        # is NOT NULL), so a platform-wide role cannot exist without punching a
        # hole in tenant isolation. Their authority is the fixed master namespace,
        # resolved the same way the React AuthContext resolves it.
        return CurrentScope(
            user=user,
            organization_id=None,
            branch_ids=[],
            permissions=set(MASTER_PERMISSIONS),
            is_master=True,
            all_branches=False,
        )

    org = db.get(Organization, user.organization_id)
    if org is None:
        raise AuthenticationError("This account is not attached to an organisation.")
    if org.status in (OrganizationStatus.SUSPENDED, OrganizationStatus.CANCELLED):
        raise PermissionDeniedError(
            f"This organisation is {org.status.lower()}. Contact the platform administrator."
        )

    all_branches = user.all_branches
    if all_branches:
        branch_ids = list(
            db.scalars(select(Branch.id).where(Branch.organization_id == org.id)).all()
        )
    else:
        branch_ids = [b.id for b in user.branches]

    return CurrentScope(
        user=user,
        organization_id=org.id,
        branch_ids=branch_ids,
        permissions=user.permission_codes,
        is_master=False,
        all_branches=all_branches,
    )


CurrentUser = Annotated[User, Depends(get_current_user)]
Scope = Annotated[CurrentScope, Depends(get_current_scope)]


def require(*permissions: str):
    """
    Endpoint guard. Several arguments mean OR:

        _: None = Depends(require("rooms.edit"))
        _: None = Depends(require("payments.approve", "payments.edit"))
    """

    def dependency(scope: Scope) -> CurrentScope:
        if not scope.can(list(permissions)):
            raise PermissionDeniedError(
                "Your role does not include the permission needed for this action "
                f"({' or '.join(permissions)})."
            )
        return scope

    return dependency


def require_role(*role_names: str):
    """
    Guard by role name. Prefer `require(...)` on a permission wherever possible -
    permissions survive a customer renaming their roles, role names do not.
    """
    def dependency(scope: Scope) -> CurrentScope:
        held = {r.name for r in scope.user.roles}
        if not held & set(role_names):
            raise PermissionDeniedError(
                f"This action is restricted to: {', '.join(role_names)}."
            )
        return scope

    return dependency


def require_master(scope: Scope) -> CurrentScope:
    """Master-admin-only. A PG owner hitting these gets 403."""
    if not scope.is_master:
        raise PermissionDeniedError("This endpoint is restricted to platform administrators.")
    return scope


def require_tenant(scope: Scope) -> CurrentScope:
    """Tenant-only. A master admin has no organization scope, so it is refused."""
    if scope.is_master or scope.organization_id is None:
        raise PermissionDeniedError(
            "This endpoint operates inside an organisation. Platform administrators "
            "should use the master endpoints."
        )
    return scope


def require_branch(scope: CurrentScope, branch_id: uuid.UUID | None) -> None:
    """
    Call from a handler whenever a branch_id arrives from the client. Never trust
    a branch just because it belongs to the right organization.
    """
    if not scope.owns_branch(branch_id):
        raise PermissionDeniedError("You do not have access to that branch.")


# The brief names these; they are the same objects under a longer name.
require_permission = require
require_authenticated_user = get_current_user

CurrentCustomer = Annotated[Customer, Depends(get_current_customer)]


def client_ip(request: Request) -> str | None:
    """Behind a proxy the real address is in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
