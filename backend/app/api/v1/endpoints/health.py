from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.database import check_database_connection
from app.core.responses import ok

router = APIRouter(tags=["meta"])


@router.get("/health", summary="Liveness probe")
def health() -> dict:
    """Cheap and dependency-free. Answers whether the process is up."""
    return {"status": "ok"}


@router.get("/health/db", summary="Database connectivity")
def health_db(response: Response) -> dict:
    """
    Readiness probe. Returns 503 when the database is unreachable so a load
    balancer takes the instance out of rotation rather than serving errors.
    """
    connected, detail = check_database_connection()
    if not connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "error",
            "database": "unreachable",
            # The exception class only - never the DSN, which contains credentials.
            "detail": detail,
        }
    return {"status": "ok", "database": "connected", "server_version": detail}


@router.get("/health/full", summary="Full status")
def health_full(response: Response) -> dict:
    connected, detail = check_database_connection()
    if not connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ok({
        "status": "ok" if connected else "degraded",
        "environment": settings.environment,
        "version": "0.1.0",
        "milestone": "1 - foundation",
        "database": {"connected": connected, "detail": detail if connected else None},
    })
