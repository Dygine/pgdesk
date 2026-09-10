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

from datetime import datetime, timezone

from app.core.config import settings as app_settings
from app.core.crypto import encrypt, is_readable
from app.models import PlatformSettings
from app.models.platform import SINGLETON_ID

#: Fields a master admin may write. Anything not listed is ignored rather than
#: rejected, so an older client posting a removed field does not 400.
WRITABLE = {
    "default_trial_days", "grace_period_days", "auto_suspend_after_grace",
    "expiry_warning_days", "notify_email_enabled", "notify_sms_enabled",
    "notify_whatsapp_enabled", "platform_name", "support_email",
    # Mail server. The password is deliberately NOT here - it takes a different
    # path (`set_smtp_password`) because it must be encrypted on the way in and
    # must never come back out. Listing it as an ordinary writable field would
    # eventually see it echoed by a serializer that treats every column alike.
    "smtp_host", "smtp_port", "smtp_username", "smtp_from_email",
    "smtp_from_name", "smtp_use_tls", "smtp_use_ssl",
    "native_session_days",
}


def channel_status(db: Session | None = None) -> dict[str, dict]:
    """
    What can actually send, right now, on this deployment.

    Email now has two possible sources. The environment still wins, because a
    deployment already configured that way must not change behaviour, and
    because an operator cannot lock themselves out of mail by saving a bad form.
    Falling back to the database is what lets a master admin set a mail server
    without a redeploy - which is the difference between a mail password that
    gets rotated and one that never does.

    `db` is optional so the older env-only call sites keep working.
    """
    email_ready = bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))
    email_source = "environment"
    if not email_ready and db is not None:
        row = db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
        if row is not None and row.smtp_host and row.smtp_from_email:
            email_ready = True
            email_source = "platform settings"
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
            "source": email_source if email_ready else None,
            "detail": (f"SMTP is configured ({email_source})." if email_ready else
                       "Not configured. Set a mail server below, or supply "
                       "SMTP_HOST and SMTP_FROM in the environment."),
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
            "native_session_days": row.native_session_days,

            # --- mail server ---
            "smtp_host": row.smtp_host,
            "smtp_port": row.smtp_port,
            "smtp_username": row.smtp_username,
            "smtp_from_email": row.smtp_from_email,
            "smtp_from_name": row.smtp_from_name,
            "smtp_use_tls": row.smtp_use_tls,
            "smtp_use_ssl": row.smtp_use_ssl,
            "smtp_verified_at": (row.smtp_verified_at.isoformat()
                                 if row.smtp_verified_at else None),
            # Whether a password is stored, never the password. A settings
            # endpoint that returns the secret it was given is a way to read
            # secrets, not a way to configure them - and the form only needs to
            # know whether to show "change password" or "set password".
            "smtp_password_set": bool(row.smtp_password_encrypted),
            "smtp_password_readable": is_readable(row.smtp_password_encrypted),

            # Reported alongside the toggles so the UI can show "enabled but not
            # deliverable" as the distinct state it is.
            "channels": channel_status(self.db),
            "environment": app_settings.environment,
        }

    def set_smtp_password(self, plaintext: str | None) -> None:
        """
        Store or clear the mail password.

        Separate from `update` because the value is encrypted on the way in and
        has no way out. An empty string clears it, which is how an operator
        moves to a relay that needs no authentication - distinct from omitting
        the field, which leaves the stored one alone.
        """
        row = self.get()
        row.smtp_password_encrypted = encrypt(plaintext) if plaintext else None
        # Saving new credentials invalidates the previous proof of delivery.
        # Leaving the old timestamp would show a green "verified" tick beside a
        # password nobody has ever successfully sent with.
        row.smtp_verified_at = None
        self.db.flush()

    def mark_smtp_verified(self) -> None:
        row = self.get()
        row.smtp_verified_at = datetime.now(timezone.utc)
        self.db.flush()
