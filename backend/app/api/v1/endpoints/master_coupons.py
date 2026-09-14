"""
`/master/coupons/*` and `/master/revenue` — the platform operator's side.

Creating a coupon, granting it to specific PG owners, and seeing what the
platform actually earned. Master scope only: these endpoints span every tenant,
so they sit behind `require_master` like the rest of `/master/*`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.core.dependencies import CurrentScope, DbSession, require_master
from app.models import (
    Coupon, CouponAssignment, CouponRedemption, Organization, OrgBillingProfile,
    PlatformCharge, SubscriptionPlan,
)
from app.models.enums import NotificationType
from app.services.coupon_service import CouponService, normalise
from app.services.notification_service import NotificationService
from app.services.platform_billing_service import (
    PlatformBillingService, paise_to_rupees, rupees_to_paise,
)

log = logging.getLogger("pgguru.api.master_coupons")

router = APIRouter(prefix="/master", tags=["master"])

Master = Annotated[CurrentScope, Depends(require_master)]


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    description: str | None = None
    kind: str = Field(default="percent", pattern="^(percent|fixed)$")
    #: Percent as a whole number, or rupees for a fixed discount. Converted to
    #: paise on the way in - the API speaks rupees because a human types it.
    value: float = Field(gt=0)
    max_discount_rupees: float | None = None
    min_amount_rupees: float = 0
    applies_to_plans: list[str] = Field(default_factory=list)
    applies_to_cycles: int | None = 1
    valid_from: date | None = None
    valid_until: date | None = None
    max_redemptions: int | None = None
    max_per_org: int = 1

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return normalise(v)


class CouponUpdate(BaseModel):
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(active|paused|expired)$")
    valid_until: date | None = None
    max_redemptions: int | None = None


class AssignRequest(BaseModel):
    organization_ids: list[uuid.UUID]
    notify: bool = True


def _coupon_payload(db, coupon: Coupon, svc: CouponService) -> dict:
    return {
        "id": str(coupon.id),
        "code": coupon.code,
        "description": coupon.description,
        "kind": coupon.kind,
        "value": coupon.value,
        "value_display": (f"{coupon.value}%" if coupon.kind == "percent"
                          else f"\u20b9{paise_to_rupees(coupon.value):,.2f}"),
        "max_discount_rupees": (paise_to_rupees(coupon.max_discount_paise)
                                if coupon.max_discount_paise else None),
        "min_amount_rupees": paise_to_rupees(coupon.min_amount_paise),
        "applies_to_plans": coupon.applies_to_plans or [],
        "applies_to_cycles": coupon.applies_to_cycles,
        "valid_from": coupon.valid_from.isoformat() if coupon.valid_from else None,
        "valid_until": coupon.valid_until.isoformat() if coupon.valid_until else None,
        "max_redemptions": coupon.max_redemptions,
        "max_per_org": coupon.max_per_org,
        "status": coupon.status,
        "is_targeted": coupon.is_targeted,
        "assigned_to": [str(a.organization_id) for a in coupon.assignments],
        "usage": svc.usage(coupon),
        "created_at": coupon.created_at.isoformat(),
    }


# -------------------------------------------------------------- coupons --
@router.get("/coupons", summary="Every coupon")
def list_coupons(db: DbSession, scope: Master) -> dict:
    svc = CouponService(db)
    coupons = db.scalars(select(Coupon).order_by(Coupon.created_at.desc())).all()
    return {"data": [_coupon_payload(db, c, svc) for c in coupons]}


@router.post("/coupons", status_code=status.HTTP_201_CREATED,
             summary="Create a coupon")
def create_coupon(body: CouponCreate, db: DbSession,
                  scope: Master) -> dict:
    if db.scalars(select(Coupon).where(Coupon.code == body.code)).first():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"A coupon with code {body.code} already exists.")

    if body.kind == "percent" and body.value > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "A percentage discount cannot exceed 100%.")

    # Warn rather than refuse: an uncapped percentage coupon is a legitimate
    # choice, but it should be a deliberate one.
    if (body.kind == "percent" and body.max_discount_rupees is None
            and body.max_redemptions is None):
        log.warning("coupon %s created with no discount cap and no redemption "
                    "limit", body.code)

    # Validate plan codes now. A coupon that silently applies to nothing because
    # of a typo is found weeks later by a customer who cannot use it.
    if body.applies_to_plans:
        known = {p.code for p in db.scalars(select(SubscriptionPlan))}
        unknown = set(body.applies_to_plans) - known
        if unknown:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Unknown plan code(s): {', '.join(sorted(unknown))}")

    coupon = Coupon(
        code=body.code, description=body.description, kind=body.kind,
        value=int(body.value) if body.kind == "percent"
        else rupees_to_paise(body.value),
        max_discount_paise=(rupees_to_paise(body.max_discount_rupees)
                            if body.max_discount_rupees else None),
        min_amount_paise=rupees_to_paise(body.min_amount_rupees),
        applies_to_plans=body.applies_to_plans,
        applies_to_cycles=body.applies_to_cycles,
        valid_from=body.valid_from, valid_until=body.valid_until,
        max_redemptions=body.max_redemptions, max_per_org=body.max_per_org,
        status="active",
        created_by_id=getattr(scope, "user_id", None))
    db.add(coupon)
    db.commit()
    return _coupon_payload(db, coupon, CouponService(db))


@router.patch("/coupons/{coupon_id}", summary="Edit a coupon")
def update_coupon(coupon_id: uuid.UUID, body: CouponUpdate, db: DbSession,
                  scope: Master) -> dict:
    coupon = db.get(Coupon, coupon_id)
    if coupon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coupon not found")

    # Deliberately narrow. The discount value, kind and per-org cap are not
    # editable: changing what a code is worth after customers hold it means two
    # people redeeming "the same" coupon get different things, and the
    # redemption rows already written no longer describe what happened.
    for field in ("description", "status", "valid_until", "max_redemptions"):
        value = getattr(body, field)
        if value is not None:
            setattr(coupon, field, value)
    db.commit()
    return _coupon_payload(db, coupon, CouponService(db))


@router.delete("/coupons/{coupon_id}", summary="Delete an unused coupon")
def delete_coupon(coupon_id: uuid.UUID, db: DbSession,
                  scope: Master) -> dict:
    coupon = db.get(Coupon, coupon_id)
    if coupon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coupon not found")

    used = db.scalar(select(func.count(CouponRedemption.id)).where(
        CouponRedemption.coupon_id == coupon.id,
        CouponRedemption.state == "confirmed"))
    if used:
        # A redeemed coupon is part of the financial record: deleting it would
        # orphan the discount lines on invoices already issued. Pause it.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"That coupon has been redeemed {used} time(s) and cannot be "
            f"deleted. Pause it instead.")

    db.delete(coupon)
    db.commit()
    return {"deleted": True}


@router.post("/coupons/{coupon_id}/assign", summary="Grant a coupon to specific PGs")
def assign_coupon(coupon_id: uuid.UUID, body: AssignRequest, db: DbSession,
                  scope: Master) -> dict:
    """
    Target a coupon at named organisations.

    Once a coupon has any assignment it stops being a public code - only the
    assigned organisations can redeem it, and it appears in their billing screen
    without them needing to be told the code.
    """
    coupon = db.get(Coupon, coupon_id)
    if coupon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coupon not found")

    notifier = NotificationService(db)
    existing = {a.organization_id for a in coupon.assignments}
    added = 0

    for org_id in body.organization_ids:
        if org_id in existing:
            continue
        org = db.get(Organization, org_id)
        if org is None:
            continue
        assignment = CouponAssignment(coupon_id=coupon.id, organization_id=org_id)
        db.add(assignment)
        added += 1

        if body.notify:
            value = (f"{coupon.value}%" if coupon.kind == "percent"
                     else f"\u20b9{paise_to_rupees(coupon.value):,.0f}")
            until = (f" Valid until {coupon.valid_until.strftime('%d %b %Y')}."
                     if coupon.valid_until else "")
            notifier.to_permission_holders(
                org_id, "org.settings.manage", NotificationType.SUBSCRIPTION,
                f"{value} off your next renewal",
                f"Use code {coupon.code} when you pay.{until}")
            assignment.notified_at = datetime.now(timezone.utc)

    db.commit()
    return {"assigned": added,
            "total": len(coupon.assignments) + added}


@router.delete("/coupons/{coupon_id}/assign/{organization_id}",
               summary="Withdraw a coupon from one PG")
def unassign_coupon(coupon_id: uuid.UUID, organization_id: uuid.UUID,
                    db: DbSession, scope: Master) -> dict:
    assignment = db.scalars(select(CouponAssignment).where(
        CouponAssignment.coupon_id == coupon_id,
        CouponAssignment.organization_id == organization_id)).first()
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not assigned")
    db.delete(assignment)
    db.commit()
    return {"removed": True}


@router.get("/coupons/{coupon_id}/redemptions", summary="Who used this coupon")
def coupon_redemptions(coupon_id: uuid.UUID, db: DbSession,
                       scope: Master) -> dict:
    rows = db.scalars(select(CouponRedemption).where(
        CouponRedemption.coupon_id == coupon_id)
        .order_by(CouponRedemption.created_at.desc()).limit(200)).all()
    orgs = {o.id: o.name for o in db.scalars(select(Organization))}
    return {"data": [{
        "organization": orgs.get(r.organization_id, "—"),
        "organization_id": str(r.organization_id),
        "period": r.period.isoformat() if r.period else None,
        "state": r.state,
        "gross_rupees": paise_to_rupees(r.gross_paise),
        "discount_rupees": paise_to_rupees(r.discount_paise),
        "net_rupees": paise_to_rupees(r.net_paise),
        "created_at": r.created_at.isoformat(),
    } for r in rows]}


# -------------------------------------------------------------- revenue --
@router.get("/revenue", summary="What the platform earned")
def revenue(db: DbSession, scope: Master, days: int = 90) -> dict:
    """
    Platform revenue from PG owners.

    Counts only `paid` charges. A charge that was created and abandoned is not
    revenue, and including it would make the figure a measure of intent.
    """
    from datetime import timedelta
    since = date.today() - timedelta(days=days)

    charges = db.scalars(select(PlatformCharge).where(
        PlatformCharge.status == "paid",
        PlatformCharge.created_at >= since)).all()

    subscription_paise = sum(c.net_paise for c in charges
                             if c.purpose == "subscription")
    topup_paise = sum(c.net_paise for c in charges if c.purpose == "wallet_topup")
    discount_paise = sum(c.discount_paise for c in charges)

    held = int(db.scalar(select(func.coalesce(
        func.sum(OrgBillingProfile.cached_wallet_paise), 0))) or 0)

    by_org: dict[str, int] = {}
    for c in charges:
        by_org[str(c.organization_id)] = (
            by_org.get(str(c.organization_id), 0) + c.net_paise)
    orgs = {str(o.id): o.name for o in db.scalars(select(Organization))}
    top = sorted(by_org.items(), key=lambda kv: kv[1], reverse=True)[:10]

    return {
        "window_days": days,
        "subscription_rupees": paise_to_rupees(subscription_paise),
        "topup_rupees": paise_to_rupees(topup_paise),
        "discount_given_rupees": paise_to_rupees(discount_paise),
        "collected_rupees": paise_to_rupees(subscription_paise + topup_paise),
        # Money taken but not yet consumed. A liability, not revenue - the
        # owner can still spend it, and in some readings can ask for it back.
        "wallet_float_rupees": paise_to_rupees(held),
        "paying_organizations": len(by_org),
        "top_organizations": [
            {"organization": orgs.get(oid, "—"), "organization_id": oid,
             "paid_rupees": paise_to_rupees(amount)} for oid, amount in top],
    }


@router.get("/billing/charges", summary="Every platform charge")
def all_charges(db: DbSession, scope: Master, limit: int = 100,
                status_filter: str | None = None) -> dict:
    q = select(PlatformCharge).order_by(PlatformCharge.created_at.desc())
    if status_filter:
        q = q.where(PlatformCharge.status == status_filter)
    charges = db.scalars(q.limit(min(limit, 500))).all()
    orgs = {o.id: o.name for o in db.scalars(select(Organization))}
    return {"data": [{
        "id": str(c.id),
        "organization": orgs.get(c.organization_id, "—"),
        "purpose": c.purpose, "method": c.method, "status": c.status,
        "gross_rupees": paise_to_rupees(c.gross_paise),
        "discount_rupees": paise_to_rupees(c.discount_paise),
        "net_rupees": paise_to_rupees(c.net_paise),
        "invoice_number": c.dygine_invoice_number,
        "failure_reason": c.failure_reason,
        "created_at": c.created_at.isoformat(),
    } for c in charges]}


@router.post("/billing/reconcile", summary="Settle charges left in limbo")
def reconcile(db: DbSession, scope: Master) -> dict:
    """
    Ask Dygine what happened to charges we never got an answer about.

    Covers both a webhook that never arrived and a call that timed out after
    Dygine had already acted. Safe to run repeatedly.
    """
    result = PlatformBillingService(db).reconcile_open()
    db.commit()
    return result


@router.post("/billing/verify-dygine", summary="Check the Dygine credentials work")
def verify_dygine(db: DbSession, scope: Master) -> dict:
    from app.services.dygine_client import DygineClient, DygineError
    try:
        result = DygineClient(db).verify()
        db.commit()
        return result
    except DygineError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
