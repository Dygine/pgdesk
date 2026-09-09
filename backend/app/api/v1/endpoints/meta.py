"""
Reference data: the permission catalogue and the subscription plans.

Both require authentication. Neither contains tenant data, so leaving them open
would not leak a customer's records - but the permission catalogue describes the
shape of the authorisation system, and the plan list is commercial detail, and
nothing in the product renders either before sign-in. There is no reader to
serve anonymously, so there is no reason to answer anonymously.
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.core.responses import ok
from app.models import SubscriptionPlan
from app.permissions.catalog import ACTION_LABELS, ALL_PERMISSIONS, MASTER_PERMISSIONS, PERMISSION_MODULES

router = APIRouter(prefix="/meta", tags=["meta"])

# Any signed-in principal, staff or resident. The guard is about having an
# account at all, not about holding a particular permission.
Principal = Annotated[object, Depends(get_current_principal)]


@router.get("/permissions", summary="Permission catalogue")
def permission_catalogue(_: Principal) -> dict:
    return ok({
        "modules": PERMISSION_MODULES,
        "action_labels": ACTION_LABELS,
        "all": ALL_PERMISSIONS,
        "master": MASTER_PERMISSIONS,
        "count": len(ALL_PERMISSIONS),
    })


@router.get("/plans", summary="Subscription plans")
def plans(_: Principal, db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order)
    ).all()
    return ok([
        {
            "id": str(p.id), "code": p.code, "name": p.name, "price": p.price,
            "billing_cycle": p.billing_cycle, "support_level": p.support_level,
            "features": p.features, "status": p.status,
            "limits": {
                "branches": p.max_branches, "users": p.max_users, "beds": p.max_beds,
                "customers": p.max_customers, "storage_gb": p.storage_limit_gb,
            },
        }
        for p in rows
    ])
