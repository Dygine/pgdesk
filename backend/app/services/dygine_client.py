"""
The only place PGGuru talks to Dygine Pay.

Credentials come from `PlatformSettings`, not the environment, so the operator
can rotate a key from master admin without a redeploy - the same decision the
SMTP password already makes.

Everything here raises `DygineError` on failure and never returns a half-answer.
A billing screen that renders a balance it could not actually fetch is worse
than one that says it could not reach the payments service: the first leads
someone to believe they have money they may not have.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import uuid

import httpx
from sqlalchemy.orm import Session

from app.core.crypto import decrypt
from app.models import PlatformSettings
from app.models.platform import SINGLETON_ID

log = logging.getLogger("pgguru.dygine")

TIMEOUT = 20.0
DEFAULT_BASE_URL = "https://pay.dygine.com"


class DygineError(Exception):
    """A call to Dygine failed. `code` carries Dygine's own error code."""

    def __init__(self, message: str, *, status: int = 0, code: str = "",
                 detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.detail = detail or {}

    @property
    def is_insufficient_balance(self) -> bool:
        return self.code == "insufficient_balance"

    @property
    def is_unreachable(self) -> bool:
        """Network-level failure, as opposed to Dygine refusing the request."""
        return self.status == 0


class DygineNotConfigured(DygineError):
    """No credentials saved yet. Distinguished so callers can say so plainly."""


class DygineClient:
    def __init__(self, db: Session):
        self.db = db
        self._settings: PlatformSettings | None = None

    # ------------------------------------------------------------ config --
    def settings(self) -> PlatformSettings | None:
        if self._settings is None:
            try:
                self._settings = self.db.get(
                    PlatformSettings, uuid.UUID(SINGLETON_ID))
            except Exception:                    # noqa: BLE001
                return None
        return self._settings

    @property
    def enabled(self) -> bool:
        row = self.settings()
        return bool(row and row.dygine_enabled and row.dygine_key_id
                    and row.dygine_key_secret_encrypted)

    @property
    def base_url(self) -> str:
        row = self.settings()
        raw = (row.dygine_base_url if row and row.dygine_base_url
               else DEFAULT_BASE_URL)
        return raw.strip().rstrip("/")

    def webhook_secret(self) -> str | None:
        row = self.settings()
        return decrypt(row.dygine_webhook_secret_encrypted) if row else None

    def _auth_header(self) -> str:
        row = self.settings()
        if row is None or not row.dygine_key_id:
            raise DygineNotConfigured(
                "Dygine Pay is not configured. Add the key pair in "
                "master admin settings.")
        secret = decrypt(row.dygine_key_secret_encrypted)
        if not secret:
            raise DygineNotConfigured(
                "The Dygine key secret could not be read. It may have been "
                "saved with a different encryption key - re-enter it.")
        # Stripped again here, not only on save, so a value stored before this
        # was fixed starts working without anyone having to re-enter it.
        token = base64.b64encode(
            f"{row.dygine_key_id.strip()}:{secret.strip()}".encode()).decode()
        return f"Basic {token}"

    # ---------------------------------------------------------- plumbing --
    def _call(self, method: str, path: str, body: dict | None = None,
              idempotency_key: str | None = None) -> dict:
        if not self.enabled:
            raise DygineNotConfigured(
                "Dygine Pay is not enabled. Turn it on in master admin "
                "settings and save a key pair.")

        headers = {"Authorization": self._auth_header(),
                   "Content-Type": "application/json"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                res = client.request(method, f"{self.base_url}{path}",
                                     json=body, headers=headers)
        except httpx.RequestError as exc:
            log.warning("dygine unreachable: %s %s - %s", method, path, exc)
            raise DygineError(
                "Could not reach the payments service. Nothing was charged.",
            ) from None

        if res.status_code >= 400:
            try:
                err = res.json().get("error", {})
            except ValueError:
                err = {}
            message = err.get("message") or res.text[:300]
            log.warning("dygine %s %s -> %s %s", method, path,
                        res.status_code, message)

            # Say what to do about it. "Invalid API credentials" is Dygine's
            # message and it is accurate, but on its own it does not tell an
            # operator which of the two values to look at - and the stored
            # secret cannot be read back to compare.
            if res.status_code == 401:
                message = (
                    "Dygine rejected these credentials. Check the key id is "
                    "exactly what Dygine admin shows, and re-enter the key "
                    "secret - it is the part AFTER the colon on the line shown "
                    "when the key was issued, not the whole line.")

            # A non-JSON body means we did not reach the application at all -
            # usually a sleeping free instance answering with its own error
            # page. Pasting that HTML into a toast helps nobody.
            if not err and res.headers.get("content-type", "").startswith("text/"):
                message = ("The payments service is not responding. If it is on "
                           "a free plan it may be asleep - open its /health URL "
                           "once and try again.")

            raise DygineError(message, status=res.status_code,
                              code=err.get("code", ""),
                              detail=err.get("detail", {}))

        return res.json() if res.content else {}

    # ---------------------------------------------------------- checkout --
    def create_checkout(self, *, customer: dict, line_items: list[dict],
                        purpose: str, idempotency_key: str,
                        success_url: str | None = None,
                        cancel_url: str | None = None,
                        notes: dict | None = None) -> dict:
        """
        Create a hosted payment and get a URL to send the owner to.

        The idempotency key must be stable for the attempt, not random. A key of
        `sub:{org}:{period}` means a double-clicked renew button creates one
        order; a fresh uuid means two.
        """
        body: dict = {"customer": customer, "line_items": line_items,
                      "purpose": purpose}
        if success_url:
            body["success_url"] = success_url
        if cancel_url:
            body["cancel_url"] = cancel_url
        if notes:
            body["notes"] = notes
        return self._call("POST", "/v1/checkout/sessions", body, idempotency_key)

    def get_payment(self, reference: str) -> dict:
        """
        Always safe to call. This is the self-heal path for a webhook we never
        received - poll it rather than assuming a payment did not happen.
        """
        return self._call("GET", f"/v1/payments/{reference}")

    # ------------------------------------------------------------ wallet --
    def wallet_balance(self, external_id: str) -> int:
        """Balance in paise. Cheap call - no transaction list."""
        data = self._call("GET",
                          f"/v1/customers/{external_id}/wallet?balance_only=1")
        return int(data.get("balance") or 0)

    def wallet_detail(self, external_id: str) -> dict:
        return self._call("GET", f"/v1/customers/{external_id}/wallet")

    def wallet_debit(self, external_id: str, amount_paise: int, *,
                     description: str, idempotency_key: str,
                     reference_type: str | None = None,
                     reference_id: str | None = None) -> dict:
        """
        Spend wallet balance.

        Raises DygineError with `is_insufficient_balance` when there is not
        enough. Callers must treat that as a normal outcome and offer a top-up,
        not as an outage.
        """
        return self._call("POST", "/v1/wallet/debit", {
            "customer_external_id": external_id,
            "amount": amount_paise,
            "description": description,
            "reference_type": reference_type,
            "reference_id": reference_id,
        }, idempotency_key)

    # ---------------------------------------------------------- customer --
    def upsert_customer(self, **fields) -> dict:
        return self._call("POST", "/v1/customers", fields)

    # ---------------------------------------------------------- invoices --
    def list_invoices(self, external_id: str) -> list[dict]:
        return self._call(
            "GET", f"/v1/customers/{external_id}/invoices").get("data", [])

    def invoice_pdf_url(self, invoice_id: str) -> str:
        return f"{self.base_url}/v1/invoices/{invoice_id}/pdf"

    # ------------------------------------------------------------- probe --
    def verify(self) -> dict:
        """
        Prove the credentials actually work, for the master admin settings page.

        Calls a harmless read. "Saved" and "works" are different claims, and a
        wrong secret saves perfectly.
        """
        data = self._call("GET", "/v1/plans")
        row = self.settings()
        if row is not None:
            from datetime import datetime, timezone
            row.dygine_verified_at = datetime.now(timezone.utc)
            self.db.flush()
        return {"ok": True, "plans": len(data.get("data", []))}


def verify_webhook(secret: str, raw_body: bytes, signature_header: str) -> bool:
    """
    Verify a webhook from Dygine.

    Must be given the RAW request body. Parsing the JSON and re-serialising it
    changes the bytes, the signature stops matching, and the tempting fix for
    that is to stop verifying - which leaves an endpoint anyone can forge into
    extending subscriptions for free.
    """
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}",
                               (signature_header or "").strip())
