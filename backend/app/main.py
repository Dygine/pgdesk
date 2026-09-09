"""
Application entry point.

Deliberately thin: it wires configuration, middleware, error handlers and the
versioned router, and does nothing else. Business logic lives in services,
data access in repositories, HTTP in routers.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import check_database_connection
from app.core.exceptions import register_exception_handlers
from app.middleware import RequestContextMiddleware

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("pgdesk")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.assert_production_safe()

    connected, detail = check_database_connection()
    if connected:
        logger.info("Database connected (PostgreSQL %s)", detail)
    else:
        # Not fatal: the app should still serve /health so an orchestrator can
        # report *why* it is unhealthy rather than crash-looping silently.
        logger.error("Database unreachable at startup: %s", detail)

    logger.info(
        "%s starting in %s mode | CORS: %s",
        settings.project_name, settings.environment, ", ".join(settings.cors_origin_list),
    )
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.project_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    description=(
        "Multi-tenant PG and hostel management API.\n\n"
        "**Milestone 1 — foundation.** FastAPI, PostgreSQL, SQLAlchemy 2.x and Alembic "
        "are wired; the security, tenancy and permission layers are in place and unit "
        "tested, but the CRUD endpoints that use them arrive in later milestones.\n\n"
        "Two invariants hold across every endpoint that will be added:\n"
        "1. `organization_id` is taken from the authenticated session, never from the request.\n"
        "2. Every action is gated by a `module.action` permission that matches the "
        "React app's catalogue exactly."
    ),
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,     # never "*" - see config.assert_production_safe
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-PGDesk-Auth"],
    expose_headers=["X-Request-ID"],
)

register_exception_handlers(app)

# Health sits at the root, outside the version prefix, so probes never break on a bump.
app.include_router(health.router)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "success": True,
        "data": {"name": settings.project_name, "version": "0.1.0", "docs": "/docs"},
        "message": "PGDesk API",
    }
