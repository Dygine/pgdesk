"""Rent, invoices and payments."""
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.dependencies import CurrentScope, DbSession, require, require_tenant
from app.core.exceptions import PermissionDeniedError
from app.core.responses import ok, paginated
from app.models import Invoice, Payment
from app.schemas.operations import (
    InvoiceCancel, InvoiceCreate, InvoiceUpdate, PaymentCreate, PaymentDecision,
    PaymentSettingsUpdate, RefundRequest, RentRun,
)
from app.services.payment_gateway_service import PaymentSettingsService, handle_webhook
from app.services.billing_service import BillingService

router = APIRouter(tags=["billing"])
Tenant = Annotated[CurrentScope, Depends(require_tenant)]


def _svc(db, scope) -> BillingService:
    return BillingService(db, scope)


def _invoice(i: Invoice, *, detail: bool = False) -> dict:
    payload = {
        "id": str(i.id), "invoice_number": i.invoice_number,
        "resident_id": str(i.resident_id),
        "resident": i.resident.full_name if i.resident else None,
        "branch_id": str(i.branch_id),
        "invoice_date": i.invoice_date.isoformat(),
        "due_date": i.due_date.isoformat(),
        "period": i.period.isoformat() if i.period else None,
        "subtotal": float(i.subtotal), "discount": float(i.discount),
        "late_fee": float(i.late_fee), "tax": float(i.tax),
        "total": float(i.total), "paid_amount": float(i.paid_amount),
        "balance": float(i.balance), "status": i.status, "notes": i.notes,
        "days_overdue": max((date.today() - i.due_date).days, 0)
        if float(i.balance) > 0 else 0,
    }
    if detail:
        payload["items"] = [
            {"id": str(it.id), "kind": it.kind, "description": it.description,
             "quantity": float(it.quantity), "unit_price": float(it.unit_price),
             "amount": float(it.amount)}
            for it in i.items]
        payload["payments"] = [
            {"id": str(p.id), "payment_number": p.payment_number,
             "amount": float(p.amount), "method": p.method, "status": p.status,
             "payment_date": p.payment_date.isoformat()}
            for p in i.payments]
    return payload


def _payment(p: Payment) -> dict:
    return {
        "id": str(p.id), "payment_number": p.payment_number,
        "resident_id": str(p.resident_id),
        "resident": p.resident.full_name if p.resident else None,
        "invoice_id": str(p.invoice_id) if p.invoice_id else None,
        "branch_id": str(p.branch_id), "amount": float(p.amount),
        "payment_date": p.payment_date.isoformat(), "method": p.method,
        "reference": p.reference, "notes": p.notes, "status": p.status,
        "verified_at": p.verified_at.isoformat() if p.verified_at else None,
        # desk | resident | razorpay - who put this payment in.
        "source": p.source, "gateway_payment_id": p.gateway_payment_id,
    }


