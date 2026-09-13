"""
The loop that actually delivers, and the daily rent reminder.

Why a loop inside the web process
---------------------------------
The alternative is a worker service, which on Render is a second paid instance,
and a queue broker, which is a third. For a deployment measured in hundreds of
residents that is infrastructure bought to solve a problem nobody has yet.

What makes an in-process loop safe here is that the queue is a database table,
not memory. Nothing is lost when the process restarts mid-sweep - a row without
`pushed_at` is simply still pending - and `SKIP LOCKED` means running several
web workers gives each sweep a different batch instead of delivering everything
twice.

The honest cost: delivery is up to `SWEEP_SECONDS` late, and a host that sleeps
an idle instance delivers nothing until it wakes. Both are fine for invoices,
announcements and rent reminders. Neither would be fine for chat, which this is
not.

When one PG outgrows this, `PushService.dispatch_pending` is unchanged and gets
called from a real worker instead. That is the reason delivery state lives on
the row rather than in this module.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Customer, Invoice, Notification, PlatformSettings
from app.models.enums import NotificationType
from app.models.platform import SINGLETON_ID
from app.services.push_service import PushService

log = logging.getLogger("pgguru.push.dispatcher")

#: How often the queue is drained. Ten seconds is under the threshold where a
#: person posting an announcement and watching their own phone would call it
#: broken, and far above the rate at which an idle database would notice.
SWEEP_SECONDS = 10

#: Reminders are checked this often. Hourly rather than daily so a deploy or a
#: restart cannot skip the one moment in the day the job would have run.
REMINDER_CHECK_SECONDS = 3600


# --------------------------------------------------------------- rent reminders
def send_rent_reminders(db) -> int:
    """
    Warn residents whose invoice falls due in `rent_reminder_days`.

    The existing code notifies once, when the invoice is created - which for an
    invoice raised three weeks early is a message nobody remembers by the time
    the money is actually due. This is the second touch.

    Idempotent by construction: an invoice already carrying a reminder
    notification is skipped. Without that, an hourly check would remind the same
    person twenty-four times a day, and rent reminders are exactly the kind of
    message that turns people off notifications for good.
    """
    row = db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
    if row is None or row.rent_reminder_days <= 0:
        return 0

    target = date.today() + timedelta(days=row.rent_reminder_days)

    invoices = list(db.scalars(
        select(Invoice).where(Invoice.due_date == target)))
    if not invoices:
        return 0

    sent = 0
    for invoice in invoices:
        # Settled, cancelled or not yet issued. A DRAFT invoice is one the
        # office is still editing - reminding a resident about a number that
        # may still change is worse than not reminding them at all.
        if str(invoice.status).upper() in {"PAID", "CANCELLED", "DRAFT"}:
            continue

        already = db.scalar(
            select(Notification.id).where(
                Notification.entity_type == "invoice_reminder",
                Notification.entity_id == invoice.id).limit(1))
        if already:
            continue

        resident = db.get(Customer, invoice.resident_id)
        if resident is None or not resident.is_active:
            continue

        db.add(Notification(
            organization_id=invoice.organization_id,
            resident_id=resident.id,
            kind=NotificationType.RENT_DUE,
            title="Rent due soon",
            message=(f"Invoice {invoice.invoice_number} for {invoice.total} "
                     f"is due on {invoice.due_date}."),
            entity_type="invoice_reminder", entity_id=invoice.id,
            link="/me/rent"))
        sent += 1

    if sent:
        db.commit()
        log.info("Queued %d rent reminder(s) for %s", sent, target)
    return sent


# ----------------------------------------------------------------- the loops
async def _sweep_loop() -> None:
    """Drain the push queue for ever, forgiving every error."""
    while True:
        await asyncio.sleep(SWEEP_SECONDS)
        try:
            # A session per tick, never one held open across sleeps. A
            # long-lived session pins a connection from a pool sized for
            # request traffic, and holds a snapshot that goes stale within
            # seconds of being opened.
            db = SessionLocal()
            try:
                result = await asyncio.to_thread(
                    PushService(db).dispatch_pending)
                if result.get("sent") or result.get("failed"):
                    db.commit()
                    log.info("Push sweep: %s", result)
                else:
                    db.rollback()
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never let one bad tick end the loop. A dispatcher that dies
            # silently on the first transient database blip is worse than no
            # dispatcher, because the symptom is indistinguishable from
            # "nobody posted anything".
            log.exception("Push sweep failed; continuing")


async def _reminder_loop() -> None:
    while True:
        await asyncio.sleep(REMINDER_CHECK_SECONDS)
        try:
            db = SessionLocal()
            try:
                await asyncio.to_thread(send_rent_reminders, db)
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Rent reminder run failed; continuing")


_tasks: list[asyncio.Task] = []


def start(enabled: bool = True) -> None:
    """Launch the loops. Called once from the app lifespan."""
    if not enabled or _tasks:
        return
    loop = asyncio.get_event_loop()
    _tasks.append(loop.create_task(_sweep_loop()))
    _tasks.append(loop.create_task(_reminder_loop()))
    log.info("Push dispatcher started (sweep every %ss)", SWEEP_SECONDS)


async def stop() -> None:
    """Cancel the loops on shutdown so a reload does not stack duplicates."""
    for task in _tasks:
        task.cancel()
    for task in _tasks:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _tasks.clear()
