"""
The refresh session cookie.

Why a cookie at all: the refresh token is the long-lived credential. Held in
localStorage it is readable by any script that runs on the page, so a single XSS
gives an attacker a session that outlives every access token and survives the
user closing the tab. HttpOnly puts it somewhere script cannot reach.

Three properties do the work:

  HttpOnly   script cannot read it
  Secure     it is not sent over plaintext HTTP
  Path       scoped to /api/v1/auth, so it rides along with four endpoints
             instead of every request the app makes

The access token deliberately stays in the response body. Something has to go in
the Authorization header, and a thirty-minute token that lives in a JavaScript
variable is a far smaller prize than a fourteen-day one on disk.

CSRF
----
A cookie is sent by the browser whether or not the page asked for it, so a
cookie-borne credential needs a second factor proving the request came from our
own front end. Two are used together:

  SameSite   blocks the cookie on cross-site navigations
  A required custom header on every state-changing auth call. A cross-origin
  request carrying a custom header is not a "simple request", so the browser
  must preflight it, and the preflight is answered only for the origins in
  CORS_ORIGINS. An attacker's page cannot get past that; a <form> post - which
  needs no preflight - cannot set the header in the first place.
"""
from fastapi import Request, Response

from app.core.config import settings
from app.core.exceptions import AuthenticationError

#: Front-end sends this on refresh and logout. Value is irrelevant; presence is
#: the assertion, because only a preflighted same-origin-approved request can
#: set it at all.
CSRF_HEADER = "X-PGDesk-Auth"


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        domain=settings.refresh_cookie_domain,
        path=settings.refresh_cookie_path,
    )


def clear_refresh_cookie(response: Response) -> None:
    """
    Cleared with the same attributes it was set with.

    A delete_cookie whose path or domain differs from the original leaves the
    cookie in place, and the user stays signed in after clicking sign out.
    """
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        domain=settings.refresh_cookie_domain,
        path=settings.refresh_cookie_path,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
    )


def read_refresh_token(request: Request, body_token: str | None = None) -> str | None:
    """
    Cookie first, then an explicit body value.

    The body path exists for non-browser API clients, which have no cookie jar.
    It is checked second so that a stale token pasted into a body can never
    override the live session the browser is actually holding.
    """
    return request.cookies.get(settings.refresh_cookie_name) or body_token


def require_csrf_header(request: Request) -> None:
    """
    Refuse a cookie-authenticated call that did not come from our own client.

    Skipped when no refresh cookie is present: such a request is authenticating
    with a body token like any other API client, and is not vulnerable to the
    browser attaching a credential on its own.
    """
    if settings.refresh_cookie_name not in request.cookies:
        return
    if CSRF_HEADER.lower() not in {k.lower() for k in request.headers.keys()}:
        raise AuthenticationError(
            "This request is missing the header the browser client sends. "
            "Sign in again."
        )
