"""
The response headers a browser needs in order to defend the app for us.

None of these change what the API does. They change what a browser is willing
to do with the response, which is the only place several classes of attack can
be stopped at all.

Why each one is here, and why it is set the way it is:

**Strict-Transport-Security** - only on HTTPS responses. Sending it over plain
http is meaningless (a browser ignores it) and setting it during local
development pins localhost to https in that browser's HSTS store for a year,
which is a genuinely unpleasant thing to debug. `includeSubDomains` is on
because pgguru.in serves the app, the API and the marketing site; a subdomain
left on http is a place to strip the session cookie from.

**X-Frame-Options / frame-ancestors** - nothing in this app is ever framed. The
screens that matter here take money and change bed assignments, and a
transparent iframe over a "Confirm payment" button is the entire clickjacking
attack. DENY rather than SAMEORIGIN: there is no first-party framing either.

**X-Content-Type-Options** - stops a browser guessing that an uploaded document
is really HTML and running it. Resident ID scans are user-supplied bytes served
back from our origin, which is exactly the case this header exists for.

**Referrer-Policy** - URLs here carry organisation and resident uuids. Without
this they leak in the Referer header of every outbound link and every image
loaded from another host.

**Permissions-Policy** - the API itself never needs a camera, a microphone or a
location. Denying them costs nothing and shrinks what an injected script in a
framed or embedded context can ask for. The *app* asks for camera and location
through Capacitor's native permissions, not through this header, so the native
scanner and geofence are unaffected.

**Content-Security-Policy** - applied only to API responses, deliberately.
The front end is a separate Vite build served as static files, and a CSP
written here could not know its hashes; getting that wrong takes the whole UI
down. What is covered is every JSON and every document this API serves, where
`default-src 'none'` is both correct and free - an API response has no
legitimate reason to load anything at all.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

#: Sent on every response.
BASE_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

#: An API response should never pull in a script, a style or an image.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

#: One year, which is the minimum the HSTS preload list accepts.
HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds the headers above without ever overwriting one a route set itself.

    The "do not overwrite" rule matters: the invoice PDF route sets its own
    Content-Disposition and a future route may need a looser frame policy for a
    specific embed. A middleware that stamps over route decisions turns into
    something people work around rather than something they trust.
    """

    def __init__(self, app, *, hsts: bool = True, api_prefix: str = "/api"):
        super().__init__(app)
        self.hsts = hsts
        self.api_prefix = api_prefix

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        for name, value in BASE_HEADERS.items():
            response.headers.setdefault(name, value)

        # Only meaningful over TLS. Behind Render the original scheme arrives in
        # X-Forwarded-Proto; request.url.scheme alone says "http" there.
        forwarded = request.headers.get("x-forwarded-proto", "")
        secure = forwarded.split(",")[0].strip() == "https" or request.url.scheme == "https"
        if self.hsts and secure:
            response.headers.setdefault("Strict-Transport-Security", HSTS)

        if request.url.path.startswith(self.api_prefix):
            response.headers.setdefault("Content-Security-Policy", API_CSP)

        return response
