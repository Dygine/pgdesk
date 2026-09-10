"""
Accounts for people looking for a PG.

A separate router from `public` because every endpoint here, except signing in,
needs a seeker session - but a seeker session is not a principal. It is read
from its own header by its own dependency and accepted nowhere else in the API,
so a seeker token can never reach tenant data. See app/models/seeker.py.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, Field

from app.core.dependencies import DbSession
from app.core.responses import ok
from app.models import PgSeeker
from app.services.seeker_service import SeekerService

router = APIRouter(prefix="/public/seeker", tags=["public"])


def _ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def current_seeker(db: DbSession,
                   x_pgdesk_seeker: Annotated[str | None, Header()] = None) -> PgSeeker:
    """The seeker behind `X-PGDesk-Seeker`, or a 401 the app answers with sign-in."""
    return SeekerService(db).resolve(x_pgdesk_seeker)


CurrentSeeker = Annotated[PgSeeker, Depends(current_seeker)]


# ------------------------------------------------------------------ schemas
class SessionRequest(BaseModel):
    """
    A verified email, plus a name when this is a new account.

    Leave the name out to mean "sign me in". If there is no account yet the
    reply is 409 `needs_profile` and the verification is kept, so the app can
    ask for a name and send the same token straight back.
    """
    verification_token: str = Field(min_length=16, max_length=200)
    full_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=20)


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=20)


class SeekerEnquiry(BaseModel):
    branch_id: uuid.UUID
    message: str | None = Field(default=None, max_length=1000)
    move_in_date: date | None = None


# ---------------------------------------------------------------- sessions
@router.post("/session", summary="Sign in or create an account with a verified email")
def start_session(body: SessionRequest, request: Request, db: DbSession) -> dict:
    seeker, token, created = SeekerService(db).start_session(
        verification_token=body.verification_token, full_name=body.full_name,
        phone=body.phone, ip=_ip(request), user_agent=request.headers.get("user-agent"))
    payload = {"token": token, "seeker": SeekerService.describe(seeker), "created": created}
    db.commit()
    return ok(payload, message=("Your account is ready." if created
                                else f"Welcome back, {seeker.full_name}."))


@router.post("/logout", summary="Sign out on this device")
def logout(db: DbSession, x_pgdesk_seeker: Annotated[str | None, Header()] = None) -> dict:
    SeekerService(db).logout(x_pgdesk_seeker)
    db.commit()
    return ok(None, message="Signed out.")


# ----------------------------------------------------------------- profile
@router.get("/me", summary="The signed-in seeker")
def me(seeker: CurrentSeeker, db: DbSession) -> dict:
    payload = SeekerService.describe(seeker)
    db.commit()                 # resolve() may have touched last_seen_at
    return ok(payload)


@router.patch("/me", summary="Update name or phone")
def update_me(body: ProfileUpdate, seeker: CurrentSeeker, db: DbSession) -> dict:
    SeekerService(db).update_profile(seeker, full_name=body.full_name, phone=body.phone)
    payload = SeekerService.describe(seeker)
    db.commit()
    return ok(payload, message="Profile saved.")


# --------------------------------------------------------------- enquiries
@router.get("/enquiries", summary="Enquiries this seeker has sent")
def my_enquiries(seeker: CurrentSeeker, db: DbSession) -> dict:
    rows = SeekerService(db).enquiries(seeker)
    db.commit()
    return ok(rows)


@router.post("/enquiries", status_code=status.HTTP_201_CREATED,
             summary="Enquire at a listed PG in one tap")
def send_enquiry(body: SeekerEnquiry, request: Request, seeker: CurrentSeeker,
                 db: DbSession) -> dict:
    enquiry = SeekerService(db).send_enquiry(
        seeker, branch_id=body.branch_id, message=body.message,
        move_in_date=body.move_in_date, ip=_ip(request))
    db.commit()
    return ok({"id": str(enquiry.id), "status": enquiry.status},
              message="Enquiry sent. The PG will contact you directly.")
