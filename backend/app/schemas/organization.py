"""Master-admin contracts: organisations, plans, subscriptions, usage."""
import uuid
from datetime import date, datetime

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class PlanOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    price: int
    billing_cycle: str
    support_level: str | None = None
    features: list = Field(default_factory=list)
    status: str
    sort_order: int
    limits: dict[str, int] = Field(default_factory=dict)


class PlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: int | None = Field(default=None, ge=0)
    support_level: str | None = None
    features: list[str] | None = None
    status: str | None = None
    limits: dict[str, int] | None = Field(
        default=None, description="Any of: branches, buildings, floors, rooms, beds, "
                                  "customers, users, admins, storage_gb, monthly_transactions",
    )


class SubscriptionOut(ORMModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    plan_name: str | None = None
    plan_code: str | None = None
    start_date: date
    end_date: date
    trial_end_date: date | None = None
    status: str
    is_current: bool
    days_remaining: int | None = None
    limits: dict[str, int] = Field(default_factory=dict)


class OrganizationOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    legal_name: str | None = None
    owner_name: str
    owner_email: str
    owner_phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    gstin: str | None = None
    pg_type: str | None = None
    gender: str | None = None
    notes: str | None = None
    status: str
    storage_used_gb: float = 0
    onboarded_on: date | None = None
    created_at: datetime

    subscription: SubscriptionOut | None = None
    counts: dict[str, int] = Field(default_factory=dict)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    legal_name: str | None = None
    pg_type: str | None = None
    gender: str | None = None

    owner_name: str = Field(min_length=2, max_length=160)
    owner_email: EmailStr
    owner_phone: str | None = None

    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    gstin: str | None = None
    notes: str | None = None

    plan_code: str
    status: str = "TRIAL"
    subscription_start: date | None = None
    subscription_end: date | None = None
    limit_overrides: dict[str, int] | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = None
    legal_name: str | None = None
    owner_name: str | None = None
    owner_phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    gstin: str | None = None
    pg_type: str | None = None
    gender: str | None = None
    notes: str | None = None


class StatusChange(BaseModel):
    status: str = Field(description="ACTIVE | TRIAL | EXPIRED | SUSPENDED | INACTIVE | CANCELLED")
    reason: str | None = None


class ExtendSubscription(BaseModel):
    days: int = Field(ge=1, le=1095)


class ChangePlan(BaseModel):
    plan_code: str


class LimitOverrides(BaseModel):
    overrides: dict[str, int | None]


class CreatedOwnerCredentials(BaseModel):
    """
    Returned exactly once, at creation.

    The password is never stored in readable form and never appears again in any
    response - if the operator loses it they issue a new one.
    """
    name: str
    email: str
    temporary_password: str
    must_change_password: bool = True


class BrevoKeyUpdate(BaseModel):
    """Write-only, like the SMTP password. Empty string clears it."""

    api_key: str = Field(max_length=400)


class DygineSecretsUpdate(BaseModel):
    """
    Write-only, like the SMTP password and the Brevo key.

    Two different secrets that are routinely confused. `key_secret` authenticates
    PGGuru *to* Dygine on outbound calls. `webhook_secret` verifies events
    arriving *from* Dygine. Swapping them means every API call is rejected and
    every webhook fails its signature check.

    An omitted field leaves what is stored untouched; an empty string clears it.
    """

    key_secret: str | None = Field(default=None, max_length=400)
    webhook_secret: str | None = Field(default=None, max_length=400)


class SmtpPasswordUpdate(BaseModel):
    """
    Write-only. There is no matching read anywhere in the API.

    Empty string clears the stored password, for a relay that needs no
    authentication. That is different from not sending the field at all, which
    leaves whatever is stored untouched.
    """

    password: str = Field(max_length=400)


class TestEmailRequest(BaseModel):
    to: str = Field(min_length=3, max_length=255)


class PlatformSettingsUpdate(BaseModel):
    """
    Every field optional: the master settings screen PATCHes only what changed.

    The bounds mirror the CHECK constraints on the table, so a bad value is
    rejected with a readable 422 at the edge rather than a database error from
    somewhere deep in the request.
    """
    default_trial_days: int | None = Field(default=None, ge=0, le=365)
    grace_period_days: int | None = Field(default=None, ge=0, le=90)
    auto_suspend_after_grace: bool | None = None
    expiry_warning_days: int | None = Field(default=None, ge=0, le=90)

    notify_email_enabled: bool | None = None
    notify_sms_enabled: bool | None = None
    notify_whatsapp_enabled: bool | None = None
    notify_push_enabled: bool | None = None

    # --- push (the Firebase key has its own endpoint, deliberately) ---
    push_to_residents: bool | None = None
    push_to_staff: bool | None = None
    #: 0 turns rent reminders off. Bounded at 30 to match the CHECK on the
    #: table, so a bad value is a readable 422 rather than a database error.
    rent_reminder_days: int | None = Field(default=None, ge=0, le=30)

    platform_name: str | None = Field(default=None, min_length=1, max_length=80)
    support_email: EmailStr | None = None

    # --- mail server (the password has its own endpoint, deliberately) ---
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_username: str | None = Field(default=None, max_length=255)
    # Not EmailStr: that rejects reserved TLDs like .local, and an internal
    # relay address is a perfectly ordinary thing for an operator to use. The
    # mail server is the authority on what it will accept, not this schema.
    smtp_from_email: str | None = Field(default=None, max_length=255)
    smtp_from_name: str | None = Field(default=None, max_length=120)
    smtp_use_tls: bool | None = None
    smtp_use_ssl: bool | None = None

    # --- which transport actually sends ---
    email_provider: Literal["smtp", "brevo"] | None = None
    brevo_sender_email: str | None = Field(default=None, max_length=255)
    brevo_sender_name: str | None = Field(default=None, max_length=120)

    #: How long a signed-in phone stays signed in. The default of 3650 days is
    #: "until the app is removed" in practice; an operator who decides that is
    #: too long for staff phones can shorten it without a code change.
    native_session_days: int | None = Field(default=None, ge=1, le=3650)

    # --- Dygine Pay (the two secrets have their own endpoint, deliberately) ---
    #
    # These must be listed here as well as in the service's WRITABLE set. The
    # service set is the second gate; this schema is the first, and pydantic
    # drops any field it does not declare - silently, with a 200 response. A
    # field missing here saves nothing and reports no error, which is a
    # genuinely confusing failure: the form appears to work and then reverts.
    dygine_enabled: bool | None = None
    dygine_base_url: str | None = Field(default=None, max_length=200)
    dygine_key_id: str | None = Field(default=None, max_length=80)
    #: 0 turns the low-balance warning off. Bounded to match the CHECK.
    wallet_low_balance_warning_days: int | None = Field(default=None, ge=0, le=60)
    wallet_topup_presets: list[int] | None = None
