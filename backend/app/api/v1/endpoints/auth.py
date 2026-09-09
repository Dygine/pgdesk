"""
Authentication endpoints.

The router is thin on purpose: it reads the request, calls AuthService, commits,
and shapes the envelope. Every rule about who may sign in lives in the service.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import settings
from app.core.dependencies import DbSession, get_current_principal
from app.core.exceptions import AppError, AuthenticationError
from app.core.responses import ok
from app.core.security import decode_token
from app.core.session_cookie import (
    clear_refresh_cookie, read_refresh_token, require_csrf_header,
    set_refresh_cookie,
)
from app.models.enums import AuditAction
from app.schemas.auth import (
    ChangePasswordRequest, LoginRequest, LogoutRequest, RefreshRequest,
)
from app.services.audit import AuditService
from app.services.auth_service import AuthService, Principal
from app.services.login_throttle import LoginThrottle

router = APIRouter(prefix="/auth", tags=["auth"])

CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def _client(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else None
    )
    return request.headers.get("user-agent"), ip


@router.post("/login", summary="Sign in", status_code=status.HTTP_200_OK)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> dict:
    """
    Staff, master admins and residents all sign in here.

    A wrong email and a wrong password return the same 401 with the same message,
    so this endpoint cannot be used to discover which addresses hold accounts.

    The refresh token leaves in an HttpOnly cookie, not in the body, so a script
    injected into the page cannot read the long-lived credential. The access
    token is returned in the body for the client to hold in memory.
    """
    service = AuthService(db)
    audit = AuditService(db)
    throttle = LoginThrottle(db)
    ua, ip = _client(request)
    identifier = body.email.strip().lower()

    # Spent budget short-circuits before any password work, so a locked account
    # costs an attacker a cheap 429 rather than a full Argon2 verify.
    throttle.check(identifier, ip)

    try:
        principal = service.authenticate(body.email, body.password)
    except AppError as exc:
        # Recorded for both the lockout counter and the audit trail. The reason
        # is the exception's own code, never the password that was tried.
        throttle.record(identifier, ip, successful=False, reason=exc.code)
        audit.record(
            scope=None, module="Auth", action=AuditAction.LOGIN_FAILED,
            description=f"Failed sign-in for {identifier} ({exc.code})",
            entity_type="login", user_name=identifier,
            ip_address=ip, user_agent=ua,
        )
        # Committed even though the request fails: a counter rolled back with
        # the error would count nothing, and the lockout would never trigger.
        db.commit()
        raise

    access, refresh = service.issue_tokens(principal, user_agent=ua, ip=ip)
    described = service.describe(principal)

    throttle.record(identifier, ip, successful=True)
    throttle.clear(identifier)

    audit.record(
        scope=None, module="Auth", action=AuditAction.LOGIN,
        description=f"{described.name} signed in ({described.portal} portal)",
        entity_type=principal.kind.value, entity_id=principal.id,
        organization_id=principal.organization_id,
        user_name=described.name, ip_address=ip, user_agent=ua,
    )
    db.commit()

    set_refresh_cookie(response, refresh)

    payload = {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": described.model_dump(mode="json"),
    }
    if settings.expose_refresh_token_in_body:
        payload["refresh_token"] = refresh
    return ok(payload, message=f"Signed in as {described.name}.")


@router.post("/refresh", summary="Exchange a refresh token for a new access token")
def refresh(request: Request, response: Response, db: DbSession,
            body: RefreshRequest | None = None) -> dict:
    """
    Refresh tokens are single-use. Each call revokes the token presented and
    returns a new pair; replaying an old one signs every session out.

    The token is read from the HttpOnly cookie. A body value is still accepted
    for non-browser clients, which have no cookie jar - the cookie wins when
    both are present, so a stale pasted token cannot displace a live session.
    """
    require_csrf_header(request)

    service = AuthService(db)
    ua, ip = _client(request)

    presented = read_refresh_token(request, body.refresh_token if body else None)
    if not presented:
        raise AuthenticationError("No session to refresh. Sign in again.")

    access, new_refresh, principal = service.rotate_refresh_token(
        presented, user_agent=ua, ip=ip
    )
    described = service.describe(principal)
    db.commit()

    set_refresh_cookie(response, new_refresh)

    payload = {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": described.model_dump(mode="json"),
    }
    if settings.expose_refresh_token_in_body:
        payload["refresh_token"] = new_refresh
    return ok(payload)


@router.post("/logout", summary="Sign out")
def logout(
    request: Request, response: Response, db: DbSession, principal: CurrentPrincipal,
    body: LogoutRequest | None = None,
) -> dict:
    """
    Revokes this session, or every session for the account when the caller asks
    for that. Always succeeds - an already-revoked token is not an error.

    The cookie is cleared either way. Leaving it behind would mean the browser
    keeps presenting a revoked token on every refresh attempt, which reads to
    the user as a sign-out that did not work.
    """
    service = AuthService(db)
    presented = read_refresh_token(request, body.refresh_token if body else None)
    all_sessions = bool(body and body.all_sessions)

    if presented and not all_sessions:
        service.revoke(presented)
        message = "Signed out."
    else:
        count = service.revoke_all_sessions(principal)
        message = f"Signed out of {count} session{'' if count == 1 else 's'}."

    clear_refresh_cookie(response)

    ua, ip = _client(request)
    AuditService(db).record(
        scope=None, module="Auth", action=AuditAction.LOGOUT,
        description=f"{principal.name} signed out",
        entity_type=principal.kind.value, entity_id=principal.id,
        organization_id=principal.organization_id,
        user_name=principal.name, ip_address=ip, user_agent=ua,
    )
    db.commit()
    return ok(None, message=message)


@router.get("/me", summary="The authenticated account")
def me(db: DbSession, principal: CurrentPrincipal) -> dict:
    """
    The single source of identity for the client.

    Permissions are returned here rather than packed into the JWT so that a role
    change takes effect on the next request instead of the next login.
    """
    return ok(AuthService(db).describe(principal).model_dump(mode="json"))


@router.post("/change-password", summary="Change your own password")
def change_password(
    body: ChangePasswordRequest, db: DbSession, principal: CurrentPrincipal
) -> dict:
    """
    Also the mechanism behind `must_change_password`: an owner created with a
    temporary password clears the flag by calling this.

    Every other session is revoked, since the usual reason to change a password
    is that someone else may know the old one.
    """
    service = AuthService(db)
    service.change_password(principal, body.current_password, body.new_password)

    AuditService(db).record(
        scope=None, module="Auth", action=AuditAction.UPDATE,
        description=f"{principal.name} changed their password",
        entity_type=principal.kind.value, entity_id=principal.id,
        organization_id=principal.organization_id, user_name=principal.name,
    )
    db.commit()
    return ok(None, message="Password changed. Sign in again on your other devices.")
