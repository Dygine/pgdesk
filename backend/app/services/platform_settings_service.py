"""
Platform-wide settings.

The row is created on first read rather than by a data migration, so a fresh
database and an upgraded one behave identically and neither needs a seeding step
before the master settings screen works.

`channel_status` is the important part of this module. The settings table stores
whether an operator *wants* email/SMS/WhatsApp; this function reports whether a
channel could actually deliver, by looking for real credentials. The two are
reported separately and never conflated, because a screen that shows WhatsApp as
"on" when no provider is configured is telling the operator a message was sent
when nothing was.
"""
from __future__ import annotations

import os
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.models import PlatformSettings
from app.models.platform import SINGLETON_ID

#: Fields a master admin may write. Anything not listed is ignored rather than
#: rejected, so an older client posting a removed field does not 400.
WRITABLE = {
    "default_trial_days", "grace_period_days", "auto_suspend_after_grace",
    "expiry_warning_days", "notify_email_enabled", "notify_sms_enabled",
    "notify_whatsapp_enabled", "platform_name", "support_email",
}


def channel_status() -> dict[str, dict]:
    """
    What can actually send, right now, on this deployment.

    Configuration is read from the environment rather than the database: these
    are deployment secrets, not tenant preferences, and they must not be
    editable from a web form.
    """
    email_ready = bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))
    sms_ready = bool(os.getenv("SMS_PROVIDER_KEY"))
    whatsapp_ready = bool(os.getenv("WHATSAPP_PROVIDER_KEY")
                          and os.getenv("WHATSAPP_PHONE_ID"))
    return {
        "in_app": {
            "configured": True,
            "detail": "Notifications are written to the database and read by both portals.",
        },
        "email": {
            "configured": email_ready,
            "detail": ("SMTP is configured." if email_ready else
                       "Not configured. Set SMTP_HOST and SMTP_FROM to enable delivery."),
        },
        "sms": {
            "configured": sms_ready,
            "detail": ("An SMS provider is configured." if sms_ready else
                       "Not configured. No SMS provider credentials are present."),
        },
        "whatsapp": {
            "configured": whatsapp_ready,
            "detail": ("A WhatsApp provider is configured." if whatsapp_ready else
                       "Not configured. No WhatsApp provider credentials are present."),
        },
    }


class PlatformSettingsService:
    def __init__(self, db: Session):
        self.db = db

    def get(self) -> PlatformSettings:
        row = self.db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
        if row is None:
            row = PlatformSettings(id=uuid.UUID(SINGLETON_ID))
            self.db.add(row)
            self.db.flush()
        return row

    def update(self, data: dict) -> PlatformSettings:
        row = self.get()
        for key, value in data.items():
            if key in WRITABLE and value is not None:
                setattr(row, key, value)
        self.db.flush()
        return row

    def as_dict(self) -> dict:
        row = self.get()
        return {
            "default_trial_days": row.default_trial_days,
            "grace_period_days": row.grace_period_days,
            "auto_suspend_after_grace": row.auto_suspend_after_grace,
            "expiry_warning_days": row.expiry_warning_days,
            "notify_email_enabled": row.notify_email_enabled,
            "notify_sms_enabled": row.notify_sms_enabled,
            "notify_whatsapp_enabled": row.notify_whatsapp_enabled,
            "platform_name": row.platform_name,
            "support_email": row.support_email,
            # Reported alongside the toggles so the UI can show "enabled but not
            # deliverable" as the distinct state it is.
            "channels": channel_status(),
            "environment": app_settings.environment,
        }
