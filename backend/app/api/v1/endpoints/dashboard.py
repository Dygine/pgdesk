"""Owner dashboard, organisation settings context and tenant usage."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentScope, DbSession, require, require_tenant
from app.core.responses import ok
from app.services.dashboard_service import OwnerDashboardService
from app.services.subscription_limits import SubscriptionLimitService

router = APIRouter(tags=["dashboard"])
Tenant = Annotated[CurrentScope, Depends(require_tenant)]


@router.get("/dashboard", summary="Owner and staff dashboard")
def owner_dashboard(db: DbSession, scope: Tenant,
                    _: None = Depends(require("dashboard.view")),
                    branch_id: uuid.UUID | None = None) -> dict:
    """
    Scoped to the branches the caller is assigned to. Passing a `branch_id` they
    do not hold yields empty figures rather than another branch's numbers.
    """
    return ok(OwnerDashboardService(db, scope).overview(branch_id))


@router.get("/subscription", summary="This organisation's plan and usage")
def my_subscription(db: DbSession, scope: Tenant,
                    _: None = Depends(require("dashboard.view"))) -> dict:
    return ok(SubscriptionLimitService(db).summary(scope.organization_id))
