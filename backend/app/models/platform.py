"""
Platform-level settings.

Deliberately NOT tenant-scoped. `organization_settings` is one row per tenant and
answers "how does this PG run"; this table is one row for the whole installation
and answers "how does the platform treat its tenants" - trial lengths, grace
periods, when a lapsed subscription gets suspended.

A single row is enforced by a CHECK on a fixed primary key rather than by
convention, because "the settings row" being ambiguous is the kind of bug that
only shows up once two rows disagree in production.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Index, Integer, JSON, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import Timestamps, UUIDPrimaryKey

# The one legal primary key. Any other value is rejected by the CHECK below.
SINGLETON_ID = "00000000-0000-0000-0000-000000000001"


class PlatformSettings(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "platform_settings"

    # --- subscription lifecycle ---
    #: 30, because that is what the public signup page offers. A default that
#: disagrees with the marketing copy is a support ticket waiting to happen.
    default_trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    auto_suspend_after_grace: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)
    expiry_warning_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    # --- notification channels ---
    # These are honest booleans about intent. Whether a channel can actually
    # deliver is a separate question answered by `channel_status()` in the
    # service, which checks for real credentials. Turning a switch on here does
    # not make an unconfigured provider start sending.
    notify_email_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)
    notify_sms_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)
    notify_whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)

    # --- outbound mail ---
    #: "smtp" or "brevo". Which transport actually sends.
    #:
    #: Both are kept because they fail in different places. SMTP talks to a mail
    #: server on port 587, which most managed hosts block on their free tiers -
    #: Render closed 25, 465 and 587 outright. An HTTP provider posts to port
    #: 443, which nothing blocks anywhere, so it works on hosting where SMTP
    #: simply cannot. Someone self-hosting on their own VPS has the opposite
    #: preference and wants no third party in the path at all.
    email_provider: Mapped[str] = mapped_column(
        String(20), nullable=False, default="smtp")

    #: Encrypted, like the SMTP password, and equally write-only: the settings
    #: endpoint reports whether a key is stored, never what it is.
    brevo_api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    #: Must be an address verified in the Brevo dashboard. An unverified sender
    #: is rejected at send time with an error that reads like a code fault.
    brevo_sender_email: Mapped[str | None] = mapped_column(String(255))
    brevo_sender_name: Mapped[str | None] = mapped_column(String(120))
    brevo_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Stored here rather than only in the environment so an operator can change
    # a mail password without a redeploy. The environment still wins when set,
    # so existing deployments keep behaving exactly as they did.
    #
    # The password is encrypted (app/core/crypto.py) and is never returned by
    # the API - the settings endpoint reports whether one is stored, not what it
    # is. A write-only field is the only shape that lets a form save a secret
    # without also being a way to read it back.
    smtp_host: Mapped[str | None] = mapped_column(String(255))
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_username: Mapped[str | None] = mapped_column(String(255))
    smtp_password_encrypted: Mapped[str | None] = mapped_column(Text)
    smtp_from_email: Mapped[str | None] = mapped_column(String(255))
    smtp_from_name: Mapped[str | None] = mapped_column(String(120))
    #: STARTTLS on the submission port (587). Turn off only for implicit TLS on
    #: 465, which `smtp_use_ssl` covers, or for a local relay that has neither.
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    smtp_use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Set on a successful test send. The screen shows it so an operator can
    #: tell "saved" from "actually delivered a message", which are not the same
    #: claim and are routinely confused.
    smtp_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- sessions ---
    #: How long a signed-in phone stays signed in. Ten years by default, which
    #: is "until the app is removed" in practice. Kept as a number rather than a
    #: boolean so an operator who decides that is too long for staff can shorten
    #: it without a code change.
    native_session_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3650)

    # --- platform identity ---
    platform_name: Mapped[str] = mapped_column(
        String(80), nullable=False, default="PGuru")
    support_email: Mapped[str | None] = mapped_column(String(255))

    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(f"id = '{SINGLETON_ID}'", name="ck_platform_settings_singleton"),
        CheckConstraint("default_trial_days BETWEEN 0 AND 365",
                        name="ck_platform_trial_days"),
        CheckConstraint("grace_period_days BETWEEN 0 AND 90",
                        name="ck_platform_grace_days"),
        CheckConstraint("expiry_warning_days BETWEEN 0 AND 90",
                        name="ck_platform_warning_days"),
        CheckConstraint("smtp_port BETWEEN 1 AND 65535", name="ck_platform_smtp_port"),
        CheckConstraint("email_provider IN ('smtp', 'brevo')",
                        name="ck_platform_email_provider"),
        CheckConstraint("native_session_days BETWEEN 1 AND 3650",
                        name="ck_platform_native_session_days"),
    )


class LoginAttempt(Base, UUIDPrimaryKey, Timestamps):
    """
    Every sign-in attempt, successful or not.

    Persisted rather than counted in memory because a lockout that resets when a
    worker restarts is not a lockout, and an API behind more than one process
    would otherwise give an attacker one budget per worker.

    Deliberately stores no password and no token - only who was asked for, from
    where, and whether it worked. `identifier` is the email as submitted, which
    may not correspond to any account; that is the point, since attempts against
    addresses that do not exist are exactly what a spray looks like.
    """
    __tablename__ = "login_attempts"

    identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), index=True)
    successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (
        Index("ix_login_attempts_identifier_time", "identifier", "created_at"),
        Index("ix_login_attempts_ip_time", "ip_address", "created_at"),
    )
