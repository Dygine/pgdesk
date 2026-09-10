"""
The unauthenticated surface.

Everything else in this API resolves a principal first and scopes every query to
it. Nothing here has one, which makes this the only router where a mistake is
visible to the whole internet rather than to one tenant. Three rules apply to
every endpoint below and none of them are optional:

  - Read paths return only fields chosen for publication, written out by hand
    so a column added later cannot leak by being caught in a loop.
  - Write paths derive the organisation from a looked-up row, never from the
    request body.
  - Anything that creates an account or sends mail is rate limited and requires
    a proved email address.

The router carries no auth dependency at all, rather than an optional one. An
optional principal is a thing a handler can forget to check.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, Field

from app.core.dependencies import DbSession
from app.core.exceptions import (
    AppError, AuthenticationError, ConflictError, RateLimitedError, ServiceUnavailableError, UpstreamServiceError,
)
from app.core.responses import ok
from app.models.otp import OtpPurpose
from app.services.email_service import (
    EmailNotConfigured, EmailSendFailed, EmailService,
)
from app.services.otp_service import OtpError, OtpService
from app.services.platform_settings_service import PlatformSettingsService
from app.services.public_service import PublicService
from app.services.signup_service import SignupService

router = APIRouter(prefix="/public", tags=["public"])


def _ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ------------------------------------------------------------------ schemas
class SendCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class VerifyCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=4, max_length=10)


class EnquiryRequest(BaseModel):
    """
    An enquiry, plus the token proving the address was verified.

    The token is required rather than optional. Without it this endpoint writes
    an arbitrary name, phone number and message into a PG owner's inbox on
    behalf of an address nobody proved - which is spam with extra steps, and
    worse, spam that looks like a real lead.
    """

    branch_id: uuid.UUID
    verification_token: str = Field(min_length=16, max_length=200)
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=20)
    message: str | None = Field(default=None, max_length=1000)
    move_in_date: date | None = None


class OwnerSignupRequest(BaseModel):
    verification_token: str = Field(min_length=16, max_length=200)
    pg_name: str = Field(min_length=2, max_length=160)
    owner_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=80)
    password: str = Field(min_length=8, max_length=200)


# ------------------------------------------------------------------- search
@router.get("/pgs", summary="Search PGs that have opted into listing")
def search_pgs(db: DbSession,
               latitude: float | None = Query(default=None, ge=-90, le=90),
               longitude: float | None = Query(default=None, ge=-180, le=180),
               radius_km: float | None = Query(default=None, gt=0, le=50),
               city: str | None = None,
               q: str | None = Query(default=None, max_length=120),
               max_rent: float | None = Query(default=None, ge=0),
               gender: str | None = Query(default=None, max_length=10),
               only_vacant: bool = False,
               limit: int = Query(default=20, ge=1, le=60)) -> dict:
    """
    Nearest first when a position is given, cheapest first otherwise.

    Only branches whose owner switched listing on appear, and vacancy is
    reported as a band rather than a count - see `PublicService` for why a
    number would be a gift to anyone mapping a competitor's occupancy.
    """
    results = PublicService(db).search(
        latitude=latitude, longitude=longitude, radius_km=radius_km,
        city=city, query=q, max_rent=max_rent, gender=gender,
        only_vacant=only_vacant, limit=limit)
    return ok(results)


@router.get("/pgs/{branch_id}", summary="One listing")
def get_pg(branch_id: uuid.UUID, db: DbSession) -> dict:
    return ok(PublicService(db).get_listing(branch_id))


# --------------------------------------------------------- email verification
@router.post("/send-code", summary="Email a verification code")
def send_code(body: SendCodeRequest, request: Request, db: DbSession) -> dict:
    """
    Used by both signup and enquiry.

    Unlike the password-reset equivalent, this one may say whether an address is
    already registered - and it deliberately does not, here. The signup endpoint
    reports that clearly at the point of submission, where the person can act on
    it; saying it at the code stage would turn this into an account checker that
    needs no follow-through.
    """
    address = body.email.strip().lower()
    if "@" not in address:
        raise ConflictError("Enter a valid email address.")

    try:
        code = OtpService(db).issue(
            email=address, purpose=OtpPurpose.SIGNUP_EMAIL, ip=_ip(request))
    except OtpError as exc:
        db.commit()
        raise RateLimitedError(str(exc)) from None

    platform = PlatformSettingsService(db).get()
    try:
        EmailService(db).send_otp(
            to=address, code=code, purpose_label="verifying your email address",
            minutes=10, platform_name=platform.platform_name or "PGDesk")
    except EmailNotConfigured:
        db.commit()
        raise ServiceUnavailableError(
            "This platform cannot send email yet. Please contact support.") from None
    except EmailSendFailed as exc:
        db.commit()
        # Reported, unlike in a password reset. There is no address to protect
        # here - the person typed it into a signup form a moment ago - and
        # silence would leave them waiting for a mail that never arrives.
        raise UpstreamServiceError(f"Could not send the code: {exc}") from None

    db.commit()
    return ok({"sent": True},
              message="We sent a 6-digit code to your email. It expires in 10 minutes.")


@router.post("/verify-code", summary="Check a verification code")
def verify_code(body: VerifyCodeRequest, db: DbSession) -> dict:
    try:
        token = OtpService(db).verify(
            email=body.email, purpose=OtpPurpose.SIGNUP_EMAIL, code=body.code)
    except OtpError as exc:
        db.commit()          # the attempt counter must survive the refusal
        raise AuthenticationError(str(exc)) from None
    db.commit()
    return ok({"verification_token": token}, message="Email verified.")


# ---------------------------------------------------------------- enquiries
@router.post("/enquiries", status_code=status.HTTP_201_CREATED,
             summary="Ask a PG about a bed")
def create_enquiry(body: EnquiryRequest, request: Request, db: DbSession) -> dict:
    """
    The resident-side path. No account is created.

    A seeker belongs to no organisation, and every principal in this system is
    scoped to one, so giving them a login would mean a third principal kind
    threaded through the token tables and the isolation rules. For someone whose
    whole interaction is "I saw your listing, call me", a row is the right
    shape. They become a resident through the ordinary check-in flow, which
    already handles beds, rent and invoicing correctly.
    """
    otp = OtpService(db)
    try:
        email = otp.consume(token=body.verification_token,
                            purpose=OtpPurpose.SIGNUP_EMAIL)
    except OtpError as exc:
        db.commit()
        raise AuthenticationError(str(exc)) from None

    enquiry = PublicService(db).create_enquiry(
        branch_id=body.branch_id, full_name=body.full_name, email=email,
        phone=body.phone, message=body.message,
        move_in_date=body.move_in_date, ip=_ip(request))
    db.commit()
    return ok({"id": str(enquiry.id), "status": enquiry.status},
              message="Your enquiry has been sent. The PG will contact you directly.")


# ------------------------------------------------------------------- signup
@router.post("/signup/owner", status_code=status.HTTP_201_CREATED,
             summary="Create a PG account with a free trial")
def signup_owner(body: OwnerSignupRequest, db: DbSession) -> dict:
    """
    Creates the organisation, its owner and a trial subscription together.

    Deliberately does not sign the new owner in. Issuing a session straight from
    a signup means the token path and the login path diverge - different code,
    different throttling, different audit line - and the login they are about to
    do is one form they have already filled in half of.
    """
    otp = OtpService(db)
    try:
        email = otp.consume(token=body.verification_token,
                            purpose=OtpPurpose.SIGNUP_EMAIL)
    except OtpError as exc:
        db.commit()
        raise AuthenticationError(str(exc)) from None

    service = SignupService(db)
    org, owner = service.create_owner(
        pg_name=body.pg_name, owner_name=body.owner_name, email=email,
        phone=body.phone, password=body.password, city=body.city)
    trial_days = service._trial_days()
    db.commit()

    return ok(
        {"organization_id": str(org.id), "organization": org.name,
         "email": owner.email, "trial_days": trial_days},
        message=(f"{org.name} is ready. Your {trial_days}-day free trial has "
                 "started - sign in to set up your first branch."))
