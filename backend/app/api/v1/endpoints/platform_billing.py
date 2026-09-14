"""
`/billing/platform/*` — what a PG owner sees and does about paying PGGuru.

Separate from `/invoices` and `/payments`, which are the resident-facing rent
system. The two never mix: this router is about the owner paying the platform,
and no resident, staff member or seeker can reach any of it.

Access is `settings.manage`, not a new permission. An organisation that has
already decided who may change its settings has decided who may spend its money;
inventing a second permission would mean every existing PG has nobody able to
pay until someone reassigns roles.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.dependencies import CurrentScope, DbSession, require, require_tenant
from app.models import Coupon, PlatformCharge, SubscriptionPlan
from app.services.coupon_service import CouponError, CouponService
from app.services.dygine_client import DygineError, DygineNotConfigured
from app.services.platform_billing_service import (
    PlatformBillingService, paise_to_rupees, rupees_to_paise,
)

log = logging.getLogger("pgguru.api.platform_billing")

router = APIRouter(prefix="/billing/platform", tags=["platform billing"])

Tenant = Annotated[CurrentScope, Depends(require_tenant)]


class TopupRequest(BaseModel):
    amount_rupees: float = Field(gt=0, description="Rupees to add to the wallet")


class CheckoutRequest(BaseModel):
    coupon_code: str | None = None
    success_url: str | None = None
    cancel_url: str | None = None


class CouponPreview(BaseModel):
    code: str


class AutoDebitRequest(BaseModel):
    enabled: bool


def _service(db) -> PlatformBillingService:
    return PlatformBillingService(db)


def _dygine_error(exc: DygineError) -> HTTPException:
    """
    Turn a gateway failure into an honest HTTP response.

    A configuration problem is 503 rather than 500: it is not a bug, the
    operator has not finished setting the platform up, and the message says so.
    """
    if isinstance(exc, DygineNotConfigured):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    if exc.is_insufficient_balance:
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if exc.is_unreachable:
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


# ------------------------------------------------------------- overview --
@router.get("/summary", summary="Wallet, plan and what is due")
def summary(db: DbSession, scope: Tenant,
            _: None = Depends(require("settings.manage"))) -> dict:
    """
    Everything the billing screen needs in one call.

    `wallet_live` is False when the balance came from cache because the payments
    service could not be reached. The UI must say so rather than presenting a
    stale figure as current - an owner who believes they have a balance they do
    not is about to have a renewal fail.
    """
    svc = _service(db)
    org_id = scope.organization_id

    balance, as_of, live = svc.wallet_balance(org_id)
    prof = svc.profile(org_id)
    sub, plan = svc.current_plan(org_id)

    payload: dict = {
        "wallet": {
            "balance_paise": balance,
            "balance_rupees": paise_to_rupees(balance),
            "as_of": as_of.isoformat() if as_of else None,
            "live": live,
        },
        "auto_debit_enabled": prof.auto_debit_enabled,
        "gateway_available": svc.dygine.enabled,
        "subscription": None,
        "due": None,
    }

    if sub is not None and plan is not None:
        payload["subscription"] = {
            "plan_code": plan.code,
            "plan_name": plan.name,
            "price_rupees": plan.price,
            "billing_cycle": plan.billing_cycle,
            "status": sub.status,
            "current_period_end": sub.end_date.isoformat(),
            "days_remaining": (sub.end_date - date.today()).days,
        }
        try:
            payload["due"] = svc.quote(org_id).as_dict()
        except ValueError as exc:
            log.info("no quote for %s: %s", org_id, exc)

    coupons = CouponService(db).available_for(org_id)
    payload["available_coupons"] = [{
        "code": c.code, "description": c.description, "kind": c.kind,
        "value": c.value,
        "valid_until": c.valid_until.isoformat() if c.valid_until else None,
    } for c in coupons]

    return payload


@router.get("/history", summary="Past charges and invoices")
def history(db: DbSession, scope: Tenant, limit: int = 50,
            _: None = Depends(require("settings.manage"))) -> dict:
    svc = _service(db)
    charges = db.scalars(
        select(PlatformCharge)
        .where(PlatformCharge.organization_id == scope.organization_id)
        .order_by(PlatformCharge.created_at.desc())
        .limit(min(limit, 200))).all()

    return {"data": [{
        "id": str(c.id),
        "purpose": c.purpose,
        "method": c.method,
        "period": c.period.isoformat() if c.period else None,
        "gross_rupees": paise_to_rupees(c.gross_paise),
        "discount_rupees": paise_to_rupees(c.discount_paise),
        "net_rupees": paise_to_rupees(c.net_paise),
        "status": c.status,
        "invoice_number": c.dygine_invoice_number,
        "invoice_url": (svc.dygine.invoice_pdf_url(c.dygine_invoice_id)
                        if c.dygine_invoice_id else None),
        "failure_reason": c.failure_reason,
        "created_at": c.created_at.isoformat(),
        "paid_at": c.paid_at.isoformat() if c.paid_at else None,
    } for c in charges]}


@router.get("/wallet/transactions", summary="Wallet ledger")
def wallet_transactions(db: DbSession, scope: Tenant,
                        _: None = Depends(require("settings.manage"))) -> dict:
    svc = _service(db)
    prof = svc.profile(scope.organization_id)
    try:
        return svc.dygine.wallet_detail(prof.dygine_external_id)
    except DygineError as exc:
        raise _dygine_error(exc) from None


# -------------------------------------------------------------- coupons --
@router.post("/coupons/preview", summary="Check a coupon before paying")
def preview_coupon(body: CouponPreview, db: DbSession, scope: Tenant,
                   _: None = Depends(require("settings.manage"))) -> dict:
    """
    Price the charge with this coupon. Reserves nothing.

    Deliberately separate from checkout so the owner sees the new total before
    committing - and so an abandoned "what if" does not consume a redemption.
    """
    svc = _service(db)
    try:
        plan_info = svc.quote(scope.organization_id, coupon_code=body.code)
    except CouponError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return plan_info.as_dict()


# ------------------------------------------------------------- payments --
@router.post("/topup", summary="Add money to the wallet")
def topup(body: TopupRequest, db: DbSession, scope: Tenant,
          _: None = Depends(require("settings.manage"))) -> dict:
    svc = _service(db)
    try:
        charge = svc.start_topup_checkout(
            scope.organization_id, rupees_to_paise(body.amount_rupees))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except DygineError as exc:
        raise _dygine_error(exc) from None

    db.commit()
    return {"charge_id": str(charge.id), "checkout_url": charge.checkout_url,
            "amount_rupees": paise_to_rupees(charge.net_paise)}


@router.post("/subscription/checkout", summary="Pay the subscription by card or UPI")
def subscription_checkout(body: CheckoutRequest, db: DbSession,
                          scope: Tenant,
                          _: None = Depends(require("settings.manage"))) -> dict:
    svc = _service(db)
    try:
        charge = svc.start_subscription_checkout(
            scope.organization_id, coupon_code=body.coupon_code,
            success_url=body.success_url, cancel_url=body.cancel_url)
    except CouponError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except DygineError as exc:
        raise _dygine_error(exc) from None

    db.commit()
    return {"charge_id": str(charge.id), "checkout_url": charge.checkout_url,
            "amount_rupees": paise_to_rupees(charge.net_paise),
            "discount_rupees": paise_to_rupees(charge.discount_paise)}


@router.post("/subscription/pay-from-wallet", summary="Pay the subscription from the wallet")
def pay_from_wallet(body: CheckoutRequest, db: DbSession, scope: Tenant,
                    _: None = Depends(require("settings.manage"))) -> dict:
    """
    Settle the renewal from wallet balance. No redirect, no webhook.

    A 409 means the balance does not cover it - that is a normal outcome and the
    UI should offer a top-up, not report an error.
    """
    svc = _service(db)
    try:
        charge = svc.pay_from_wallet(scope.organization_id,
                                     coupon_code=body.coupon_code)
    except CouponError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except DygineError as exc:
        db.commit()          # keep the charge row: it records the attempt
        raise _dygine_error(exc) from None

    db.commit()
    sub, _plan = svc.current_plan(scope.organization_id)
    return {"charge_id": str(charge.id), "status": charge.status,
            "paid_rupees": paise_to_rupees(charge.net_paise),
            "current_period_end": sub.end_date.isoformat() if sub else None}


@router.post("/auto-debit", summary="Turn automatic renewal on or off")
def set_auto_debit(body: AutoDebitRequest, db: DbSession, scope: Tenant,
                   _: None = Depends(require("settings.manage"))) -> dict:
    svc = _service(db)
    prof = svc.profile(scope.organization_id)
    prof.auto_debit_enabled = body.enabled
    db.commit()
    return {"auto_debit_enabled": prof.auto_debit_enabled}
