"""
Coupons on platform subscription charges.

The whole of the difficulty is in counting redemptions correctly under
concurrency, and in not burning a coupon on a payment that failed.

**Why reservations exist.** Both simpler designs are wrong:

  - Mark the coupon used when the checkout is created. The payment then fails,
    and the customer is holding a code that no longer works through no fault of
    their own.
  - Mark it used only when payment succeeds. Two owners check out against the
    last remaining redemption, both pay, and you have honoured more discounts
    than you issued.

So a redemption is *reserved* at checkout, *confirmed* on payment, and
*released* on failure or expiry.

**Why the lock.** `count(*)` taken outside a transaction lets two concurrent
requests both read "one left" and both proceed. Every path that changes the
redemption count takes `SELECT ... FOR UPDATE` on the coupon row first and does
its counting inside that lock. This is the same failure mode as an overdrawn
wallet and takes the same cure.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Coupon, CouponAssignment, CouponRedemption, Organization, Subscription,
    SubscriptionPlan,
)

log = logging.getLogger("pgguru.coupons")

#: How long a reservation is held. Matches the Dygine checkout session window,
#: so an abandoned checkout releases its coupon at the same moment the payment
#: link stops working rather than holding it indefinitely.
RESERVATION_MINUTES = 35


class CouponError(Exception):
    """A coupon cannot be used, with a reason fit to show the customer."""


@dataclass
class Quote:
    """What a charge costs once a coupon is applied."""

    gross_paise: int
    discount_paise: int
    net_paise: int
    coupon: Coupon | None = None

    @property
    def has_discount(self) -> bool:
        return self.discount_paise > 0

    def as_dict(self) -> dict:
        return {
            "gross_paise": self.gross_paise,
            "discount_paise": self.discount_paise,
            "net_paise": self.net_paise,
            "coupon_code": self.coupon.code if self.coupon else None,
            "coupon_description": self.coupon.description if self.coupon else None,
        }


def normalise(code: str) -> str:
    """Users type codes by hand, in any case, with copy-paste whitespace."""
    return (code or "").strip().upper()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CouponService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------ lookup --
    def by_code(self, code: str) -> Coupon | None:
        return self.db.scalars(
            select(Coupon).where(Coupon.code == normalise(code))).first()

    def available_for(self, organization_id: uuid.UUID) -> list[Coupon]:
        """
        Coupons targeted at this organisation that it can still use.

        Public codes are deliberately not listed - a customer who has not been
        given a campaign code should not discover it by opening their billing
        page. Targeted coupons appear because they were granted to them.
        """
        today = date.today()
        coupons = self.db.scalars(
            select(Coupon)
            .join(CouponAssignment, CouponAssignment.coupon_id == Coupon.id)
            .where(CouponAssignment.organization_id == organization_id,
                   Coupon.status == "active",
                   or_(Coupon.valid_from.is_(None), Coupon.valid_from <= today),
                   or_(Coupon.valid_until.is_(None), Coupon.valid_until >= today))
        ).all()
        return [c for c in coupons
                if self._org_uses(c.id, organization_id) < c.max_per_org]

    # ------------------------------------------------------------ counts --
    def _live_uses(self, coupon_id: uuid.UUID) -> int:
        """
        Confirmed redemptions plus reservations that have not expired.

        An expired reservation is not counted: the checkout was abandoned and
        the redemption is effectively free again, whether or not the sweep has
        got round to releasing the row yet.
        """
        return int(self.db.scalar(
            select(func.count(CouponRedemption.id)).where(
                CouponRedemption.coupon_id == coupon_id,
                or_(CouponRedemption.state == "confirmed",
                    (CouponRedemption.state == "reserved")
                    & (CouponRedemption.reserved_until > _now())))) or 0)

    def _org_uses(self, coupon_id: uuid.UUID, organization_id: uuid.UUID) -> int:
        return int(self.db.scalar(
            select(func.count(CouponRedemption.id)).where(
                CouponRedemption.coupon_id == coupon_id,
                CouponRedemption.organization_id == organization_id,
                or_(CouponRedemption.state == "confirmed",
                    (CouponRedemption.state == "reserved")
                    & (CouponRedemption.reserved_until > _now())))) or 0)

    def _cycles_used(self, coupon_id: uuid.UUID,
                     organization_id: uuid.UUID) -> int:
        return int(self.db.scalar(
            select(func.count(CouponRedemption.id)).where(
                CouponRedemption.coupon_id == coupon_id,
                CouponRedemption.organization_id == organization_id,
                CouponRedemption.state == "confirmed")) or 0)

    # ---------------------------------------------------------- discount --
    def discount_for(self, coupon: Coupon, gross_paise: int) -> int:
        """
        What this coupon takes off, in paise.

        Capped three ways: by `max_discount_paise`, and by the charge itself -
        a discount larger than the charge would make the invoice negative, which
        is a credit note, not a subscription payment.
        """
        if coupon.kind == "percent":
            amount = gross_paise * coupon.value // 100
            if coupon.max_discount_paise is not None:
                amount = min(amount, coupon.max_discount_paise)
        else:
            amount = coupon.value
        return max(0, min(amount, gross_paise))

    # ---------------------------------------------------------- validate --
    def validate(self, code: str, organization_id: uuid.UUID,
                 gross_paise: int, plan: SubscriptionPlan | None = None) -> Quote:
        """
        Check a coupon and price the charge. Reserves nothing.

        Used by the "apply coupon" button so the owner sees the new total before
        committing to anything.
        """
        coupon = self.by_code(code)
        if coupon is None:
            raise CouponError("That coupon code is not valid.")

        self._assert_usable(coupon, organization_id, gross_paise, plan)

        discount = self.discount_for(coupon, gross_paise)
        return Quote(gross_paise=gross_paise, discount_paise=discount,
                     net_paise=gross_paise - discount, coupon=coupon)

    def _assert_usable(self, coupon: Coupon, organization_id: uuid.UUID,
                       gross_paise: int,
                       plan: SubscriptionPlan | None) -> None:
        """Every reason a coupon might not apply, with a message worth reading."""
        today = date.today()

        if coupon.status == "paused":
            raise CouponError("That coupon is not currently active.")
        if coupon.status == "expired":
            raise CouponError("That coupon has expired.")
        if coupon.valid_from and today < coupon.valid_from:
            raise CouponError(
                f"That coupon is not valid until "
                f"{coupon.valid_from.strftime('%d %b %Y')}.")
        if coupon.valid_until and today > coupon.valid_until:
            raise CouponError("That coupon has expired.")

        if gross_paise < coupon.min_amount_paise:
            raise CouponError(
                f"This coupon applies to charges of "
                f"\u20b9{coupon.min_amount_paise / 100:,.0f} or more.")

        if coupon.applies_to_plans:
            if plan is None or plan.code not in coupon.applies_to_plans:
                raise CouponError("That coupon does not apply to this plan.")

        # A targeted coupon is only for the organisations it was granted to.
        if coupon.assignments:
            allowed = {a.organization_id for a in coupon.assignments}
            if organization_id not in allowed:
                # Deliberately the same message as an unknown code. Telling a
                # stranger "that code exists but is not for you" is an
                # invitation to go looking for one that is.
                raise CouponError("That coupon code is not valid.")

        if (coupon.max_redemptions is not None
                and self._live_uses(coupon.id) >= coupon.max_redemptions):
            raise CouponError("That coupon has been fully redeemed.")

        if self._org_uses(coupon.id, organization_id) >= coupon.max_per_org:
            raise CouponError("You have already used that coupon.")

        if (coupon.applies_to_cycles is not None
                and self._cycles_used(coupon.id, organization_id)
                >= coupon.applies_to_cycles):
            raise CouponError(
                "That coupon has been used for all the billing cycles it covers.")

    # ----------------------------------------------------------- reserve --
    def reserve(self, code: str, organization_id: uuid.UUID, gross_paise: int,
                *, plan: SubscriptionPlan | None = None,
                period: date | None = None) -> tuple[Quote, CouponRedemption]:
        """
        Validate and hold a redemption, under a lock on the coupon row.

        The lock is the point. Without it two concurrent renewals both read
        "one redemption left" and both reserve it.
        """
        coupon = self.by_code(code)
        if coupon is None:
            raise CouponError("That coupon code is not valid.")

        # Lock first, then count. The other order proves nothing.
        locked = self.db.execute(
            select(Coupon).where(Coupon.id == coupon.id).with_for_update()
        ).scalar_one()

        # Reuse before validating, not after.
        #
        # This order matters and the other way round is a bug: a retried
        # renewal for a month that already has a reservation would be measured
        # against the per-org cap, find its *own* earlier reservation counted
        # against it, and be refused with "you have already used that coupon" -
        # on the customer's second click of the same button.
        if period is not None:
            existing = self.db.scalars(select(CouponRedemption).where(
                CouponRedemption.coupon_id == locked.id,
                CouponRedemption.organization_id == organization_id,
                CouponRedemption.period == period,
                CouponRedemption.state.in_(["reserved", "confirmed"]))).first()
            if existing is not None:
                return (Quote(gross_paise=existing.gross_paise,
                              discount_paise=existing.discount_paise,
                              net_paise=existing.net_paise, coupon=locked),
                        existing)

        self._assert_usable(locked, organization_id, gross_paise, plan)

        discount = self.discount_for(locked, gross_paise)
        redemption = CouponRedemption(
            coupon_id=locked.id, organization_id=organization_id, period=period,
            gross_paise=gross_paise, discount_paise=discount,
            net_paise=gross_paise - discount, state="reserved",
            reserved_until=_now() + timedelta(minutes=RESERVATION_MINUTES))
        self.db.add(redemption)
        self.db.flush()

        log.info("coupon %s reserved for org %s (-%s paise)",
                 locked.code, organization_id, discount)
        return (Quote(gross_paise=gross_paise, discount_paise=discount,
                      net_paise=gross_paise - discount, coupon=locked),
                redemption)

    def confirm(self, redemption: CouponRedemption,
                charge_id: uuid.UUID | None = None) -> None:
        """Payment succeeded. Idempotent - a redelivered webhook is harmless."""
        if redemption.state == "confirmed":
            return
        redemption.state = "confirmed"
        redemption.confirmed_at = _now()
        redemption.reserved_until = None
        if charge_id:
            redemption.charge_id = charge_id
        self.db.flush()

    def release(self, redemption: CouponRedemption, reason: str = "") -> None:
        """
        Payment failed or was abandoned. Give the redemption back.

        Never releases a confirmed one: that would hand back a discount the
        customer has already been given.
        """
        if redemption.state != "reserved":
            return
        redemption.state = "released"
        redemption.released_reason = reason[:200]
        redemption.reserved_until = None
        self.db.flush()

    def sweep_expired(self) -> int:
        """
        Release reservations whose checkout window has passed.

        Run from the daily job. Not strictly required for correctness - the
        counting already ignores expired reservations - but it keeps the table
        honest, so an operator reading it sees what is actually held.
        """
        stale = self.db.scalars(select(CouponRedemption).where(
            CouponRedemption.state == "reserved",
            CouponRedemption.reserved_until < _now())).all()
        for redemption in stale:
            self.release(redemption, "checkout expired")
        if stale:
            log.info("released %s expired coupon reservations", len(stale))
        return len(stale)

    # ------------------------------------------------------------- admin --
    def usage(self, coupon: Coupon) -> dict:
        confirmed = int(self.db.scalar(
            select(func.count(CouponRedemption.id)).where(
                CouponRedemption.coupon_id == coupon.id,
                CouponRedemption.state == "confirmed")) or 0)
        reserved = int(self.db.scalar(
            select(func.count(CouponRedemption.id)).where(
                CouponRedemption.coupon_id == coupon.id,
                CouponRedemption.state == "reserved",
                CouponRedemption.reserved_until > _now())) or 0)
        given = int(self.db.scalar(
            select(func.coalesce(func.sum(CouponRedemption.discount_paise), 0))
            .where(CouponRedemption.coupon_id == coupon.id,
                   CouponRedemption.state == "confirmed")) or 0)
        return {"confirmed": confirmed, "reserved": reserved,
                "remaining": (None if coupon.max_redemptions is None
                              else max(0, coupon.max_redemptions
                                       - confirmed - reserved)),
                "total_discount_paise": given}
