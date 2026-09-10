"""
Authentication endpoints.

The router is thin on purpose: it reads the request, calls AuthService, commits,
and shapes the envelope. Every rule about who may sign in lives in the service.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import settings
from app.core.dependencies import DbSession, get_current_principal
from app.core.exceptions import (
    AppError, AuthenticationError, RateLimitedError,
)
from app.core.responses import ok
from app.core.security import decode_token
from app.core.session_cookie import (
    clear_refresh_cookie, read_refresh_token, require_csrf_header,
    set_refresh_cookie,
)
from app.models.enums import AuditAction, PrincipalKind
from app.schemas.auth import (
    ChangePasswordRequest, ForgotPasswordRequest, LoginRequest, LogoutRequest,
    QrLoginRequest, RefreshRequest, ResetPasswordRequest, VerifyOtpRequest,
)
from app.services.audit import AuditService
from app.services.auth_service import AuthService, Principal
from app.services.login_code_service import LoginCodeService
from app.services.login_throttle import LoginThrottle
from app.services.otp_service import OtpError
from app.services.password_reset_service import (
    NEUTRAL_REPLY, PasswordResetService,
)

router = APIRouter(prefix="/auth", tags=["auth"])

CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


#: Sent by the installed app. Its presence means two things: give this session
#: the long lifetime, and return the refresh token in the body.
#:
#: The body matters as much as the lifetime. A Capacitor app is served from
#: https://localhost while the API is on another domain, so every call is
#: cross-site and a SameSite=Lax cookie is never attached - the session would
#: die thirty minutes after login with no visible cause. Handing the token to
#: the app to keep in its own private storage sidesteps the cookie entirely.
NATIVE_CLIENT_HEADER = "X-PGDesk-Client"


def _is_native(request: Request) -> bool:
    return (request.headers.get(NATIVE_CLIENT_HEADER) or "").lower() == "native"


def _client(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else None
    )
    return request.headers.get("user-agent"), ip


def _session_payload(service: AuthService, principal: Principal, request: Request,
                     response: Response) -> dict:
    """
    Issue a token pair for the device making this request, shaped like /login.

    Shared by the QR sign-in and by change-password, which both end with "this
    phone is now signed in" and must not drift from /login in what they return.
    """
    ua, ip = _client(request)
    native = _is_native(request)
    access, refresh = service.issue_tokens(principal, user_agent=ua, ip=ip, native=native)
    set_refresh_cookie(response, refresh)
    payload = {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": service.describe(principal).model_dump(mode="json"),
    }
    if native or settings.expose_refresh_token_in_body:
        payload["refresh_token"] = refresh
    return payload


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

    native = _is_native(request)
    access, refresh = service.issue_tokens(principal, user_agent=ua, ip=ip, native=native)
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
    if native or settings.expose_refresh_token_in_body:
        payload["refresh_token"] = refresh
    return ok(payload, message=f"Signed in as {described.name}.")


@router.post("/qr-login", summary="Sign in by scanning a one-time QR code")
def qr_login(body: QrLoginRequest, request: Request, response: Response,
             db: DbSession) -> dict:
    """
    The resident's first sign-in, without typing a temporary password.

    The PG shows a QR carrying a 30-minute, single-use key. Scanning it here
    signs the resident in with `must_change_password` still set, so the app
    goes straight to "set your password" - see app/models/login_code.py.

    Throttled by address only. There is no email to count against, and the key
    is 192 random bits, so this is about a source spraying junk, not guessing.
    """
    ua, ip = _client(request)
    throttle = LoginThrottle(db)
    throttle.check_ip(ip)

    try:
        customer = LoginCodeService(db).redeem(body.code, ip=ip, user_agent=ua)
    except AppError as exc:
        throttle.record("qr-login", ip, successful=False, reason=exc.code)
        AuditService(db).record(
            scope=None, module="Auth", action=AuditAction.LOGIN_FAILED,
            description=f"Failed QR sign-in ({exc.code})",
            entity_type="login", user_name="qr-login",
            ip_address=ip, user_agent=ua,
        )
        db.commit()      # the counter and the audit line must survive the refusal
        raise

    service = AuthService(db)
    principal = Principal(
        kind=PrincipalKind.CUSTOMER, id=customer.id, email=customer.email or "",
        name=customer.full_name, organization_id=customer.organization_id, obj=customer)
    payload = _session_payload(service, principal, request, response)

    AuditService(db).record(
        scope=None, module="Auth", action=AuditAction.LOGIN,
        description=f"{customer.full_name} signed in with a QR code (customer portal)",
        entity_type=principal.kind.value, entity_id=principal.id,
        organization_id=principal.organization_id,
        user_name=customer.full_name, ip_address=ip, user_agent=ua,
    )
    db.commit()
    return ok(payload, message=f"Signed in as {customer.full_name}.")


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

    native = _is_native(request)
    access, new_refresh, principal = service.rotate_refresh_token(
        presented, user_agent=ua, ip=ip, native=native
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
    # Native clients always get the token back: they hold it themselves because
    # the cookie cannot reach them. Browsers do not, because the cookie works
    # there and is HttpOnly, which is strictly safer than a value JavaScript can
    # read.
    if native or settings.expose_refresh_token_in_body:
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
    body: ChangePasswordRequest, request: Request, response: Response,
    db: DbSession, principal: CurrentPrincipal
) -> dict:
    """
    Also the mechanism behind `must_change_password`: an owner created with a
    temporary password, or a resident who signed in with a QR, clears the flag
    by calling this - without the current password in that one state.

    Every session is revoked, since the usual reason to change a password is
    that someone else may know the old one. The device that made this request
    then gets a fresh pair in the reply. Before, it was revoked along with the
    rest and signed out silently when its access token expired half an hour
    later, which read as a bug rather than a security measure.
    """
    first_time = bool(principal.obj.must_change_password)
    service = AuthService(db)
    service.change_password(principal, body.current_password, body.new_password)

    AuditService(db).record(
        scope=None, module="Auth", action=AuditAction.UPDATE,
        description=(f"{principal.name} set their password" if first_time
                     else f"{principal.name} changed their password"),
        entity_type=principal.kind.value, entity_id=principal.id,
        organization_id=principal.organization_id, user_name=principal.name,
    )
    payload = _session_payload(service, principal, request, response)
    db.commit()
    return ok(payload, message=("Password set." if first_time else
                                "Password changed. Your other devices have been signed out."))


# ----------------------------------------------------------- password reset
@router.post("/forgot-password", summary="Ask for a reset code by email")
def forgot_password(body: ForgotPasswordRequest, request: Request,
                    db: DbSession) -> dict:
    """
    Always answers the same thing.

    Whether or not the address has an account, the reply is identical. Saying
    "no such user" would turn this into a free tool for discovering which
    residents and staff have accounts here, and a list of real users at a known
    PG is worth money to somebody.
    """
    _, ip = _client(request)
    try:
        PasswordResetService(db).request_code(body.email, ip=ip)
    except OtpError as exc:
        # Rate limits are reported. They describe the caller's own behaviour
        # against an address they typed themselves, so they leak nothing - and
        # silently swallowing them would leave someone tapping a dead button.
        db.commit()
        raise RateLimitedError(str(exc)) from None
    db.commit()
    return ok({"sent": True}, message=NEUTRAL_REPLY)


@router.post("/verify-otp", summary="Check a reset code")
def verify_otp(body: VerifyOtpRequest, db: DbSession) -> dict:
    """
    Exchanges a correct code for a short-lived token.

    The token is what step three spends, so the code and the new password never
    travel together and the code does not have to be held by the client.
    """
    try:
        token = PasswordResetService(db).verify_code(email=body.email, code=body.code)
    except OtpError as exc:
        db.commit()      # the attempt counter must survive the refusal
        raise AuthenticationError(str(exc)) from None
    db.commit()
    return ok({"verification_token": token},
              message="Code verified. Choose a new password.")


@router.post("/reset-password", summary="Set a new password with a verified code")
def reset_password_with_token(body: ResetPasswordRequest, db: DbSession) -> dict:
    try:
        PasswordResetService(db).reset(
            token=body.verification_token, new_password=body.new_password)
    except OtpError as exc:
        db.commit()
        raise AuthenticationError(str(exc)) from None
    db.commit()
    return ok({"reset": True},
              message="Your password has been changed. Please sign in.")
