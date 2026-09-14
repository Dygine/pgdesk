"""
`/support/platform/*` for the PG owner, `/master/tickets/*` for the operator.

Two routers in one module because they are two ends of the same conversation,
and keeping them together makes it obvious that the owner side never passes
`include_internal=True`.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.dependencies import (
    CurrentScope, CurrentUser, DbSession, require, require_master, require_tenant,
)
from app.core.responses import ok
from app.models import PlatformCharge, PlatformTicket
from app.services.platform_support_service import (
    CATEGORIES, PRIORITIES, PlatformSupportService, payload,
)

log = logging.getLogger("pgguru.api.platform_support")

router = APIRouter(prefix="/support/platform", tags=["platform support"])
master_router = APIRouter(prefix="/master/tickets", tags=["master"])

Tenant = Annotated[CurrentScope, Depends(require_tenant)]
Master = Annotated[CurrentScope, Depends(require_master)]


class TicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=5, max_length=8000)
    category: str = Field(default="question")
    priority: str = Field(default="normal")
    charge_id: uuid.UUID | None = None


class ReplyBody(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class PlatformReply(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    #: A note to yourself. Never shown to the owner, and does not change whose
    #: turn it is.
    internal: bool = False
    status: str | None = None


class StatusChange(BaseModel):
    status: str


# ------------------------------------------------------------------ owner --
@router.get("/meta", summary="Categories and priorities")
def meta(scope: Tenant) -> dict:
    return ok({"categories": sorted(CATEGORIES),
               "priorities": ["low", "normal", "high", "urgent"]})


@router.get("", summary="My tickets")
def list_tickets(db: DbSession, scope: Tenant,
                 _: None = Depends(require("settings.manage"))) -> dict:
    svc = PlatformSupportService(db)
    tickets = svc.for_organization(scope.organization_id)
    return ok([payload(db, t) for t in tickets])


@router.post("", status_code=status.HTTP_201_CREATED, summary="Raise a ticket")
def create_ticket(body: TicketCreate, db: DbSession, user: CurrentUser,
                  scope: Tenant,
                  _: None = Depends(require("settings.manage"))) -> dict:
    charge_id = None
    if body.charge_id:
        # Only a charge belonging to this organisation. An id from elsewhere
        # would attach another PG's payment to this thread.
        charge = db.scalars(select(PlatformCharge).where(
            PlatformCharge.id == body.charge_id,
            PlatformCharge.organization_id == scope.organization_id)).first()
        charge_id = charge.id if charge else None

    svc = PlatformSupportService(db)
    ticket = svc.raise_ticket(
        organization_id=scope.organization_id, user=user,
        subject=body.subject, body=body.body, category=body.category,
        priority=body.priority, charge_id=charge_id)
    db.commit()
    return ok(payload(db, ticket), message="Ticket raised. We will reply here.")


@router.get("/{ticket_id}", summary="One ticket")
def get_ticket(ticket_id: uuid.UUID, db: DbSession, scope: Tenant,
               _: None = Depends(require("settings.manage"))) -> dict:
    ticket = _own_ticket(db, ticket_id, scope.organization_id)
    # include_internal stays False here, always.
    return ok(payload(db, ticket))


@router.post("/{ticket_id}/reply", summary="Reply to a ticket")
def reply(ticket_id: uuid.UUID, body: ReplyBody, db: DbSession,
          user: CurrentUser, scope: Tenant,
          _: None = Depends(require("settings.manage"))) -> dict:
    ticket = _own_ticket(db, ticket_id, scope.organization_id)
    PlatformSupportService(db).reply_as_owner(ticket, user=user, body=body.body)
    db.commit()
    return ok(payload(db, ticket))


@router.post("/{ticket_id}/close", summary="Close my own ticket")
def close_own(ticket_id: uuid.UUID, db: DbSession, user: CurrentUser,
              scope: Tenant,
              _: None = Depends(require("settings.manage"))) -> dict:
    ticket = _own_ticket(db, ticket_id, scope.organization_id)
    PlatformSupportService(db).set_status(ticket, "closed", user=user,
                                          notify=False)
    db.commit()
    return ok(payload(db, ticket))


def _own_ticket(db, ticket_id: uuid.UUID,
                organization_id: uuid.UUID) -> PlatformTicket:
    ticket = db.scalars(select(PlatformTicket).where(
        PlatformTicket.id == ticket_id,
        PlatformTicket.organization_id == organization_id)).first()
    if ticket is None:
        # 404 rather than 403: confirming a ticket exists but belongs to
        # someone else is itself a leak.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket


# --------------------------------------------------------------- operator --
@master_router.get("", summary="The support queue")
def queue(db: DbSession, scope: Master, ticket_status: str | None = None) -> dict:
    svc = PlatformSupportService(db)
    tickets = svc.queue(status=ticket_status)
    return ok({"counts": svc.counts(),
               "data": [payload(db, t, include_internal=True) for t in tickets]})


@master_router.get("/{ticket_id}", summary="One ticket, with internal notes")
def master_ticket(ticket_id: uuid.UUID, db: DbSession, scope: Master) -> dict:
    ticket = db.get(PlatformTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ok(payload(db, ticket, include_internal=True))


@master_router.post("/{ticket_id}/reply", summary="Answer a ticket")
def master_reply(ticket_id: uuid.UUID, body: PlatformReply, db: DbSession,
                 user: CurrentUser, scope: Master) -> dict:
    ticket = db.get(PlatformTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    PlatformSupportService(db).reply_as_platform(
        ticket, user=user, body=body.body, internal=body.internal,
        status=body.status)
    db.commit()
    return ok(payload(db, ticket, include_internal=True))


@master_router.post("/{ticket_id}/status", summary="Change ticket status")
def master_status(ticket_id: uuid.UUID, body: StatusChange, db: DbSession,
                  user: CurrentUser, scope: Master) -> dict:
    ticket = db.get(PlatformTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    try:
        PlatformSupportService(db).set_status(ticket, body.status, user=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    db.commit()
    return ok(payload(db, ticket, include_internal=True))
