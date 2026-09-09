"""
Request id + timing.

Every response carries X-Request-ID; the same id goes into the log line, so a
report of "it failed at 14:32" can be traced to one request.
"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("pgdesk.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"

        logger.info(
            "%s %s -> %s (%.1f ms) [%s]",
            request.method, request.url.path, response.status_code, elapsed_ms, request_id,
        )
        return response
