"""
Seeker accounts: signing up, staying signed in, and enquiring.

See `app/models/seeker.py` for why this is a separate, low-power credential and
not a third principal kind.

There is no seeker password. Signing up and signing in are the same act -
prove an email with a six-digit code - and a person who already has an account
is simply signed in. That removes a password to forget from someone whose whole
relationship with the platform might last a fortnight, and it means "sign in
on my new phone" needs nothing but their inbox.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AuthenticationError, ConflictError, PermissionDeniedError, RateLimitedError,
)
from app.core.security import hash_token
from app.models import Branch, Organization, PgEnquiry, PgSeeker, SeekerSession
from app.models.otp import OtpPurpose
from app.services.otp_service import OtpError, OtpService
from app.services.public_service import PublicService

#: The header a seeker's app sends. Never `Authorization`, so a seeker token can
#: never be mistaken for a staff or resident session by any other endpoint.
SEEKER_HEADER = "X-PGDesk-Seeker"

#: Long, because the device is personal and the token can only send enquiries.
SESSION_DAYS = 180

#: Enough to shortlist a whole neighbourhood in a day; not enough to spam one.
MAX_ENQUIRIES_PER_DAY = 15

#: `last_seen_at` is written at most this often, not on every request.
TOUCH_EVERY = timedelta(hours=1)


class SeekerService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------ sessions
    def start_session(self, *, verification_token: str, full_name: str | None = None,
                      phone: str | None = None, ip: str | None = None,
                      user_agent: str | None = None) -> tuple[PgSeeker, str, bool]:
        """
        Sign in, or sign up, with a verified email.

        Returns `(seeker, raw_token, created)`.

        If the address has no account yet and no name was given, the answer is
        a 409 `needs_profile` and the verification is NOT spent, so the screen
        can ask for a name and send the same token straight back. Without the
        peek, a seeker who tapped "Sign in" instead of "Create account" would
        burn their code and have to wait for another email.
        """
        otp = OtpService(self.db)
        try:
            email = otp.peek(token=verification_token, purpose=OtpPurpose.SIGNUP_EMAIL)
        except OtpError as exc:
            raise AuthenticationError(str(exc), code=exc.code) from None

        seeker = self.db.scalars(select(PgSeeker).where(PgSeeker.email == email)).first()
        name = (full_name or "").strip()
        phone = (phone or "").strip() or None

        if seeker is None and len(name) < 2:
            raise ConflictError(
                "Tell us your name to finish creating your account.",
                code="needs_profile")
        if seeker is not None and not seeker.is_active:
            raise PermissionDeniedError(
                "This account has been switched off. Contact support if that is a mistake.")

        try:
            otp.consume(token=verification_token, purpose=OtpPurpose.SIGNUP_EMAIL)
        except OtpError as exc:
            raise AuthenticationError(str(exc), code=exc.code) from None

        now = datetime.now(timezone.utc)
        created = seeker is None
        if created:
            seeker = PgSeeker(email=email, full_name=name[:160], phone=phone)
            self.db.add(seeker)
            self.db.flush()
        else:
            # A returning seeker who retypes their details is updating them.
            if len(name) >= 2:
                seeker.full_name = name[:160]
            if phone:
                seeker.phone = phone
        seeker.last_seen_at = now

        raw = secrets.token_urlsafe(32)
        self.db.add(SeekerSession(
            seeker_id=seeker.id, token_hash=hash_token(raw),
            expires_at=now + timedelta(days=SESSION_DAYS),
            user_agent=(user_agent or "")[:300] or None, ip_address=ip))
        self.db.flush()
        return seeker, raw, created

    def resolve(self, raw: str | None) -> PgSeeker:
        """The seeker behind a token, or a 401 the app answers by showing sign-in."""
        if not raw:
            raise AuthenticationError("Sign in to continue.", code="seeker_required")
        row = self.db.scalars(select(SeekerSession).where(
            SeekerSession.token_hash == hash_token(raw.strip()))).first()
        now = datetime.now(timezone.utc)
        if row is None or row.revoked_at is not None or row.expires_at <= now:
            raise AuthenticationError(
                "Your session has ended. Sign in again.", code="seeker_session")
        seeker = self.db.get(PgSeeker, row.seeker_id)
        if seeker is None or not seeker.is_active:
            raise AuthenticationError(
                "Your session has ended. Sign in again.", code="seeker_session")
        if seeker.last_seen_at is None or now - seeker.last_seen_at > TOUCH_EVERY:
            seeker.last_seen_at = now
        return seeker

    def logout(self, raw: str | None) -> None:
        if not raw:
            return
        row = self.db.scalars(select(SeekerSession).where(
            SeekerSession.token_hash == hash_token(raw.strip()))).first()
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------- profile
    @staticmethod
    def describe(seeker: PgSeeker) -> dict:
        return {
            "id": str(seeker.id), "email": seeker.email,
            "full_name": seeker.full_name, "phone": seeker.phone,
            "created_at": seeker.created_at.isoformat() if seeker.created_at else None,
        }

    def update_profile(self, seeker: PgSeeker, *, full_name: str | None = None,
                       phone: str | None = None) -> PgSeeker:
        if full_name is not None:
            name = full_name.strip()
            if len(name) < 2:
                raise ConflictError("Enter your name.")
            seeker.full_name = name[:160]
        if phone is not None:
            seeker.phone = phone.strip() or None
        return seeker

    # ----------------------------------------------------------- enquiries
    def send_enquiry(self, seeker: PgSeeker, *, branch_id: uuid.UUID,
                     message: str | None = None, move_in_date: date | None = None,
                     ip: str | None = None) -> PgEnquiry:
        """
        One tap, no code: the email was proved when the account was made.

        Goes through the same `PublicService.create_enquiry` as the anonymous
        path, so the listing checks, the duplicate folding and the owner's
        notification are identical whichever way the enquiry arrives.
        """
        since = datetime.now(timezone.utc) - timedelta(days=1)
        sent_today = self.db.scalar(select(func.count(PgEnquiry.id)).where(
            PgEnquiry.email == seeker.email, PgEnquiry.created_at >= since)) or 0
        if sent_today >= MAX_ENQUIRIES_PER_DAY:
            raise RateLimitedError(
                "You have sent a lot of enquiries today. Please wait for the PGs "
                "to reply, or try again tomorrow.")

        return PublicService(self.db).create_enquiry(
            branch_id=branch_id, full_name=seeker.full_name, email=seeker.email,
            phone=seeker.phone, message=message, move_in_date=move_in_date, ip=ip)

    def enquiries(self, seeker: PgSeeker) -> list[dict]:
        """
        Everything this address has sent, newest first, including enquiries made
        before the account existed - they were proved against the same email.

        A PG that has since unlisted still shows up by name, because it is the
        seeker's own history. Its phone number does not: unlisting withdraws
        that, and this screen must not keep publishing it.
        """
        rows = self.db.execute(
            select(PgEnquiry, Branch, Organization)
            .join(Branch, Branch.id == PgEnquiry.branch_id)
            .join(Organization, Organization.id == PgEnquiry.organization_id)
            .where(PgEnquiry.email == seeker.email)
            .order_by(PgEnquiry.created_at.desc())
            .limit(100)).all()
        return [
            {
                "id": str(e.id),
                "status": e.status,
                "message": e.message,
                "move_in_date": e.move_in_date.isoformat() if e.move_in_date else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "branch_id": str(b.id),
                "pg_name": o.name,
                "branch_name": b.name,
                "city": b.city,
                "listed": bool(b.listed_publicly),
                "contact_phone": b.contact_phone_public if b.listed_publicly else None,
            }
            for e, b, o in rows
        ]
