"""Every failure returns the same envelope shape and leaks nothing."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AppError, ConflictError, NotFoundError, PermissionDeniedError,
    SubscriptionLimitError, TenantIsolationError, register_exception_handlers,
)


@pytest.fixture
def app_with_errors():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    def _nf():
        raise NotFoundError("Branch not found.")

    @app.get("/denied")
    def _d():
        raise PermissionDeniedError("Your role does not include rooms.edit.")

    @app.get("/other-tenant")
    def _ot():
        raise TenantIsolationError("Branch not found.")

    @app.get("/limit")
    def _l():
        raise SubscriptionLimitError("Branch limit reached for your current subscription plan.")

    @app.get("/boom")
    def _b():
        raise RuntimeError("secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_not_found_shape(app_with_errors):
    r = app_with_errors.get("/not-found")
    assert r.status_code == 404
    assert r.json() == {"success": False, "message": "Branch not found.",
                        "code": "not_found", "errors": []}


def test_permission_denied_is_403(app_with_errors):
    r = app_with_errors.get("/denied")
    assert r.status_code == 403
    assert r.json()["code"] == "permission_denied"


def test_cross_tenant_access_answers_404_not_403(app_with_errors):
    """
    Answering 403 would confirm the row exists in another tenant. 404 is the
    correct response and must be indistinguishable from a genuine miss.
    """
    other = app_with_errors.get("/other-tenant")
    genuine = app_with_errors.get("/not-found")
    assert other.status_code == 404
    assert other.json() == genuine.json()


def test_subscription_limit_is_409_with_a_usable_message(app_with_errors):
    r = app_with_errors.get("/limit")
    assert r.status_code == 409
    assert r.json()["code"] == "subscription_limit_reached"
    assert "limit reached" in r.json()["message"].lower()


def test_error_classes_carry_their_status_codes():
    assert NotFoundError("x").status_code == 404
    assert PermissionDeniedError("x").status_code == 403
    assert ConflictError("x").status_code == 409
    assert SubscriptionLimitError("x").status_code == 409
    assert AppError("x").status_code == 400
