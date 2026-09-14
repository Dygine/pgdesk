"""
How a PG owner pays the platform.

This is the only module in PGGuru that moves money *to* PGGuru. Everything in
`billing_service.py` is a resident paying their landlord and settles through
that landlord's own Razorpay keys; nothing here touches it.

Three things it is careful about.

**Units.** `SubscriptionPlan.price` is an `Integer` number of **rupees**. Dygine
speaks **paise**, everywhere. Every crossing is through `rupees_to_paise`, never
a bare multiplication scattered through the code, because the day someone
forgets is the day an owner is charged 1,49,900 for a 1,499 plan.

**Never extend on a promise.** A subscription is extended only after Dygine says
the money is captured - and then exactly once, guarded by `PlatformCharge.applied_at`,
because a webhook will eventually be delivered twice.

**A timeout is not a failure.** If a wallet debit times out, the debit may well
have happened. Extending the subscription would be wrong and refusing it would
be wrong; the only safe move is to leave the charge open and let the reconcile
pass settle it against Dygine's own record.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Coupon, CouponRedemption, DygineEvent, Organization, OrgBillingProfile,
    PlatformCharge, PlatformSettings, Subscription, SubscriptionPlan,
)
from app.models.enums import (
    AuditAction, NotificationType, OrganizationStatus, SubscriptionStatus,
)
from app.models.platform import SINGLETON_ID
from app.services.audit import AuditService
from app.services.coupon_service import CouponError, CouponService, Quote
from app.services.dygine_client import DygineClient, DygineError, DygineNotConfigured
from app.services.notification_service import NotificationService

log = logging.getLogger("pgguru.platform_billing")


def rupees_to_paise(rupees: int | float) -> int:
    """
    The single conversion point between PGGuru's rupees and Dygine's paise.

    Deliberately one function rather than `* 100` at each call site. A stray
    multiplication that gets missed does not fail loudly - it silently charges
    a hundred times too much.
    """
    return int(round(float(rupees) * 100))


def paise_to_rupees(paise: int) -> float:
    return round(int(paise) / 100, 2)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def period_of(when: date | None = None) -> date:
    """The billing period a date falls in, as the first of that month."""
    when = when or date.today()
    return when.replace(day=1)


@dataclass
class ChargePlan:
    """What an organisation is about to be asked to pay."""

    organization: Organization
    plan: SubscriptionPlan
    quote: Quote
    period: date
    wallet_paise: int
    wallet_covers: bool

    def as_dict(self) -> dict:
        return {
            "plan": {"code": self.plan.code, "name": self.plan.name,
                     "price_rupees": self.plan.price,
                     "billing_cycle": self.plan.billing_cycle},
            "period": self.period.isoformat(),
            **self.quote.as_dict(),
            "wallet_paise": self.wallet_paise,
            "wallet_covers": self.wallet_covers,
        }


class PlatformBillingService:
    def __init__(self, db: Session):
        self.db = db
        self.dygine = DygineClient(db)
        self.coupons = CouponService(db)
        self.audit = AuditService(db)
        self.notify = NotificationService(db)

    # ------------------------------------------------------------ profile --
    def profile(self, organization_id: uuid.UUID) -> OrgBillingProfile:
        """
        Get or create the billing profile.

        Created lazily so existing organisations need no backfill migration -
        the row appears the first time an owner opens their billing screen.
        """
        row = self.db.scalars(select(OrgBillingProfile).where(
            OrgBillingProfile.organization_id == organization_id)).first()
        if row is None:
            row = OrgBillingProfile(
                organization_id=organization_id,
                dygine_external_id=str(organization_id))
            self.db.add(row)
            self.db.flush()
        elif not row.dygine_external_id:
            row.dygine_external_id = str(organization_id)
            self.db.flush()
        return row

    def _customer_payload(self, org: Organization) -> dict:
        """
        How this organisation appears to Dygine.

        `state_code` decides CGST/SGST versus IGST on the invoice, so it is sent
        whenever known. `external_id` is the org uuid and never the name, which
        has to survive a rename.
        """
        return {
            "external_id": str(org.id),
            "name": org.legal_name or org.name,
            "email": org.owner_email,
            "phone": org.owner_phone,
            "gstin": org.gstin or None,
            "state_code": _state_code(org.state),
            "billing_address": ", ".join(
                p for p in [org.address, org.city, org.state, org.pincode] if p),
        }

    # ------------------------------------------------------------- wallet --
    def wallet_balance(self, organization_id: uuid.UUID, *,
                       refresh: bool = True) -> tuple[int, datetime | None, bool]:
        """
        Returns (paise, as_of, live).

        `live` is False when the figure came from the cache because Dygine could
        not be reached. The caller must show that plainly rather than presenting
        a stale number as current - someone who believes they have a balance
        they do not is about to have a renewal fail.
        """
        prof = self.profile(organization_id)
        if not refresh or not self.dygine.enabled:
            return prof.cached_wallet_paise, prof.cached_at, False
        try:
            balance = self.dygine.wallet_balance(prof.dygine_external_id)
        except DygineError as exc:
            log.warning("wallet balance unavailable for %s: %s",
                        organization_id, exc)
            return prof.cached_wallet_paise, prof.cached_at, False

        prof.cached_wallet_paise = balance
        prof.cached_at = _now()
        self.db.flush()
        return balance, prof.cached_at, True

    def cache_balance(self, organization_id: uuid.UUID, paise: int) -> None:
        """Update the display copy from a webhook, without calling out."""
        prof = self.profile(organization_id)
        prof.cached_wallet_paise = max(0, int(paise))
        prof.cached_at = _now()
        self.db.flush()

    # -------------------------------------------------------------- quote --
    def current_plan(self, organization_id: uuid.UUID) -> tuple[Subscription | None,
                                                                SubscriptionPlan | None]:
        sub = self.db.scalars(select(Subscription).where(
            Subscription.organization_id == organization_id,
            Subscription.is_current.is_(True))).first()
        if sub is None:
            return None, None
        return sub, self.db.get(SubscriptionPlan, sub.plan_id)

    def quote(self, organization_id: uuid.UUID, *, coupon_code: str | None = None,
              plan: SubscriptionPlan | None = None,
              period: date | None = None) -> ChargePlan:
        """
        Price the next subscription charge, optionally with a coupon.

        Reserves nothing - this is what the billing screen renders while the
        owner decides.
        """
        org = self.db.get(Organization, organization_id)
        if org is None:
            raise ValueError("Organisation not found")

        if plan is None:
            _, plan = self.current_plan(organization_id)
        if plan is None:
            raise ValueError("This organisation has no subscription plan")

        gross = rupees_to_paise(plan.price)
        period = period or period_of()

        quote = Quote(gross_paise=gross, discount_paise=0, net_paise=gross)
        if coupon_code:
            quote = self.coupons.validate(coupon_code, organization_id, gross, plan)

        balance, _, _ = self.wallet_balance(organization_id)
        return ChargePlan(organization=org, plan=plan, quote=quote, period=period,
                          wallet_paise=balance,
                          wallet_covers=balance >= quote.net_paise)

    # ----------------------------------------------------- charge records --
    def _charge(self, *, organization_id: uuid.UUID, purpose: str, method: str,
                gross: int, discount: int, net: int, period: date | None,
                plan_id: uuid.UUID | None, idempotency_key: str) -> PlatformCharge:
        """
        Find or create the charge for this attempt.

        Keyed on the idempotency key, so a retried request continues the
        existing charge instead of opening a second one.
        """
        existing = self.db.scalars(select(PlatformCharge).where(
            PlatformCharge.idempotency_key == idempotency_key)).first()
        if existing is not None:
            return existing

        charge = PlatformCharge(
            organization_id=organization_id, plan_id=plan_id, purpose=purpose,
            method=method, period=period, gross_paise=gross,
            discount_paise=discount, net_paise=net, status="created",
            idempotency_key=idempotency_key)
        self.db.add(charge)
        self.db.flush()
        return charge

    # ------------------------------------------------------- pay by card --
    def start_subscription_checkout(
            self, organization_id: uuid.UUID, *, coupon_code: str | None = None,
            success_url: str | None = None,
            cancel_url: str | None = None) -> PlatformCharge:
        """
        Hosted checkout for a subscription renewal.

        The coupon is reserved before Dygine is called and released if Dygine
        refuses, so a failure here does not consume the customer's discount.
        """
        plan_info = self.quote(organization_id, coupon_code=coupon_code)
        org, plan, period = plan_info.organization, plan_info.plan, plan_info.period
        gross = plan_info.quote.gross_paise

        redemption: CouponRedemption | None = None
        quote = plan_info.quote
        if coupon_code:
            quote, redemption = self.coupons.reserve(
                coupon_code, organization_id, gross, plan=plan, period=period)

        key = f"sub:{organization_id}:{period.isoformat()}"
        charge = self._charge(
            organization_id=organization_id, purpose="subscription",
            method="gateway", gross=gross, discount=quote.discount_paise,
            net=quote.net_paise, period=period, plan_id=plan.id,
            idempotency_key=key)

        if charge.status == "paid":
            return charge                      # already settled; nothing to do
        if charge.checkout_url and charge.status == "created":
            return charge                      # resume the existing link

        line_items = [{
            "description": f"{_platform_name(self.db)} {plan.name} — "
                           f"{period.strftime('%b %Y')}",
            "amount": gross, "quantity": 1,
        }]
        if quote.has_discount:
            # Sent as its own line, not netted off the price, so the invoice
            # shows the customer what they were charged and what came off it -
            # and so GST is computed on what they actually paid.
            line_items.append({
                "description": f"Discount {quote.coupon.code}"
                               + (f" ({quote.coupon.value}%)"
                                  if quote.coupon.kind == "percent" else ""),
                "amount": -quote.discount_paise, "quantity": 1,
                "kind": "discount",
            })

        try:
            session = self.dygine.create_checkout(
                customer=self._customer_payload(org), line_items=line_items,
                purpose="subscription", idempotency_key=key,
                success_url=success_url, cancel_url=cancel_url,
                notes={"organization_id": str(org.id),
                       "period": period.isoformat(),
                       "plan_code": plan.code})
        except DygineError as exc:
            if redemption is not None:
                self.coupons.release(redemption, f"checkout failed: {exc}")
            charge.status = "failed"
            charge.failure_reason = str(exc)[:400]
            self.db.flush()
            raise

        charge.dygine_session_id = session.get("id")
        charge.checkout_url = session.get("checkout_url")
        if redemption is not None:
            redemption.charge_id = charge.id
        self.db.flush()
        return charge

    def start_topup_checkout(self, organization_id: uuid.UUID, amount_paise: int,
                             *, success_url: str | None = None,
                             cancel_url: str | None = None) -> PlatformCharge:
        """Hosted checkout for a wallet top-up."""
        if amount_paise < 10000:
            raise ValueError("The smallest top-up is \u20b9100.")

        org = self.db.get(Organization, organization_id)
        if org is None:
            raise ValueError("Organisation not found")

        # Unique per attempt: unlike a renewal, an owner may legitimately top up
        # the same amount twice in one day and expect both to go through.
        key = f"topup:{organization_id}:{uuid.uuid4().hex[:12]}"
        charge = self._charge(
            organization_id=organization_id, purpose="wallet_topup",
            method="gateway", gross=amount_paise, discount=0, net=amount_paise,
            period=None, plan_id=None, idempotency_key=key)

        session = self.dygine.create_checkout(
            customer=self._customer_payload(org),
            line_items=[{"description": "Wallet top-up", "amount": amount_paise,
                         "quantity": 1}],
            purpose="wallet_topup", idempotency_key=key,
            success_url=success_url, cancel_url=cancel_url,
            notes={"organization_id": str(org.id)})

        charge.dygine_session_id = session.get("id")
        charge.checkout_url = session.get("checkout_url")
        self.db.flush()
        return charge

    # ----------------------------------------------------- pay by wallet --
    def pay_from_wallet(self, organization_id: uuid.UUID, *,
                        coupon_code: str | None = None,
                        actor: str = "owner") -> PlatformCharge:
        """
        Settle a renewal from the wallet. Synchronous - no redirect, no webhook.

        A timeout here is the dangerous case: the debit may have succeeded. The
        charge is left open rather than marked failed, and `reconcile_open` will
        settle it against Dygine's record. Marking it failed would let a second
        attempt debit the wallet twice.
        """
        plan_info = self.quote(organization_id, coupon_code=coupon_code)
        plan, period = plan_info.plan, plan_info.period
        gross = plan_info.quote.gross_paise

        redemption: CouponRedemption | None = None
        quote = plan_info.quote
        if coupon_code:
            quote, redemption = self.coupons.reserve(
                coupon_code, organization_id, gross, plan=plan, period=period)

        key = f"sub:{organization_id}:{period.isoformat()}"
        charge = self._charge(
            organization_id=organization_id, purpose="subscription",
            method="wallet", gross=gross, discount=quote.discount_paise,
            net=quote.net_paise, period=period, plan_id=plan.id,
            idempotency_key=key)

        if charge.status == "paid":
            return charge

        prof = self.profile(organization_id)
        try:
            result = self.dygine.wallet_debit(
                prof.dygine_external_id, quote.net_paise,
                description=f"{plan.name} — {period.strftime('%b %Y')}",
                idempotency_key=key, reference_type="subscription",
                reference_id=str(charge.id))
        except DygineError as exc:
            if exc.is_unreachable:
                # Unknown outcome. Leave the charge open for reconciliation.
                charge.failure_reason = "Payments service unreachable; awaiting confirmation"
                self.db.flush()
                raise
            if redemption is not None:
                self.coupons.release(redemption, f"wallet debit failed: {exc}")
            charge.status = "failed"
            charge.failure_reason = str(exc)[:400]
            self.db.flush()
            raise

        charge.status = "paid"
        charge.paid_at = _now()
        charge.dygine_payment_ref = f"wallet:{result.get('id')}"
        self.db.flush()

        self.cache_balance(organization_id, int(result.get("balance") or 0))
        if redemption is not None:
            self.coupons.confirm(redemption, charge.id)
        self._apply(charge, actor=actor)
        return charge

    # ------------------------------------------------------------- apply --
    def _apply(self, charge: PlatformCharge, *, actor: str = "system") -> bool:
        """
        Extend the subscription for a paid charge. Runs at most once.

        `applied_at` is the guard. A webhook will be delivered twice sooner or
        later, and without this the organisation silently gets two months for
        one payment.
        """
        if charge.applied_at is not None:
            return False
        if charge.status != "paid":
            return False
        if charge.purpose != "subscription":
            charge.applied_at = _now()
            self.db.flush()
            return False

        sub = self.db.scalars(select(Subscription).where(
            Subscription.organization_id == charge.organization_id,
            Subscription.is_current.is_(True))).first()
        if sub is None:
            log.error("charge %s paid but organisation %s has no subscription",
                      charge.id, charge.organization_id)
            return False

        plan = self.db.get(SubscriptionPlan, sub.plan_id)
        days = _cycle_days(plan.billing_cycle if plan else "MONTHLY")

        today = date.today()
        # Extend from the existing end date when it is still in the future, so
        # paying early does not cost the customer the days they already have.
        start = sub.end_date if sub.end_date > today else today
        sub.start_date = min(sub.start_date, today)
        sub.end_date = start + timedelta(days=days)
        sub.status = SubscriptionStatus.ACTIVE

        org = self.db.get(Organization, charge.organization_id)
        if org is not None and org.status in (OrganizationStatus.TRIAL,
                                              OrganizationStatus.EXPIRING,
                                              OrganizationStatus.EXPIRED,
                                              OrganizationStatus.SUSPENDED):
            org.status = OrganizationStatus.ACTIVE

        charge.applied_at = _now()
        self.db.flush()

        # scope=None: this runs from a webhook or a scheduled job, where there
        # is no signed-in user. The audit row still records who triggered it via
        # user_name, which is what an operator reading the log needs.
        self.audit.record(
            scope=None, module="platform_billing", action=AuditAction.UPDATE,
            description=(f"Subscription paid and extended to "
                         f"{sub.end_date.strftime('%d %b %Y')}"),
            entity_type="subscription", entity_id=str(sub.id),
            user_name=actor)
        self._notify_owner(
            charge.organization_id, "Subscription renewed",
            f"Your {plan.name if plan else 'subscription'} is paid up to "
            f"{sub.end_date.strftime('%d %b %Y')}.")
        log.info("organisation %s extended to %s", charge.organization_id,
                 sub.end_date)
        return True

    # ------------------------------------------------------- reconcile --
    def reconcile_open(self, older_than_minutes: int = 10) -> dict:
        """
        Settle charges that were left in limbo.

        Two causes: a webhook that never arrived, and a call that timed out
        after Dygine had already acted. Both look identical from here, and both
        are answered the same way - ask Dygine what actually happened.

        This is the reason an owner who paid and then lost their connection does
        not have to contact support.
        """
        if not self.dygine.enabled:
            return {"checked": 0, "settled": 0}

        cutoff = _now() - timedelta(minutes=older_than_minutes)
        open_charges = self.db.scalars(select(PlatformCharge).where(
            PlatformCharge.status == "created",
            PlatformCharge.created_at < cutoff)).all()

        settled = 0
        for charge in open_charges:
            ref = charge.dygine_payment_ref
            if not ref:
                # A gateway charge with no payment reference yet: the owner
                # probably never completed the checkout. Leave it.
                continue
            try:
                payment = self.dygine.get_payment(ref)
            except DygineError:
                continue
            if payment.get("status") == "captured":
                charge.status = "paid"
                charge.paid_at = charge.paid_at or _now()
                self.db.flush()
                if self._apply(charge, actor="reconcile"):
                    settled += 1

        if settled:
            log.info("reconcile settled %s charges", settled)
        return {"checked": len(open_charges), "settled": settled}

    # ------------------------------------------------------- auto-debit --
    def run_auto_debit(self) -> dict:
        """
        Take renewals from the wallet on the day they fall due.

        The reason this exists: a wallet that has to be spent by hand is a
        prepaid account with extra steps. An owner who topped up specifically so
        their service would not lapse should not then have to remember to press
        a button on the right day.

        Only touches organisations that opted in, and only when the balance
        covers the whole charge - a partial debit would leave them paid-for-part
        of a month, which is not a state the subscription model has.
        """
        if not self.dygine.enabled:
            return {"charged": [], "insufficient": [], "failed": []}

        today = date.today()
        charged: list[str] = []
        insufficient: list[str] = []
        failed: list[str] = []

        due = self.db.scalars(select(Subscription).where(
            Subscription.is_current.is_(True),
            Subscription.end_date <= today,
            Subscription.status.in_([SubscriptionStatus.ACTIVE,
                                     SubscriptionStatus.EXPIRED]))).all()

        for sub in due:
            prof = self.profile(sub.organization_id)
            if not prof.auto_debit_enabled:
                continue
            try:
                charge = self.pay_from_wallet(sub.organization_id,
                                              actor="auto-debit")
                charged.append(str(sub.organization_id))
                self.db.commit()
            except DygineError as exc:
                self.db.rollback()
                if exc.is_insufficient_balance:
                    insufficient.append(str(sub.organization_id))
                    self._notify_owner(
                        sub.organization_id, "Top up to keep your service",
                        "Your subscription is due and your wallet balance does "
                        "not cover it. Top up to renew automatically.")
                    self.db.commit()
                else:
                    failed.append(str(sub.organization_id))
                    log.warning("auto-debit failed for %s: %s",
                                sub.organization_id, exc)
            except Exception as exc:             # noqa: BLE001
                self.db.rollback()
                failed.append(str(sub.organization_id))
                log.exception("auto-debit error for %s", sub.organization_id)

        return {"charged": charged, "insufficient": insufficient,
                "failed": failed}

    def warn_low_balance(self) -> list[str]:
        """
        Tell owners whose wallet will not cover the renewal, before the day.

        A silent failure on renewal day is a support ticket. A warning a week
        earlier is a top-up.
        """
        row = self.db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
        window = row.wallet_low_balance_warning_days if row else 7
        if window <= 0 or not self.dygine.enabled:
            return []

        today = date.today()
        horizon = today + timedelta(days=window)
        warned: list[str] = []

        upcoming = self.db.scalars(select(Subscription).where(
            Subscription.is_current.is_(True),
            Subscription.end_date > today,
            Subscription.end_date <= horizon,
            Subscription.status.in_([SubscriptionStatus.ACTIVE,
                                     SubscriptionStatus.TRIAL]))).all()

        for sub in upcoming:
            prof = self.profile(sub.organization_id)
            if not prof.auto_debit_enabled:
                continue
            if prof.low_balance_notified_on == today:
                continue                         # one warning a day, not one per run

            plan = self.db.get(SubscriptionPlan, sub.plan_id)
            if plan is None:
                continue
            needed = rupees_to_paise(plan.price)
            balance, _, live = self.wallet_balance(sub.organization_id)
            if not live or balance >= needed:
                continue

            short = needed - balance
            self._notify_owner(
                sub.organization_id, "Your wallet will not cover the renewal",
                f"Your {plan.name} renews on "
                f"{sub.end_date.strftime('%d %b')}. You need "
                f"\u20b9{paise_to_rupees(short):,.2f} more in your wallet.")
            prof.low_balance_notified_on = today
            warned.append(str(sub.organization_id))

        self.db.flush()
        return warned

    # ------------------------------------------------------------ inbound --
    def handle_event(self, event: DygineEvent) -> None:
        """
        Apply one webhook from Dygine.

        Callers must have verified the signature and stored the row first. This
        function trusts its input entirely and is not safe to call on anything
        unverified.
        """
        data = (event.payload or {}).get("data", {})
        kind = event.event_type

        if kind == "payment.captured":
            self._on_payment_captured(data)
        elif kind == "payment.failed":
            self._on_payment_failed(data)
        elif kind in ("wallet.credited", "wallet.debited"):
            self._on_wallet_moved(data)
        elif kind == "invoice.issued":
            self._on_invoice(data)
        else:
            log.info("ignoring unhandled dygine event %s", kind)

    def _charge_from_notes(self, data: dict) -> PlatformCharge | None:
        """
        Find the local charge an event refers to.

        Tries the payment reference first, then the order notes we set at
        checkout. Two paths because a wallet debit has no Dygine payment id but
        does carry our idempotency key.
        """
        ref = data.get("id")
        if ref:
            found = self.db.scalars(select(PlatformCharge).where(
                PlatformCharge.dygine_payment_ref == ref)).first()
            if found:
                return found

        order = data.get("order") or {}
        notes = order.get("notes") or {}
        org_id, period = notes.get("organization_id"), notes.get("period")
        if org_id and period:
            key = f"sub:{org_id}:{period}"
            return self.db.scalars(select(PlatformCharge).where(
                PlatformCharge.idempotency_key == key)).first()
        if org_id and order.get("purpose") == "wallet_topup":
            return self.db.scalars(select(PlatformCharge).where(
                PlatformCharge.organization_id == uuid.UUID(org_id),
                PlatformCharge.purpose == "wallet_topup",
                PlatformCharge.status == "created")
                .order_by(PlatformCharge.created_at.desc())).first()
        return None

    def _on_payment_captured(self, data: dict) -> None:
        charge = self._charge_from_notes(data)
        if charge is None:
            log.warning("captured payment %s matches no local charge",
                        data.get("id"))
            return

        charge.dygine_payment_ref = data.get("id") or charge.dygine_payment_ref
        invoice = data.get("invoice") or {}
        charge.dygine_invoice_number = invoice.get("number")
        charge.dygine_invoice_id = invoice.get("id")
        if charge.status != "paid":
            charge.status = "paid"
            charge.paid_at = _now()
        self.db.flush()

        # Confirm any coupon that was reserved against this charge.
        for redemption in self.db.scalars(select(CouponRedemption).where(
                CouponRedemption.charge_id == charge.id,
                CouponRedemption.state == "reserved")):
            self.coupons.confirm(redemption, charge.id)

        if charge.purpose == "wallet_topup":
            self.wallet_balance(charge.organization_id)   # refresh the cache
            charge.applied_at = _now()
            self._notify_owner(
                charge.organization_id, "Wallet topped up",
                f"\u20b9{paise_to_rupees(charge.net_paise):,.2f} has been added "
                f"to your wallet.")
            self.db.flush()
        else:
            self._apply(charge, actor="dygine-webhook")

    def _on_payment_failed(self, data: dict) -> None:
        charge = self._charge_from_notes(data)
        if charge is None or charge.status == "paid":
            return
        charge.status = "failed"
        charge.failure_reason = (data.get("failure_reason")
                                 or "Payment failed")[:400]
        self.db.flush()
        for redemption in self.db.scalars(select(CouponRedemption).where(
                CouponRedemption.charge_id == charge.id,
                CouponRedemption.state == "reserved")):
            self.coupons.release(redemption, "payment failed")

    def _on_wallet_moved(self, data: dict) -> None:
        external = data.get("customer_external_id")
        if not external:
            return
        try:
            org_id = uuid.UUID(external)
        except ValueError:
            return
        self.cache_balance(org_id, int(data.get("balance") or 0))

    def _on_invoice(self, data: dict) -> None:
        number = data.get("number")
        if not number:
            return
        charge = self.db.scalars(select(PlatformCharge).where(
            PlatformCharge.dygine_invoice_number == number)).first()
        if charge is not None:
            charge.dygine_invoice_id = data.get("id") or charge.dygine_invoice_id
            self.db.flush()

    # ------------------------------------------------------------ helper --
    def _notify_owner(self, organization_id: uuid.UUID, title: str,
                      message: str) -> None:
        """
        Notify whoever manages billing for this organisation.

        Uses the existing permission-holder fan-out rather than picking a single
        user: an organisation with a separate accounts person should have that
        person told, not just the owner on record.
        """
        try:
            self.notify.to_permission_holders(
                organization_id, "settings.manage",
                NotificationType.SUBSCRIPTION, title, message)
        except Exception:                        # noqa: BLE001
            # A notification failure must never roll back a payment.
            log.exception("could not notify organisation %s", organization_id)


def _cycle_days(billing_cycle: str) -> int:
    return {"MONTHLY": 30, "QUARTERLY": 91,
            "HALF_YEARLY": 182, "YEARLY": 365}.get(
                str(billing_cycle).upper(), 30)


def _platform_name(db: Session) -> str:
    try:
        row = db.get(PlatformSettings, uuid.UUID(SINGLETON_ID))
        return row.platform_name if row and row.platform_name else "PGuru"
    except Exception:                            # noqa: BLE001
        return "PGuru"


#: Indian state to GST state code. Decides CGST/SGST versus IGST on the invoice,
#: so a wrong or missing entry means tax is charged under the wrong head.
STATE_CODES = {
    "jammu and kashmir": "01", "himachal pradesh": "02", "punjab": "03",
    "chandigarh": "04", "uttarakhand": "05", "haryana": "06", "delhi": "07",
    "rajasthan": "08", "uttar pradesh": "09", "bihar": "10", "sikkim": "11",
    "arunachal pradesh": "12", "nagaland": "13", "manipur": "14",
    "mizoram": "15", "tripura": "16", "meghalaya": "17", "assam": "18",
    "west bengal": "19", "jharkhand": "20", "odisha": "21", "chhattisgarh": "22",
    "madhya pradesh": "23", "gujarat": "24", "maharashtra": "27",
    "karnataka": "29", "goa": "30", "lakshadweep": "31", "kerala": "32",
    "tamil nadu": "33", "puducherry": "34", "andaman and nicobar islands": "35",
    "telangana": "36", "andhra pradesh": "37", "ladakh": "38",
}


def _state_code(state: str | None) -> str | None:
    if not state:
        return None
    return STATE_CODES.get(state.strip().lower())


class InvoiceMailer:
    """
    Emails the invoice PDF to the owner, a short while after payment.

    Why not immediately: the payment page is still open and the customer is
    watching a spinner. An email landing in that second is noise. More
    practically, the invoice is issued inside the capture transaction and the
    PDF is fetched over the network - doing that inline would put an outbound
    HTTP call and an SMTP conversation on the critical path of taking money,
    where a slow mail server becomes a failed payment.

    So it runs from the scheduled job, and `invoice_emailed_at` guards against
    sending twice.
    """

    #: Minutes to wait after payment before the email goes out.
    DELAY_MINUTES = 10

    def __init__(self, db: Session):
        self.db = db
        self.billing = PlatformBillingService(db)

    def pending(self, now: datetime | None = None) -> list[PlatformCharge]:
        now = now or _now()
        cutoff = now - timedelta(minutes=self.DELAY_MINUTES)
        return list(self.db.scalars(select(PlatformCharge).where(
            PlatformCharge.status == "paid",
            PlatformCharge.invoice_emailed_at.is_(None),
            PlatformCharge.dygine_invoice_id.isnot(None),
            PlatformCharge.paid_at.isnot(None),
            PlatformCharge.paid_at <= cutoff)))

    def send_all(self) -> dict:
        """One pass. Safe to run repeatedly; each charge is emailed once."""
        sent, failed = 0, 0
        for charge in self.pending():
            try:
                if self.send_one(charge):
                    sent += 1
            except Exception as exc:             # noqa: BLE001
                failed += 1
                charge.invoice_email_error = str(exc)[:400]
                log.warning("invoice email failed for charge %s: %s",
                            charge.id, exc)
            self.db.commit()
        if sent or failed:
            log.info("invoice emails sent=%s failed=%s", sent, failed)
        return {"sent": sent, "failed": failed}

    def send_one(self, charge: PlatformCharge) -> bool:
        from app.services.email_service import EmailNotConfigured, EmailService

        org = self.db.get(Organization, charge.organization_id)
        if org is None or not org.owner_email:
            # Nothing to send to. Mark it done rather than retrying forever.
            charge.invoice_emailed_at = _now()
            charge.invoice_email_error = "No owner email on file"
            return False

        try:
            pdf = self.billing.dygine.invoice_pdf(charge.dygine_invoice_id)
        except DygineError as exc:
            # Leave it unsent; the next pass retries. A payments service that
            # is briefly asleep should not cost the customer their invoice.
            raise RuntimeError(f"Could not fetch the invoice PDF: {exc}") from None

        platform = _platform_name(self.db)
        number = charge.dygine_invoice_number or "your invoice"
        amount = f"\u20b9{paise_to_rupees(charge.net_paise):,.2f}"
        period = (charge.period.strftime("%B %Y") if charge.period else "")

        subject = f"{platform} invoice {number}"
        body = (
            f"Hello {org.owner_name or org.name},\n\n"
            f"Thank you for your payment of {amount}"
            + (f" for {period}" if period else "") + ".\n\n"
            f"Your invoice {number} is attached as a PDF.\n\n"
            f"You can see all your invoices any time under "
            f"My subscription in {platform}.\n\n"
            f"— {platform}\n")
        html = (
            f"<p>Hello {org.owner_name or org.name},</p>"
            f"<p>Thank you for your payment of <strong>{amount}</strong>"
            + (f" for {period}" if period else "") + ".</p>"
            f"<p>Your invoice <strong>{number}</strong> is attached as a PDF.</p>"
            f"<p>You can see all your invoices any time under "
            f"<em>My subscription</em> in {platform}.</p>"
            f"<p>— {platform}</p>")

        filename = number.replace("/", "-") + ".pdf"
        try:
            EmailService(self.db).send(
                to=org.owner_email, subject=subject, body=body, html=html,
                attachments=[(filename, pdf, "application/pdf")])
        except EmailNotConfigured:
            # No mail provider on this deployment. Not an error worth retrying
            # every ten minutes forever - record it and move on.
            charge.invoice_emailed_at = _now()
            charge.invoice_email_error = "No mail provider configured"
            return False

        charge.invoice_emailed_at = _now()
        charge.invoice_email_error = None
        log.info("invoice %s emailed to %s", number, org.owner_email)
        return True
