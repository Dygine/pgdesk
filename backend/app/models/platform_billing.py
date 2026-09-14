"""
What a PG owner pays PGGuru, and how they get a discount on it.

Two things live here that do not live anywhere else in the app, and the reason
is the same for both: **this is the only money that flows to the platform.**

Everything in `billing.py` is a resident paying their PG owner, settled through
that owner's own Razorpay keys. The platform never sees it. Everything here is
an owner paying the platform, settled through Dygine Pay. Residents, staff,
seekers and gate guards never appear in this file - they do not pay for
anything, ever.

Where the balance actually lives
--------------------------------
Not here. Dygine Pay holds the authoritative wallet balance;
`OrgBillingProfile.cached_wallet_paise` is a display copy with a timestamp
beside it so the UI can say how stale it is. Nothing in this application is
allowed to authorise a spend from that cached number - every debit goes to
Dygine, which takes a row lock and decides. Two writable copies of a balance is
how balances silently diverge.

Money is stored in **paise**, as integers, throughout this module. The rest of
the app uses `Numeric(12,2)` rupees, which is correct for rent where a human
types the figure. It is wrong at a gateway boundary, where every amount crosses
as an integer and a float round-trip eventually loses a paisa.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    Integer, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import Timestamps, UUIDPrimaryKey


class OrgBillingProfile(Base, UUIDPrimaryKey, Timestamps):
    """
    One row per organisation: how it pays the platform.

    Created lazily the first time an owner opens the billing screen, so existing
    organisations need no backfill.
    """

    __tablename__ = "org_billing_profiles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True)

    #: What Dygine calls this organisation. Always the org uuid as a string -
    #: the mapping has to survive a rename, so it cannot be the org name.
    dygine_external_id: Mapped[str | None] = mapped_column(String(80))

    #: Display copy of the Dygine balance. NEVER used to authorise a spend.
    cached_wallet_paise: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0)
    cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Take the renewal from the wallet automatically when it falls due.
    #: On by default: a wallet that has to be spent by hand is a prepaid account
    #: with extra steps, and a renewal that silently lapses because an owner was
    #: busy is a support ticket for the platform and an outage for the PG.
    auto_debit_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)

    #: Stops the low-balance warning repeating every day of the warning window.
    low_balance_notified_on: Mapped[date | None] = mapped_column(Date)

    organization: Mapped["Organization"] = relationship()

    __table_args__ = (
        CheckConstraint("cached_wallet_paise >= 0",
                        name="ck_org_billing_cache_non_negative"),
    )


class Coupon(Base, UUIDPrimaryKey, Timestamps):
    """
    A discount the platform operator grants on a subscription charge.

    Deliberately **not** stored in Dygine Pay. A coupon is a commercial decision
    about this product - which plan, which owner, which campaign. Dygine is a
    payments rail shared by every tool; teaching it PGGuru's marketing rules
    means teaching it every future tool's rules too. PGGuru computes the
    discount and asks Dygine to collect the net, sending the discount as its own
    invoice line so the customer sees what came off.
    """

    __tablename__ = "platform_coupons"

    #: Stored uppercase and stripped. Users type coupon codes by hand, in any
    #: case, with stray spaces from a copy-paste.
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True,
                                      index=True)
    description: Mapped[str | None] = mapped_column(String(300))

    #: "percent" | "fixed"
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="percent")
    #: Percent as a whole number (20 = 20%), or paise for a fixed discount.
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Ceiling on a percent coupon. 20% off with no cap is an open cheque
    #: against your most expensive plan; NULL means uncapped and is a choice.
    max_discount_paise: Mapped[int | None] = mapped_column(BigInteger)
    #: Floor before the coupon applies at all.
    min_amount_paise: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0)

    #: Plan codes this applies to. Empty list = every plan.
    applies_to_plans: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    #: How many billing cycles it survives. 1 = first payment only.
    #: NULL = every renewal forever, which is a permanent price cut rather than
    #: a promotion - allowed, but it should be a deliberate choice.
    applies_to_cycles: Mapped[int | None] = mapped_column(Integer, default=1)

    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)

    #: Total redemptions across every organisation. NULL = unlimited.
    max_redemptions: Mapped[int | None] = mapped_column(Integer)
    #: Per organisation. Usually 1.
    max_per_org: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    #: "active" | "paused" | "expired"
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active",
                                        index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    assignments: Mapped[list["CouponAssignment"]] = relationship(
        back_populates="coupon", cascade="all, delete-orphan", lazy="selectin")
    redemptions: Mapped[list["CouponRedemption"]] = relationship(
        back_populates="coupon", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("value > 0", name="ck_coupon_value_positive"),
        CheckConstraint("kind IN ('percent','fixed')", name="ck_coupon_kind"),
        CheckConstraint("status IN ('active','paused','expired')",
                        name="ck_coupon_status"),
        CheckConstraint("max_per_org > 0", name="ck_coupon_per_org_positive"),
        # A percent coupon over 100 would pay the customer to subscribe.
        CheckConstraint("kind <> 'percent' OR value <= 100",
                        name="ck_coupon_percent_range"),
        CheckConstraint("valid_until IS NULL OR valid_from IS NULL "
                        "OR valid_until >= valid_from",
                        name="ck_coupon_date_order"),
    )

    @property
    def is_targeted(self) -> bool:
        """True when only specific organisations may redeem this."""
        return bool(self.assignments)


class CouponAssignment(Base, UUIDPrimaryKey, Timestamps):
    """
    Targets a coupon at one organisation.

    A coupon with no assignments is a public code: anyone who types it gets it,
    bounded by max_redemptions. A coupon with assignments can only be redeemed
    by those organisations, and appears in their billing screen automatically
    rather than needing to be typed at all - which is what you want when you are
    granting a specific owner a discount rather than running a campaign.
    """

    __tablename__ = "platform_coupon_assignments"

    coupon_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("platform_coupons.id", ondelete="CASCADE"),
        nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    coupon: Mapped[Coupon] = relationship(back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("coupon_id", "organization_id",
                         name="uq_coupon_assignment"),
    )


class CouponRedemption(Base, UUIDPrimaryKey, Timestamps):
    """
    One use of a coupon, through a three-state lifecycle.

        reserved  -> confirmed   payment succeeded
        reserved  -> released    payment failed, or the reservation expired

    The reservation exists because both simpler designs are wrong. Marking a
    coupon used when the checkout is created burns it when the payment fails,
    and the customer is left holding a dead code. Marking it used only on
    success lets two people check out against the last remaining redemption and
    both succeed, so you honour more discounts than you issued.

    Counting is done inside a row lock on the coupon, over confirmed plus
    unexpired-reserved rows. A count taken outside the lock lets two requests
    both read "one left".
    """

    __tablename__ = "platform_coupon_redemptions"

    coupon_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("platform_coupons.id", ondelete="CASCADE"),
        nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True)

    #: The billing period this discount was applied to, as the first of the
    #: month. Stops a retried renewal redeeming twice for the same month.
    period: Mapped[date | None] = mapped_column(Date)

    gross_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    net_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

    state: Mapped[str] = mapped_column(String(12), nullable=False,
                                       default="reserved", index=True)
    #: Matches the Dygine checkout session expiry. Past this, the sweep releases
    #: it - otherwise an abandoned checkout holds a redemption forever.
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_reason: Mapped[str | None] = mapped_column(String(200))

    #: Links back to the charge this discount was part of.
    charge_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("platform_charges.id", ondelete="SET NULL"))

    coupon: Mapped[Coupon] = relationship(back_populates="redemptions")

    __table_args__ = (
        CheckConstraint("state IN ('reserved','confirmed','released')",
                        name="ck_redemption_state"),
        CheckConstraint("discount_paise >= 0 AND net_paise >= 0",
                        name="ck_redemption_non_negative"),
        Index("ix_redemption_coupon_state", "coupon_id", "state"),
        Index("ix_redemption_org", "organization_id", "state"),
    )


class PlatformCharge(Base, UUIDPrimaryKey, Timestamps):
    """
    One attempt by an organisation to pay the platform.

    Records the local side of a Dygine payment: what was owed, what was
    discounted, how it was paid, and what Dygine called it. Kept even when the
    payment fails, because "they tried and it did not work" is the single most
    useful thing to know when an owner says their subscription did not renew.
    """

    __tablename__ = "platform_charges"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subscription_plans.id", ondelete="SET NULL"))

    #: "subscription" | "wallet_topup"
    purpose: Mapped[str] = mapped_column(String(20), nullable=False,
                                         default="subscription")
    #: "gateway" (Dygine hosted checkout) | "wallet" (balance debit)
    method: Mapped[str] = mapped_column(String(10), nullable=False, default="gateway")

    period: Mapped[date | None] = mapped_column(Date, index=True)
    gross_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    net_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: created -> paid | failed | cancelled
    status: Mapped[str] = mapped_column(String(12), nullable=False,
                                        default="created", index=True)

    #: What Dygine gave us back.
    dygine_session_id: Mapped[str | None] = mapped_column(String(80))
    dygine_payment_ref: Mapped[str | None] = mapped_column(String(80), index=True)
    dygine_invoice_number: Mapped[str | None] = mapped_column(String(40))
    dygine_invoice_id: Mapped[str | None] = mapped_column(String(80))
    checkout_url: Mapped[str | None] = mapped_column(Text)

    #: The idempotency key sent to Dygine. Stable per (org, period, purpose), so
    #: a double-clicked renewal cannot create two orders. Unique here as well,
    #: so the same is true locally.
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False,
                                                 unique=True)

    failure_reason: Mapped[str | None] = mapped_column(String(400))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when this charge extended the subscription, so a redelivered webhook
    #: cannot extend it a second time.
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when the invoice email went out. The guard that stops a customer
    #: receiving the same invoice every time the job runs.
    invoice_emailed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True))
    invoice_email_error: Mapped[str | None] = mapped_column(String(400))

    __table_args__ = (
        CheckConstraint("net_paise >= 0 AND gross_paise >= 0 AND discount_paise >= 0",
                        name="ck_charge_non_negative"),
        CheckConstraint("status IN ('created','paid','failed','cancelled')",
                        name="ck_charge_status"),
        Index("ix_charge_org_created", "organization_id", "created_at"),
    )


class DygineEvent(Base, UUIDPrimaryKey, Timestamps):
    """
    Every webhook Dygine Pay sends us, stored raw before anything acts on it.

    Not optional. An event that is not stored before it is applied cannot be
    replayed when the handler turns out to have a bug, and one that is not
    deduplicated will extend a subscription twice the first time Dygine retries
    a delivery it already made.

    `event_id` is Dygine's own id and is unique here, which is what makes
    processing idempotent: a redelivery hits the constraint and is acknowledged
    without being applied again.
    """

    __tablename__ = "dygine_events"

    event_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    signature: Mapped[str | None] = mapped_column(String(128))
    raw_body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    process_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_dygine_events_type_created", "event_type", "created_at"),
    )


# ---------------------------------------------------------------- support --
class PlatformTicket(Base, UUIDPrimaryKey, Timestamps):
    """
    A PG owner asking the platform for help.

    Deliberately not `SupportQuery`, which is a resident asking their PG owner.
    Those two look similar and are opposite directions: one is tenant data the
    PG owns, this one crosses the tenant boundary and is read by the platform
    operator. Sharing a table would mean every master-admin query needed an
    "and not really a tenant record" filter, and one missed filter would leak a
    PG's private support thread into another PG's inbox.
    """

    __tablename__ = "platform_tickets"

    reference: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True)
    raised_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    #: "payment" | "bug" | "feature" | "question" | "other"
    category: Mapped[str] = mapped_column(String(20), nullable=False,
                                          default="question", index=True)
    #: "low" | "normal" | "high" | "urgent"
    priority: Mapped[str] = mapped_column(String(10), nullable=False,
                                          default="normal", index=True)
    #: "open" | "in_progress" | "waiting" | "resolved" | "closed"
    status: Mapped[str] = mapped_column(String(15), nullable=False,
                                        default="open", index=True)

    #: Set when the owner raises it from a billing screen, so support can see
    #: the charge without asking them to describe it.
    charge_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("platform_charges.id", ondelete="SET NULL"))

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    #: Whose turn it is. Drives the unread badge on both sides without needing
    #: per-user read receipts.
    last_reply_by: Mapped[str] = mapped_column(String(10), nullable=False,
                                               default="owner")
    last_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["PlatformTicketMessage"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan",
        order_by="PlatformTicketMessage.created_at", lazy="selectin")

    __table_args__ = (
        CheckConstraint("status IN ('open','in_progress','waiting','resolved','closed')",
                        name="ck_ticket_status"),
        CheckConstraint("priority IN ('low','normal','high','urgent')",
                        name="ck_ticket_priority"),
        CheckConstraint("last_reply_by IN ('owner','platform')",
                        name="ck_ticket_last_reply_by"),
        Index("ix_ticket_org_status", "organization_id", "status"),
        Index("ix_ticket_status_created", "status", "created_at"),
    )


class PlatformTicketMessage(Base, UUIDPrimaryKey, Timestamps):
    """One message in a ticket thread, from either side."""

    __tablename__ = "platform_ticket_messages"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("platform_tickets.id", ondelete="CASCADE"),
        nullable=False, index=True)
    #: "owner" | "platform"
    author_side: Mapped[str] = mapped_column(String(10), nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    author_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: A note the operator writes to themselves. Never shown to the owner.
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    ticket: Mapped[PlatformTicket] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint("author_side IN ('owner','platform')",
                        name="ck_ticket_message_side"),
    )
