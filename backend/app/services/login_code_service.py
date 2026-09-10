"""
Issuing and redeeming QR sign-in keys.

See `app/models/login_code.py` for why a key goes in the QR rather than the
temporary password. The short version: a password cannot expire after thirty
minutes; a key can, and it can only be spent once.

Issuing is a staff action and lives behind `customers.edit` in the residents
router. Redeeming is anonymous - whoever holds the key is, for one sign-in, the
resident - which is exactly why the key is single use, short lived, and dies
the moment a newer one is issued.

One rule keeps this from becoming an impersonation tool: a key is only issued
while the account is on an owner-issued temporary password
(`must_change_password`). Once the resident has chosen their own password, the
PG cannot produce a QR that walks into their account; the only way back in is
a visible password reset, which the resident notices because their password
stops working.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import hash_token
from app.models import Customer, LoginCode, Organization
from app.models.enums import CustomerStatus, OrganizationStatus
from app.utils import qr_payload

#: How long a sign-in QR works. Long enough for "install the app, open it,
#: scan", short enough that a photo of the owner's screen is useless by evening.
LOGIN_CODE_MINUTES = 30


class LoginCodeService:
    def __init__(self, db: Session):
        self.db = db

    # --------------------------------------------------------------- issue
    def issue(self, customer: Customer, *, created_by_id: uuid.UUID | None = None) -> dict:
        """
        Make a fresh key for this resident and retire any older live one.

        Returns what the owner's screen needs: the text to draw as a QR, and
        when it stops working. The raw key exists only in this return value.
        """
        now = datetime.now(timezone.utc)
        self.revoke_all(customer.id, now=now)

        raw = secrets.token_urlsafe(24)
        row = LoginCode(
            organization_id=customer.organization_id, customer_id=customer.id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(minutes=LOGIN_CODE_MINUTES),
            created_by_id=created_by_id)
        self.db.add(row)
        self.db.flush()
        return {
            "payload": qr_payload.encode(qr_payload.KIND_LOGIN, raw),
            "expires_at": row.expires_at.isoformat(),
            "valid_minutes": LOGIN_CODE_MINUTES,
        }

    def revoke_all(self, customer_id: uuid.UUID, *, now: datetime | None = None) -> int:
        """Kill every unspent key for a resident. Used on reissue and on access changes."""
        now = now or datetime.now(timezone.utc)
        rows = list(self.db.scalars(select(LoginCode).where(
            LoginCode.customer_id == customer_id,
            LoginCode.used_at.is_(None), LoginCode.revoked_at.is_(None))).all())
        for row in rows:
            row.revoked_at = now
        return len(rows)

    # -------------------------------------------------------------- redeem
    def redeem(self, raw: str, *, ip: str | None = None,
               user_agent: str | None = None) -> Customer:
        """
        Spend a key and return the resident it signs in.

        Each refusal names its reason. There is nothing to enumerate here - a
        key is 192 random bits, not a guessable identifier - and a resident
        standing at the desk needs to know whether to ask for a new code
        ("expired") or to say something ("already used").
        """
        kind, token = qr_payload.parse(raw)
        if kind in (qr_payload.KIND_RESIDENT, qr_payload.KIND_GATE):
            raise AuthenticationError(
                "That is a gate or resident card, not a sign-in code. Scan the "
                "sign-in QR your PG showed you.", code="wrong_code")
        if not token:
            raise AuthenticationError("That code could not be read.", code="invalid_code")

        # Locked: two phones scanning one screen at the same moment must not
        # both come away with a session.
        row = self.db.scalars(
            select(LoginCode).where(LoginCode.token_hash == hash_token(token))
            .with_for_update()).first()
        now = datetime.now(timezone.utc)

        if row is None:
            raise AuthenticationError(
                "This sign-in code is not valid. Ask your PG for a new one.",
                code="invalid_code")
        if row.used_at is not None:
            raise AuthenticationError(
                "This sign-in code has already been used. If that was not you, "
                "tell your PG so they can reset your access.", code="used_code")
        if row.revoked_at is not None:
            raise AuthenticationError(
                "This code was replaced by a newer one. Scan the latest QR from "
                "your PG.", code="replaced_code")
        if row.expires_at <= now:
            raise AuthenticationError(
                f"This sign-in code has expired - they last {LOGIN_CODE_MINUTES} "
                "minutes. Ask your PG for a new one.", code="expired_code")

        customer = self.db.get(Customer, row.customer_id)
        if customer is None or not customer.password_hash:
            raise AuthenticationError(
                "Portal access for this account has been turned off. "
                "Contact your PG.", code="no_access")
        if not customer.is_active or customer.status in (
                CustomerStatus.CHECKED_OUT, CustomerStatus.ARCHIVED):
            raise PermissionDeniedError(
                "This resident has checked out. The portal is no longer available.")

        org = self.db.get(Organization, customer.organization_id)
        if org and org.status in (OrganizationStatus.SUSPENDED, OrganizationStatus.CANCELLED):
            raise PermissionDeniedError(
                "This PG's account is not currently active. Please contact the front desk.")

        row.used_at = now
        row.used_ip = ip
        row.used_user_agent = (user_agent or "")[:300] or None
        customer.last_login_at = now
        return customer
