"""Master-admin contracts: organisations, plans, subscriptions, usage."""
import uuid
from datetime import date, datetime

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

    platform_name: str | None = Field(default=None, min_length=1, max_length=80)
    support_email: EmailStr | None = None
