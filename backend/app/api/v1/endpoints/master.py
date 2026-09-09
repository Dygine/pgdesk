"""
Master-admin endpoints.

Every route here is gated by `require_master`, so a PG owner reaching one gets
403 no matter what they send. Master admins have no tenant scope of their own -
they name the organisation in the path, which is the one place an organisation
id may legitimately come from the request.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select

from app.core.dependencies import (
    CurrentScope, DbSession, client_ip, require_master,
)
from app.core.responses import ok, paginated
from app.models import (
    Bed, Branch, Building, Customer, Organization, Room, Subscription,
    SubscriptionPlan, User,
)
from app.schemas.organization import (
    ChangePlan, ExtendSubscription, LimitOverrides, OrganizationCreate,
    OrganizationUpdate, PlanUpdate, PlatformSettingsUpdate, StatusChange,
)
from app.models.enums import AuditAction
from app.services.audit import AuditService
from app.services.dashboard_service import MasterDashboardService
from app.services.platform_settings_service import PlatformSettingsService
from app.services.organization_service import OrganizationService
from app.services.subscription_limits import SubscriptionLimitService

router = APIRouter(prefix="/master", tags=["master"])
Master = Annotated[CurrentScope, Depends(require_master)]


# ------------------------------------------------------------------ helpers
def _subscription_payload(db, org_id: uuid.UUID) -> dict | None:
    sub = SubscriptionLimitService(db).current_subscription(org_id)
    if sub is None:
        return None
    from datetime import date
    return {
        "id": str(sub.id), "plan_id": str(sub.plan_id),
        "plan_name": sub.plan.name if sub.plan else None,
        "plan_code": sub.plan.code if sub.plan else None,
        "start_date": sub.start_date.isoformat(), "end_date": sub.end_date.isoformat(),
        "trial_end_date": sub.trial_end_date.isoformat() if sub.trial_end_date else None,
        "status": sub.status, "is_current": sub.is_current,
        "days_remaining": (sub.end_date - date.today()).days,
        "limits": sub.effective_limits(),
    }


def _org_payload(db, org: Organization, *, with_counts: bool = True) -> dict:
    data = {
        "id": str(org.id), "name": org.name, "slug": org.slug,
        "legal_name": org.legal_name, "owner_name": org.owner_name,
        "owner_email": org.owner_email, "owner_phone": org.owner_phone,
        "address": org.address, "city": org.city, "state": org.state,
        "pincode": org.pincode, "gstin": org.gstin, "pg_type": org.pg_type,
        "gender": org.gender, "notes": org.notes, "status": org.status,
        "storage_used_gb": float(org.storage_used_gb or 0),
        "onboarded_on": org.onboarded_on.isoformat() if org.onboarded_on else None,
        "created_at": org.created_at.isoformat(),
        "subscription": _subscription_payload(db, org.id),
    }
    if with_counts:
        data["counts"] = SubscriptionLimitService(db).usage_for(org.id)
    return data


def _plan_payload(plan: SubscriptionPlan) -> dict:
    return {
        "id": str(plan.id), "code": plan.code, "name": plan.name,
        "description": plan.description, "price": plan.price,
        "billing_cycle": plan.billing_cycle, "support_level": plan.support_level,
        "features": plan.features or [], "status": plan.status,
        "sort_order": plan.sort_order,
        "limits": {
            "branches": plan.max_branches, "buildings": plan.max_buildings,
            "floors": plan.max_floors, "rooms": plan.max_rooms, "beds": plan.max_beds,
            "customers": plan.max_customers, "users": plan.max_users,
            "admins": plan.max_admins, "storage_gb": plan.storage_limit_gb,
            "monthly_transactions": plan.monthly_transaction_limit,
        },
    }


# --------------------------------------------------------------- dashboard
@router.get("/dashboard", summary="Platform overview")
def dashboard(db: DbSession, scope: Master) -> dict:
    return ok(MasterDashboardService(db).overview())


# ----------------------------------------------------------- organisations
@router.get("/organizations", summary="List organisations")
def list_organizations(
    db: DbSession, scope: Master,
    search: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    plan: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = "-created_at",
) -> dict:
    rows, total = OrganizationService(db).list(
        search=search, status=status_filter, plan_code=plan,
        page=page, page_size=page_size, sort=sort,
    )
    return paginated([_org_payload(db, o) for o in rows], page, page_size, total)


@router.post("/organizations", status_code=status.HTTP_201_CREATED,
             summary="Create an organisation with its owner and subscription")
def create_organization(body: OrganizationCreate, request: Request,
                        db: DbSession, scope: Master) -> dict:
    """
    One transaction creates the organisation, its subscription, the Owner role
    and the owner account. The temporary password is returned here and nowhere
    else - it is stored only as an Argon2 hash.
    """
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else None)

    result = OrganizationService(db).create_organization(
        body.model_dump(), actor=scope.user, ip=ip)
    db.commit()

    return ok(
        {
            "organization": _org_payload(db, result.organization),
            "owner": {
                "id": str(result.owner.id), "name": result.owner.name,
                "email": result.owner.email,
                "temporary_password": result.temporary_password,
                "must_change_password": True,
            },
        },
        message=f"{result.organization.name} created. Share the temporary password securely.",
    )


@router.get("/organizations/{organization_id}", summary="Organisation detail")
def get_organization(organization_id: uuid.UUID, db: DbSession, scope: Master) -> dict:
    service = OrganizationService(db)
    org = service.get(organization_id)

    branches = list(db.scalars(
        select(Branch).where(Branch.organization_id == org.id).order_by(Branch.name)).all())
    users = list(db.scalars(
        select(User).where(User.organization_id == org.id).order_by(User.name)).all())
    history = list(db.scalars(
        select(Subscription).where(Subscription.organization_id == org.id)
        .order_by(Subscription.start_date.desc())).all())

    payload = _org_payload(db, org)
    payload["usage"] = SubscriptionLimitService(db).summary(org.id)
    payload["branches"] = [
        {"id": str(b.id), "name": b.name, "code": b.code, "city": b.city,
         "status": b.status,
         "beds": db.scalar(select(func.count(Bed.id)).where(Bed.branch_id == b.id)) or 0,
         "rooms": db.scalar(select(func.count(Room.id)).where(Room.branch_id == b.id)) or 0}
        for b in branches
    ]
    payload["users"] = [
        {"id": str(u.id), "name": u.name, "email": u.email, "status": u.status,
         "roles": [r.name for r in u.roles],
         "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}
        for u in users
    ]
    payload["subscription_history"] = [
        {"id": str(s.id), "plan": s.plan.name if s.plan else None,
         "start_date": s.start_date.isoformat(), "end_date": s.end_date.isoformat(),
         "status": s.status, "is_current": s.is_current}
        for s in history
    ]
    return ok(payload)


@router.patch("/organizations/{organization_id}", summary="Edit an organisation")
def update_organization(organization_id: uuid.UUID, body: OrganizationUpdate,
                        db: DbSession, scope: Master) -> dict:
    org = OrganizationService(db).update(
        organization_id, body.model_dump(exclude_unset=True), actor=scope.user)
    db.commit()
    return ok(_org_payload(db, org), message=f"{org.name} updated.")


@router.post("/organizations/{organization_id}/status", summary="Suspend, activate or expire")
def change_status(organization_id: uuid.UUID, body: StatusChange,
                  db: DbSession, scope: Master) -> dict:
    """Status changes never delete data - a suspended tenant is frozen, not erased."""
    org = OrganizationService(db).set_status(
        organization_id, body.status, reason=body.reason, actor=scope.user)
    db.commit()
    return ok(_org_payload(db, org), message=f"{org.name} is now {body.status.lower()}.")


@router.post("/organizations/{organization_id}/extend", summary="Extend the subscription")
def extend(organization_id: uuid.UUID, body: ExtendSubscription,
           db: DbSession, scope: Master) -> dict:
    sub = OrganizationService(db).extend_subscription(
        organization_id, body.days, actor=scope.user)
    db.commit()
    return ok(_subscription_payload(db, organization_id),
              message=f"Extended by {body.days} days to {sub.end_date}.")


@router.post("/organizations/{organization_id}/plan", summary="Change the subscription plan")
def change_plan(organization_id: uuid.UUID, body: ChangePlan,
                db: DbSession, scope: Master) -> dict:
    OrganizationService(db).change_plan(organization_id, body.plan_code, actor=scope.user)
    db.commit()
    return ok(_subscription_payload(db, organization_id), message="Plan changed.")


@router.post("/organizations/{organization_id}/limits", summary="Override plan limits")
def set_limits(organization_id: uuid.UUID, body: LimitOverrides,
               db: DbSession, scope: Master) -> dict:
    OrganizationService(db).set_limit_overrides(
        organization_id, body.overrides, actor=scope.user)
    db.commit()
    return ok(_subscription_payload(db, organization_id), message="Limits updated.")


@router.get("/organizations/{organization_id}/usage", summary="Usage against plan limits")
def organization_usage(organization_id: uuid.UUID, db: DbSession, scope: Master) -> dict:
    return ok(SubscriptionLimitService(db).summary(organization_id))


# ------------------------------------------------------------------- plans
@router.get("/plans", summary="Subscription plans")
def list_plans(db: DbSession, scope: Master) -> dict:
    rows = db.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order)).all()
    return ok([_plan_payload(p) for p in rows])


@router.patch("/plans/{plan_id}", summary="Edit a plan")
def update_plan(plan_id: uuid.UUID, body: PlanUpdate, db: DbSession, scope: Master) -> dict:
    from app.core.exceptions import NotFoundError
    plan = db.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found.")

    data = body.model_dump(exclude_unset=True)
    limits = data.pop("limits", None) or {}
    for field, value in data.items():
        if value is not None:
            setattr(plan, field, value)

    column_for = {
        "branches": "max_branches", "buildings": "max_buildings", "floors": "max_floors",
        "rooms": "max_rooms", "beds": "max_beds", "customers": "max_customers",
        "users": "max_users", "admins": "max_admins",
        "storage_gb": "storage_limit_gb", "monthly_transactions": "monthly_transaction_limit",
    }
    for key, value in limits.items():
        if key in column_for and value is not None:
            setattr(plan, column_for[key], value)

    from app.models.enums import AuditAction
    from app.services.audit import AuditService
    AuditService(db).record(
        scope=None, module="Subscriptions", action=AuditAction.UPDATE,
        description=f"Updated plan {plan.name}", entity_type="plan", entity_id=plan.id,
        user_name=scope.user.name,
    )
    db.commit()
    return ok(_plan_payload(plan), message=f"{plan.name} updated.")


# --------------------------------------------------- usage across tenants
@router.get("/usage", summary="Usage for every organisation")
def platform_usage(db: DbSession, scope: Master,
                   severity: str | None = None) -> dict:
    service = SubscriptionLimitService(db)
    rows = [service.summary(o.id) for o in db.scalars(
        select(Organization).order_by(Organization.name)).all()]
    if severity and severity != "all":
        rows = [r for r in rows if r["worst_severity"] == severity]
    return ok(rows)


@router.get("/subscriptions", summary="Every current subscription")
def list_subscriptions(db: DbSession, scope: Master) -> dict:
    rows = db.execute(
        select(Organization, Subscription, SubscriptionPlan)
        .join(Subscription, Subscription.organization_id == Organization.id)
        .join(SubscriptionPlan, SubscriptionPlan.id == Subscription.plan_id)
        .where(Subscription.is_current.is_(True))
        .order_by(Subscription.end_date)
    ).all()
    from datetime import date
    return ok([
        {
            "organization_id": str(o.id), "organization": o.name,
            "organization_status": o.status, "city": o.city,
            "plan": p.name, "plan_code": p.code, "price": p.price,
            "start_date": s.start_date.isoformat(), "end_date": s.end_date.isoformat(),
            "status": s.status, "days_remaining": (s.end_date - date.today()).days,
        }
        for o, s, p in rows
    ])


@router.post("/subscriptions/sweep", summary="Recompute expiry statuses")
def sweep(db: DbSession, scope: Master) -> dict:
    """
    Marks lapsed subscriptions EXPIRED and near-expiry ones EXPIRING.

    Manual for now; a scheduler owns it once one exists. Idempotent, so running
    it twice changes nothing the second time.
    """
    changed = OrganizationService(db).sweep_expired()
    db.commit()
    return ok({"organizations_updated": changed},
              message=f"{changed} organisation{'s' if changed != 1 else ''} updated.")


# ------------------------------------------------------------- audit trail
@router.get("/audit", summary="Platform audit log")
def audit_log(db: DbSession, scope: Master,
              organization_id: uuid.UUID | None = None,
              module: str | None = None,
              page: int = Query(default=1, ge=1),
              page_size: int = Query(default=25, ge=1, le=100)) -> dict:
    from app.models import AuditLog
    stmt = select(AuditLog)
    if organization_id:
        stmt = stmt.where(AuditLog.organization_id == organization_id)
    if module and module != "all":
        stmt = stmt.where(AuditLog.module == module)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)).all()
    return paginated([
        {"id": str(a.id), "module": a.module, "action": a.action,
         "description": a.description, "user_name": a.user_name,
         "organization_id": str(a.organization_id) if a.organization_id else None,
         "entity_type": a.entity_type, "entity_id": a.entity_id,
         "ip_address": a.ip_address, "created_at": a.created_at.isoformat()}
        for a in rows
    ], page, page_size, total)


# -------------------------------------------------------- platform settings
@router.get("/settings", summary="Platform settings")
def get_platform_settings(db: DbSession, scope: Master) -> dict:
    """
    Platform-wide behaviour, plus an honest report of which notification
    channels can actually deliver on this deployment.

    `channels` is derived from environment configuration, not from the toggles.
    An operator can switch WhatsApp on and still see it reported as not
    configured - which is the truth, and better than a screen that implies
    messages are going out.
    """
    return ok(PlatformSettingsService(db).as_dict())


@router.patch("/settings", summary="Update platform settings")
def update_platform_settings(body: PlatformSettingsUpdate, db: DbSession, scope: Master,
                             request: Request) -> dict:
    service = PlatformSettingsService(db)
    before = service.as_dict()
    service.update(body.model_dump(exclude_unset=True))

    changed = sorted(
        k for k, v in body.model_dump(exclude_unset=True).items()
        if k in before and before[k] != v
    )
    AuditService(db).record(
        scope=scope, module="Platform", action=AuditAction.UPDATE,
        description=("Platform settings updated: " + ", ".join(changed)
                     if changed else "Platform settings saved with no changes"),
        entity_type="platform_settings",
        ip_address=client_ip(request))
    db.commit()
    return ok(service.as_dict(), message="Platform settings saved.")
