"""
Application errors and the handlers that turn them into the standard envelope.

Every failure the client sees has the same shape, and none of them leak a stack
trace, a SQL fragment or a driver message in production.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings

logger = logging.getLogger("pgdesk")


class AppError(Exception):
    """Base for errors we raise deliberately."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "app_error"

    def __init__(self, message: str, *, code: str | None = None, errors: list | None = None):
        self.message = message
        self.errors = errors or []
        if code:
            self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "not_authenticated"


class TenantIsolationError(AppError):
    """
    Raised when a request reaches a row belonging to another organization.
    Deliberately answered with 404, not 403: confirming the row exists would
    itself leak information across tenants.
    """

    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class SubscriptionLimitError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "subscription_limit_reached"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class RateLimitedError(AppError):
    """
    Too many attempts. Carries `retry_after` so the handler can set the header
    a well-behaved client reads instead of hammering on blindly.
    """

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"

    def __init__(self, message: str, *, retry_after: int | None = None,
                 code: str | None = None, errors: list | None = None):
        super().__init__(message, code=code, errors=errors)
        self.retry_after = retry_after


def _envelope(message: str, code: str, errors: list | None = None) -> dict:
    return {"success": False, "message": message, "code": code, "errors": errors or []}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        headers = {}
        retry_after = getattr(exc, "retry_after", None)
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.message, exc.code, exc.errors),
            headers=headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(p) for p in e["loc"] if p not in ("body", "query")),
             "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("The request could not be validated.", "validation_error", errors),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(str(exc.detail), "http_error"),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError):
        # A constraint fired. Log the detail; tell the client only that it conflicted.
        logger.warning("Integrity error: %s", exc.orig)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_envelope("That change conflicts with an existing record.", "conflict"),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _sqlalchemy(_: Request, exc: SQLAlchemyError):
        logger.exception("Database error")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("A database error occurred.", "database_error"),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error")
        message = str(exc) if settings.debug else "Something went wrong on our side."
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(message, "internal_error"),
        )