# ---------------------------------------------------------------- invoices
@router.get("/invoices", summary="List invoices")
def list_invoices(db: DbSession, scope: Tenant,
                  _: None = Depends(require("invoices.view")),
                  search: str | None = None,
                  status_filter: str | None = Query(default=None, alias="status"),
                  branch_id: uuid.UUID | None = None,
                  resident_id: uuid.UUID | None = None,
                  from_date: date | None = None, to_date: date | None = None,
                  page: int = Query(default=1, ge=1),
                  page_size: int = Query(default=25, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_invoices(
        search=search, status=status_filter, branch_id=branch_id,
        resident_id=resident_id, from_date=from_date, to_date=to_date,
        page=page, page_size=page_size)
    return paginated([_invoice(i) for i in rows], page, page_size, total)


@router.get("/invoices/{invoice_id}", summary="Invoice detail")
def get_invoice(invoice_id: uuid.UUID, db: DbSession, scope: Tenant,
                _: None = Depends(require("invoices.view"))) -> dict:
    return ok(_invoice(_svc(db, scope).get_invoice(invoice_id), detail=True))


@router.post("/invoices", status_code=status.HTTP_201_CREATED, summary="Raise an invoice")
def create_invoice(body: InvoiceCreate, db: DbSession, scope: Tenant,
                   _: None = Depends(require("invoices.create"))) -> dict:
    data = body.model_dump()
    data["items"] = [i for i in data["items"]]
    invoice = _svc(db, scope).create_invoice(data)
    db.commit()
    db.refresh(invoice)
    return ok(_invoice(invoice, detail=True),
              message=f"Invoice {invoice.invoice_number} raised.")


@router.patch("/invoices/{invoice_id}", summary="Edit an invoice")
def update_invoice(invoice_id: uuid.UUID, body: InvoiceUpdate, db: DbSession,
                   scope: Tenant, _: None = Depends(require("invoices.edit"))) -> dict:
    invoice = _svc(db, scope).update_invoice(
        invoice_id, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(invoice)
    return ok(_invoice(invoice, detail=True), message="Invoice updated.")


@router.post("/invoices/{invoice_id}/cancel", summary="Cancel an invoice")
def cancel_invoice(invoice_id: uuid.UUID, body: InvoiceCancel, db: DbSession,
                   scope: Tenant, _: None = Depends(require("invoices.cancel",
                                                            "invoices.delete"))) -> dict:
    """Refused if verified payments exist - those must be refunded first."""
    invoice = _svc(db, scope).cancel_invoice(invoice_id, body.reason)
    db.commit()
    return ok(_invoice(invoice), message="Invoice cancelled.")


# -------------------------------------------------------------------- rent
@router.post("/rent/generate", summary="Generate this month's rent invoices")
def generate_rent(body: RentRun, db: DbSession, scope: Tenant,
                  _: None = Depends(require("rent.generate", "invoices.create"))) -> dict:
    """
    Idempotent per resident per month, so running it twice adds nothing the
    second time.
    """
    result = _svc(db, scope).generate_rent(period=body.period, branch_id=body.branch_id)
    db.commit()
    return ok(result, message=(f"{result['created']} invoice"
                               f"{'s' if result['created'] != 1 else ''} created, "
                               f"{result['skipped']} already existed."))


@router.post("/rent/late-fees", summary="Apply late fees to overdue invoices")
def apply_late_fees(db: DbSession, scope: Tenant,
                    _: None = Depends(require("rent.manage"))) -> dict:
    count = _svc(db, scope).apply_late_fees()
    db.commit()
    return ok({"updated": count},
              message=f"Late fee applied to {count} invoice{'s' if count != 1 else ''}.")


@router.get("/rent/summary", summary="Rent dashboard")
def rent_summary(db: DbSession, scope: Tenant,
                 _: None = Depends(require("rent.view", "invoices.view")),
                 branch_id: uuid.UUID | None = None,
                 period: date | None = None) -> dict:
    return ok(_svc(db, scope).rent_summary(branch_id=branch_id, period=period))


# ---------------------------------------------------------------- payments
@router.get("/payments", summary="List payments")
def list_payments(db: DbSession, scope: Tenant,
                  _: None = Depends(require("payments.view")),
                  search: str | None = None,
                  status_filter: str | None = Query(default=None, alias="status"),
                  method: str | None = None,
                  branch_id: uuid.UUID | None = None,
                  resident_id: uuid.UUID | None = None,
                  invoice_id: uuid.UUID | None = None,
                  from_date: date | None = None, to_date: date | None = None,
                  page: int = Query(default=1, ge=1),
                  page_size: int = Query(default=25, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list_payments(
        search=search, status=status_filter, method=method, branch_id=branch_id,
        resident_id=resident_id, invoice_id=invoice_id, from_date=from_date,
        to_date=to_date, page=page, page_size=page_size)
    return paginated([_payment(p) for p in rows], page, page_size, total)


@router.post("/payments", status_code=status.HTTP_201_CREATED, summary="Record a payment")
def create_payment(body: PaymentCreate, db: DbSession, scope: Tenant,
                   _: None = Depends(require("payments.create"))) -> dict:
    """
    Recorded as PENDING. Only verification moves the invoice balance, so a note
    at the front desk cannot make an invoice look paid.
    """
    if body.auto_verify and not scope.can("payments.verify"):
        raise PermissionDeniedError(
            "Recording and verifying in one step needs the payment verification "
            "permission.")
    payment = _svc(db, scope).record_payment(
        body.model_dump(exclude={"auto_verify"}), auto_verify=body.auto_verify)
    db.commit()
    return ok(_payment(payment),
              message=f"Payment {payment.payment_number} recorded.")


@router.post("/payments/{payment_id}/verify", summary="Verify or reject a payment")
def verify_payment(payment_id: uuid.UUID, body: PaymentDecision, db: DbSession,
                   scope: Tenant, _: None = Depends(require("payments.verify"))) -> dict:
    payment = _svc(db, scope).verify_payment(
        payment_id, approved=body.approved, note=body.note)
    db.commit()
    return ok(_payment(payment), message=f"Payment {payment.status.lower()}.")


@router.post("/payments/{payment_id}/refund", summary="Refund a verified payment")
def refund_payment(payment_id: uuid.UUID, body: RefundRequest, db: DbSession,
                   scope: Tenant, _: None = Depends(require("payments.refund"))) -> dict:
    payment = _svc(db, scope).refund_payment(payment_id, body.reason)
    db.commit()
    return ok(_payment(payment), message="Payment refunded.")


# ------------------------------------------------------- how residents pay
@router.get("/payment-settings", summary="How residents can pay")
def get_payment_settings(db: DbSession, scope: Tenant,
                         _: None = Depends(require("settings.view"))) -> dict:
    """Reports whether the Razorpay secrets are stored. Never returns them."""
    payload = PaymentSettingsService(db, scope).view()
    db.commit()
    return ok(payload)


@router.put("/payment-settings", summary="Change how residents can pay")
def update_payment_settings(body: PaymentSettingsUpdate, db: DbSession, scope: Tenant,
                            _: None = Depends(require("settings.manage"))) -> dict:
    svc = PaymentSettingsService(db, scope)
    svc.update(body.model_dump(exclude_unset=True))
    db.commit()
    return ok(svc.view(), message="Payment settings saved.")


@router.post("/payment-settings/test-razorpay", summary="Check the Razorpay keys work")
def test_razorpay(db: DbSession, scope: Tenant,
                  _: None = Depends(require("settings.manage"))) -> dict:
    result = PaymentSettingsService(db, scope).test_razorpay()
    return ok(result, message=f"Razorpay accepted the {result['mode']} keys.")


@router.post("/payments/razorpay/webhook/{organization_id}",
             summary="Razorpay webhook (called by Razorpay, not by people)")
async def razorpay_webhook(organization_id: uuid.UUID, request: Request, db: DbSession) -> dict:
    """
    Public on purpose - Razorpay has no PGDesk login. Authenticity comes from the
    X-Razorpay-Signature HMAC over the raw body, keyed with this PG's webhook
    secret; anything that fails it is refused before the body is even parsed.
    """
    raw = await request.body()
    result = handle_webhook(db, organization_id, raw,
                            request.headers.get("X-Razorpay-Signature"))
    db.commit()
    return ok(result)
