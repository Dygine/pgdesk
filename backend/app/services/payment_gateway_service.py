"""
How residents pay: Razorpay, UPI, or a bank transfer.

Two paths, and the difference between them is the whole design.

**Razorpay** confirms itself. The server creates the order, the resident pays in
Razorpay Checkout, and the payment is recorded VERIFIED only after the server
has checked Razorpay's HMAC signature with the PG's own key secret. The browser
is never trusted to say "it worked". The webhook does the same job for a phone
that dies before the callback fires, and completion is idempotent, so the
callback and the webhook can both arrive and still only one payment is written.

**UPI / bank transfer** is a claim. The resident pays outside the app and types
the transaction number (UTR). That number is mandatory, format-checked and
refused if it was already used - but it proves nothing on its own, so the
payment is PENDING until someone with `payments.verify` matches it against the
bank statement. Only a verified payment moves an invoice balance; that rule
predates this module and it is not relaxed here.

Money paid through Razorpay goes to the PG owner's own Razorpay account.
PGDesk never touches it and never sees card or UPI details.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import uuid
from datetime import date, datetime, timezone
from urllib import error as urlerror, request as urlrequest

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt, is_readable
from app.core.exceptions import (
    AppError, ConflictError, NotFoundError, PermissionDeniedError, UpstreamServiceError,
)
from app.models import (
    Customer, GatewayOrder, Invoice, Organization, Payment, PaymentSettings,
)
from app.models.enums import (
    AuditAction, GatewayOrderStatus, InvoiceStatus, NotificationType, PaymentMethod,
    PaymentSource, PaymentStatus,
)
from app.services.audit import AuditService
from app.services.notification_service import NotificationService

RAZORPAY_API = "https://api.razorpay.com/v1"
TIMEOUT_SECONDS = 20

UPI_ID = re.compile(r"^[A-Za-z0-9.\-_]{2,256}@[A-Za-z][A-Za-z0-9]{1,64}$")
UPI_UTR = re.compile(r"^\d{12}$")
BANK_UTR = re.compile(r"^[A-Za-z0-9]{6,22}$")
IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
MAX_QR_IMAGE_CHARS = 400_000

PLAIN_FIELDS = (
    "razorpay_enabled", "razorpay_key_id", "upi_enabled", "upi_id", "upi_payee_name",
    "qr_image", "bank_enabled", "bank_account_name", "bank_account_number", "bank_ifsc",
    "bank_name", "instructions",
)


# --------------------------------------------------------------- helpers --
class GatewayError(Exception):
    pass


def razorpay_request(method: str, path: str, key_id: str, key_secret: str,
                     body: dict | None = None) -> dict:
    """One call to the Razorpay REST API. Module-level so tests can replace it."""
    token = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    data = json.dumps(body).encode() if body is not None else None
    req = urlrequest.Request(
        f"{RAZORPAY_API}{path}", data=data, method=method,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"})
    try:
        with urlrequest.urlopen(req, timeout=TIMEOUT_SECONDS) as res:   # noqa: S310 - fixed host
            return json.loads(res.read() or b"{}")
    except urlerror.HTTPError as exc:
        try:
            detail = json.loads(exc.read() or b"{}").get("error", {}).get("description")
        except (ValueError, AttributeError):
            detail = None
        if exc.code == 401:
            raise GatewayError(
                "Razorpay rejected these keys. Check the key id and key secret.") from None
        raise GatewayError(f"Razorpay refused the request: {detail or exc.reason}") from None
    except (urlerror.URLError, TimeoutError, OSError):
        raise GatewayError("Could not reach Razorpay. Try again in a minute.") from None


def sign(secret: str, message: str | bytes) -> str:
    raw = message if isinstance(message, bytes) else message.encode()
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def next_payment_number(db: Session, organization_id: uuid.UUID) -> str:
    """Same per-organisation sequence BillingService uses."""
    last = db.scalar(select(func.max(Payment.payment_number))
                     .where(Payment.organization_id == organization_id))
    n = 1
    if last:
        tail = str(last).rsplit("-", 1)[-1]
        if tail.isdigit():
            n = int(tail) + 1
    return f"PAY-{n:05d}"


def settings_row(db: Session, organization_id: uuid.UUID) -> PaymentSettings | None:
    return db.scalars(select(PaymentSettings).where(
        PaymentSettings.organization_id == organization_id)).first()


def razorpay_ready(row: PaymentSettings | None) -> bool:
    return bool(row and row.razorpay_enabled and row.razorpay_key_id
                and is_readable(row.razorpay_key_secret_encrypted))


def resident_options(row: PaymentSettings | None) -> dict:
    """What a resident needs in order to pay. Never a secret."""
    upi = bool(row and row.upi_enabled and row.upi_id)
    bank = bool(row and row.bank_enabled and row.bank_account_number)
    return {
        "online": razorpay_ready(row),
        "razorpay_key_id": row.razorpay_key_id if razorpay_ready(row) else None,
        "upi": {"upi_id": row.upi_id, "payee_name": row.upi_payee_name,
                "qr_image": row.qr_image} if upi else None,
        "bank": {"account_name": row.bank_account_name,
                 "account_number": row.bank_account_number,
                 "ifsc": row.bank_ifsc, "bank_name": row.bank_name} if bank else None,
        "instructions": row.instructions if row else None,
        "any": razorpay_ready(row) or upi or bank,
    }


# ------------------------------------------------------- owner settings --
class PaymentSettingsService:
    def __init__(self, db: Session, scope):
        self.db = db
        self.scope = scope
        self.audit = AuditService(db)

    def get(self) -> PaymentSettings:
        row = settings_row(self.db, self.scope.organization_id)
        if row is None:
            row = PaymentSettings(organization_id=self.scope.organization_id,
                                  razorpay_enabled=False, upi_enabled=False,
                                  bank_enabled=False)
            self.db.add(row)
            self.db.flush()
        return row

    def view(self) -> dict:
        row = self.get()
        payload = {f: getattr(row, f) for f in PLAIN_FIELDS}
        payload.update({
            # Whether a secret is stored and still decryptable - never its value.
            "has_key_secret": bool(row.razorpay_key_secret_encrypted),
            "key_secret_readable": is_readable(row.razorpay_key_secret_encrypted),
            "has_webhook_secret": bool(row.razorpay_webhook_secret_encrypted),
            "online_ready": razorpay_ready(row),
            "mode": ("test" if (row.razorpay_key_id or "").startswith("rzp_test_")
                     else "live" if row.razorpay_key_id else None),
            "webhook_path": f"/payments/razorpay/webhook/{self.scope.organization_id}",
        })
        return payload

    def update(self, data: dict) -> PaymentSettings:
        row = self.get()
        for field in PLAIN_FIELDS:
            if field in data and data[field] is not None:
                value = data[field]
                if isinstance(value, str):
                    value = value.strip() or None
                setattr(row, field, value)
        # Secrets: absent or null = unchanged, "" = remove, anything else = replace.
        for field, column in (("razorpay_key_secret", "razorpay_key_secret_encrypted"),
                              ("razorpay_webhook_secret", "razorpay_webhook_secret_encrypted")):
            if field in data and data[field] is not None:
                value = data[field].strip()
                setattr(row, column, encrypt(value) if value else None)

        if row.razorpay_key_id and not re.match(r"^rzp_(live|test)_[A-Za-z0-9]+$",
                                                row.razorpay_key_id):
            raise ConflictError("A Razorpay key id starts with rzp_live_ or rzp_test_.")
        if row.razorpay_enabled and not razorpay_ready(row):
            raise ConflictError(
                "Add your Razorpay key id and key secret before switching online payments on.")
        if row.upi_id:
            row.upi_id = row.upi_id.lower()
            if not UPI_ID.match(row.upi_id):
                raise ConflictError(
                    "That does not look like a UPI id. It should look like name@bank.")
        if row.upi_enabled and not row.upi_id:
            raise ConflictError("Enter your UPI id before switching UPI payments on.")
        if row.bank_ifsc:
            row.bank_ifsc = row.bank_ifsc.upper()
            if not IFSC.match(row.bank_ifsc):
                raise ConflictError("An IFSC code is 11 characters, like HDFC0001234.")
        if row.bank_account_number and not re.match(r"^\d{6,20}$", row.bank_account_number):
            raise ConflictError("The account number should be 6 to 20 digits.")
        if row.bank_enabled and not (row.bank_account_number and row.bank_ifsc
                                     and row.bank_account_name):
            raise ConflictError(
                "Enter the account holder name, account number and IFSC before "
                "switching bank transfer on.")
        if row.qr_image and (not row.qr_image.startswith("data:image/")
                             or len(row.qr_image) > MAX_QR_IMAGE_CHARS):
            raise ConflictError("The QR image must be a picture under about 300 KB.")

        self.audit.record(
            scope=self.scope, module="Settings", action=AuditAction.UPDATE,
            description="Updated how residents pay",   # never the secret itself
            entity_type="payment_settings", entity_id=row.id)
        return row

    def test_razorpay(self) -> dict:
        row = self.get()
        secret = decrypt(row.razorpay_key_secret_encrypted)
        if not (row.razorpay_key_id and secret):
            raise ConflictError("Save a key id and key secret first.")
        try:
            razorpay_request("GET", "/orders?count=1", row.razorpay_key_id, secret)
        except GatewayError as exc:
            raise UpstreamServiceError(str(exc)) from None
        return {"ok": True,
                "mode": "test" if row.razorpay_key_id.startswith("rzp_test_") else "live"}


# ------------------------------------------------------- resident paying --
class ResidentPaymentService:
    def __init__(self, db: Session, resident: Customer):
        self.db = db
        self.me = resident
        self.notify = NotificationService(db)
        self.audit = AuditService(db)

    def _invoice(self, invoice_id: uuid.UUID) -> Invoice:
        invoice = self.db.scalars(select(Invoice).where(
            Invoice.id == invoice_id, Invoice.resident_id == self.me.id)).first()
        if invoice is None:
            raise NotFoundError("Invoice not found.")
        return invoice

    def payable(self, invoice: Invoice, amount: float | None) -> float:
        """What may be paid now: the balance, less claims already waiting."""
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ConflictError("This invoice was cancelled.")
        pending = round(sum(float(p.amount) for p in invoice.payments
                            if p.status == PaymentStatus.PENDING), 2)
        room = round(float(invoice.balance) - pending, 2)
        if room <= 0.009:
            raise ConflictError(
                "Nothing is left to pay on this invoice"
                + (f" - Rs {pending:,.2f} is waiting for the office to confirm."
                   if pending else "."))
        value = round(float(amount if amount else room), 2)
        if value <= 0:
            raise ConflictError("Enter an amount more than zero.")
        if value > room + 0.009:
            raise ConflictError(f"That is more than what is left to pay (Rs {room:,.2f}).")
        return value

    def submit_manual(self, *, invoice_id: uuid.UUID, amount: float | None, method: str,
                      utr: str, paid_on: date | None = None,
                      note: str | None = None) -> Payment:
        row = settings_row(self.db, self.me.organization_id)
        method = (method or "").upper()
        reference = re.sub(r"\s+", "", utr or "")
        if method == PaymentMethod.UPI:
            if not (row and row.upi_enabled):
                raise ConflictError("UPI payments are not set up for this PG.")
            if not reference:
                raise AppError("Enter the UPI transaction number (UTR). It is required.",
                               code="utr_required")
            if not UPI_UTR.match(reference):
                raise AppError(
                    "A UPI transaction number (UTR) is 12 digits. You will find it in "
                    "the payment details in your UPI app.", code="utr_invalid")
        elif method == PaymentMethod.BANK_TRANSFER:
            if not (row and row.bank_enabled):
                raise ConflictError("Bank transfers are not set up for this PG.")
            if not reference:
                raise AppError("Enter the bank reference number (UTR). It is required.",
                               code="utr_required")
            if not BANK_UTR.match(reference):
                raise AppError(
                    "Enter the bank reference number exactly as shown - 6 to 22 letters "
                    "or digits.", code="utr_invalid")
        else:
            raise ConflictError("Choose UPI or bank transfer.")

        used = self.db.scalars(select(Payment).where(
            Payment.organization_id == self.me.organization_id,
            func.upper(Payment.reference) == reference.upper(),
            Payment.status != PaymentStatus.REJECTED)).first()
        if used:
            raise ConflictError(
                "This transaction number has already been submitted. If you paid twice, "
                "please contact the office.", code="utr_duplicate")
        if paid_on and paid_on > date.today():
            raise ConflictError("The payment date cannot be in the future.")

        invoice = self._invoice(invoice_id)
        value = self.payable(invoice, amount)
        payment = Payment(
            organization_id=self.me.organization_id, branch_id=invoice.branch_id,
            resident_id=self.me.id, invoice_id=invoice.id,
            payment_number=next_payment_number(self.db, self.me.organization_id),
            amount=value, payment_date=paid_on or date.today(), method=method,
            reference=reference, notes=(note or "").strip() or None,
            status=PaymentStatus.PENDING, source=PaymentSource.RESIDENT)
        self.db.add(payment)
        self.db.flush()
        invoice.payments.append(payment)
        invoice.recalculate()

        how = "UPI" if method == PaymentMethod.UPI else "bank transfer"
        self.notify.to_permission_holders(
            self.me.organization_id, "payments.verify", NotificationType.PAYMENT_RECEIVED,
            "Payment to verify",
            f"{self.me.full_name} says they paid Rs {value:,.2f} by {how} for "
            f"{invoice.invoice_number}. UTR {reference}.",
            branch_id=invoice.branch_id, entity_type="payment", entity_id=payment.id)
        self.audit.record(
            scope=None, organization_id=self.me.organization_id, user_name=self.me.full_name,
            module="Payments", action=AuditAction.CREATE,
            description=(f"{self.me.full_name} submitted {payment.payment_number}: "
                         f"{value} by {how}, UTR {reference}"),
            entity_type="payment", entity_id=payment.id, branch_id=invoice.branch_id)
        return payment

    def create_order(self, *, invoice_id: uuid.UUID, amount: float | None = None) -> dict:
        row = settings_row(self.db, self.me.organization_id)
        if not razorpay_ready(row):
            raise ConflictError(
                "Online payment is not set up for this PG. Pay by UPI or at the desk.")
        invoice = self._invoice(invoice_id)
        value = self.payable(invoice, amount)
        secret = decrypt(row.razorpay_key_secret_encrypted)
        try:
            order = razorpay_request("POST", "/orders", row.razorpay_key_id, secret, {
                "amount": int(round(value * 100)), "currency": "INR",
                "receipt": invoice.invoice_number[:40],
                "notes": {"organization_id": str(self.me.organization_id),
                          "invoice_id": str(invoice.id), "resident_id": str(self.me.id)},
            })
        except GatewayError as exc:
            raise UpstreamServiceError(str(exc)) from None
        if not order.get("id"):
            raise UpstreamServiceError("Razorpay did not return an order. Try again.")

        self.db.add(GatewayOrder(
            organization_id=self.me.organization_id, branch_id=invoice.branch_id,
            resident_id=self.me.id, invoice_id=invoice.id, gateway="razorpay",
            order_id=order["id"], amount=value, status=GatewayOrderStatus.CREATED))
        self.db.flush()
        organization = self.db.get(Organization, self.me.organization_id)
        return {
            "order_id": order["id"], "amount": value, "amount_paise": int(round(value * 100)),
            "currency": "INR", "key_id": row.razorpay_key_id,
            "name": organization.name if organization else "Rent",
            "description": f"Invoice {invoice.invoice_number}",
            "prefill": {"name": self.me.full_name, "email": self.me.email or "",
                        "contact": self.me.phone or ""},
        }

    def verify(self, *, order_id: str, payment_id: str, signature: str) -> Payment:
        order = self.db.scalars(select(GatewayOrder).where(
            GatewayOrder.order_id == order_id,
            GatewayOrder.resident_id == self.me.id)).first()
        if order is None:
            raise NotFoundError("Payment order not found.")
        row = settings_row(self.db, self.me.organization_id)
        secret = decrypt(row.razorpay_key_secret_encrypted) if row else None
        if not secret:
            raise ConflictError("Online payment is not set up for this PG any more.")
        if not hmac.compare_digest(sign(secret, f"{order_id}|{payment_id}"), signature or ""):
            raise ConflictError(
                "Could not confirm this payment with Razorpay. If money left your "
                "account, show the office the payment id from Razorpay.",
                code="signature_mismatch")
        return complete_order(self.db, order, payment_id, via="checkout")


# ----------------------------------------------------- order completion --
def complete_order(db: Session, order: GatewayOrder, gateway_payment_id: str, *,
                   via: str) -> Payment:
    """Idempotent. The callback and the webhook may both call this."""
    if order.status == GatewayOrderStatus.PAID and order.payment_id:
        return db.get(Payment, order.payment_id)
    existing = db.scalars(select(Payment).where(
        Payment.gateway_payment_id == gateway_payment_id)).first()
    if existing is not None:
        order.status = GatewayOrderStatus.PAID
        order.payment_id = existing.id
        order.gateway_payment_id = gateway_payment_id
        return existing

    invoice = db.get(Invoice, order.invoice_id) if order.invoice_id else None
    if invoice is not None and invoice.status == InvoiceStatus.CANCELLED:
        invoice = None      # money was still taken; record it unattached
    payment = Payment(
        organization_id=order.organization_id, branch_id=order.branch_id,
        resident_id=order.resident_id, invoice_id=invoice.id if invoice else None,
        payment_number=next_payment_number(db, order.organization_id),
        amount=order.amount, payment_date=date.today(), method=PaymentMethod.ONLINE,
        reference=gateway_payment_id, status=PaymentStatus.VERIFIED,
        verified_at=datetime.now(timezone.utc), source=PaymentSource.RAZORPAY,
        gateway_order_id=order.order_id, gateway_payment_id=gateway_payment_id,
        notes=f"Paid online through Razorpay, confirmed by {via}.")
    db.add(payment)
    db.flush()
    if invoice is not None:
        invoice.payments.append(payment)
        invoice.recalculate()
        if float(invoice.balance) < -0.009:
            payment.notes += " More than the balance was paid - refund or adjust it."
    order.status = GatewayOrderStatus.PAID
    order.payment_id = payment.id
    order.gateway_payment_id = gateway_payment_id

    resident = db.get(Customer, order.resident_id)
    notify = NotificationService(db)
    label = invoice.invoice_number if invoice else "an advance"
    if resident is not None:
        notify.to_permission_holders(
            order.organization_id, "payments.view", NotificationType.PAYMENT_RECEIVED,
            "Online payment received",
            f"{resident.full_name} paid Rs {float(order.amount):,.2f} online for {label}.",
            branch_id=order.branch_id, entity_type="payment", entity_id=payment.id)
        notify.to_resident(
            resident, NotificationType.PAYMENT_VERIFIED, "Payment received",
            f"Rs {float(order.amount):,.2f} paid online for {label}. Thank you.",
            entity_type="payment", entity_id=payment.id, link="/me/rent")
    AuditService(db).record(
        scope=None, organization_id=order.organization_id,
        user_name=resident.full_name if resident else "Razorpay",
        module="Payments", action=AuditAction.CREATE,
        description=f"Razorpay payment {gateway_payment_id} recorded as {payment.payment_number}",
        entity_type="payment", entity_id=payment.id, branch_id=order.branch_id)
    return payment


def handle_webhook(db: Session, organization_id: uuid.UUID, raw_body: bytes,
                   signature: str | None) -> dict:
    row = settings_row(db, organization_id)
    secret = decrypt(row.razorpay_webhook_secret_encrypted) if row else None
    if not secret:
        raise ConflictError("No webhook secret is set for this PG.")
    if not hmac.compare_digest(sign(secret, raw_body), signature or ""):
        raise PermissionDeniedError("Webhook signature does not match.")
    try:
        event = json.loads(raw_body or b"{}")
    except ValueError:
        raise AppError("The webhook body is not JSON.") from None

    kind = event.get("event")
    payload = event.get("payload") or {}
    pay = (payload.get("payment") or {}).get("entity") or {}
    order_entity = (payload.get("order") or {}).get("entity") or {}
    order_id = pay.get("order_id") or order_entity.get("id")
    if not order_id:
        return {"handled": False}
    order = db.scalars(select(GatewayOrder).where(
        GatewayOrder.order_id == order_id,
        GatewayOrder.organization_id == organization_id)).first()
    if order is None:
        return {"handled": False}

    if kind in ("payment.captured", "order.paid") and pay.get("id"):
        payment = complete_order(db, order, pay["id"], via="webhook")
        return {"handled": True, "payment_number": payment.payment_number}
    if kind == "payment.failed" and order.status == GatewayOrderStatus.CREATED:
        order.status = GatewayOrderStatus.FAILED
        order.failure_reason = (pay.get("error_description") or "Payment failed")[:300]
        return {"handled": True}
    return {"handled": False}
