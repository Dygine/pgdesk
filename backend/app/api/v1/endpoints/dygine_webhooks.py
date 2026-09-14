"""
Inbound from Dygine Pay.

Unauthenticated by design - Dygine has no session with us - so the HMAC
signature is the *only* thing standing between a stranger and a free
subscription. Three rules, none of them optional:

**Verify over the raw bytes, before parsing.** Reading the body as JSON and
re-serialising it changes the bytes, the signature stops matching, and the
tempting fix for that is to stop verifying. Never parse first.

**Store before acting.** An event that was applied but never recorded cannot be
replayed when the handler turns out to have a bug, and there is no way to answer
"did we receive that?" three days later.

**Deduplicate on Dygine's event id.** Every webhook system redelivers eventually.
Without the unique constraint a redelivery extends a subscription twice.

The endpoint returns 200 once the event is stored, even if applying it failed.
A 500 makes Dygine retry into the same failing code path; the stored row can be
replayed deliberately once the bug is fixed.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models import DygineEvent
from app.services.dygine_client import DygineClient, verify_webhook
from app.services.platform_billing_service import PlatformBillingService

log = logging.getLogger("pgguru.dygine.webhook")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/dygine", summary="Payment events from Dygine Pay")
async def dygine_webhook(
    request: Request,
    x_dygine_signature: str | None = Header(default=None),
    x_dygine_event_id: str | None = Header(default=None),
):
    raw = await request.body()

    # A fresh session, not the request-scoped dependency: this handler commits
    # the stored event independently of whether applying it succeeds, and the
    # two must not share a transaction.
    db = SessionLocal()
    try:
        secret = DygineClient(db).webhook_secret()
        if not secret:
            # No secret configured means nothing can be verified, and an
            # unverifiable endpoint that acts on its input is an open door.
            log.error("dygine webhook received but no webhook secret is set")
            return JSONResponse(status_code=503,
                                content={"error": "webhook secret not configured"})

        if not verify_webhook(secret, raw, x_dygine_signature or ""):
            log.warning("rejected dygine webhook with bad signature")
            # 400, not 401: a body we cannot verify will not become verifiable
            # on a retry, and Dygine treats 4xx as "do not redeliver".
            return JSONResponse(status_code=400,
                                content={"error": "invalid signature"})

        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            return JSONResponse(status_code=400,
                                content={"error": "malformed body"})

        event_type = payload.get("event", "")
        event_id = (x_dygine_event_id or payload.get("event_id")
                    or f"{event_type}:{hash(raw)}")

        event = DygineEvent(
            event_id=event_id, event_type=event_type,
            signature=x_dygine_signature,
            raw_body=raw.decode("utf-8", "replace"), payload=payload)
        db.add(event)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            log.info("duplicate dygine event %s ignored", event_id)
            return JSONResponse(status_code=200, content={"status": "duplicate"})

        try:
            PlatformBillingService(db).handle_event(event)
            event.processed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:                 # noqa: BLE001
            db.rollback()
            log.exception("failed to apply dygine event %s", event_id)
            fresh = db.scalars(select(DygineEvent).where(
                DygineEvent.event_id == event_id)).first()
            if fresh is not None:
                fresh.process_error = str(exc)[:2000]
                db.commit()
            # Still 200: the event is safely stored and can be replayed.
            return JSONResponse(status_code=200,
                                content={"status": "stored", "applied": False})

        return JSONResponse(status_code=200, content={"status": "ok"})
    finally:
        db.close()
