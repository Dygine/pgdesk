"""
Platform billing: coupons, wallet payment, and the webhook path.

The coupon concurrency test uses real threads against real Postgres on purpose.
What is being tested *is* the database's locking behaviour, so a mock would
prove nothing at all.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Coupon, CouponAssignment, CouponRedemption, DygineEvent, Organization,
    OrgBillingProfile, PlatformCharge, Subscription, SubscriptionPlan,
)
from app.models.enums import OrganizationStatus, SubscriptionStatus
from app.services.coupon_service import CouponError, CouponService, normalise
from app.services.dygine_client import DygineError, verify_webhook
from app.services.platform_billing_service import (
    PlatformBillingService, paise_to_rupees, period_of, rupees_to_paise,
)
from tests.conftest import TestSession, engine
from tests.factories import make_org, make_plan


# --------------------------------------------------------------- units --
class TestUnitConversion:
    """
    The single most dangerous bug in this integration.

    SubscriptionPlan.price is Integer *rupees*. Dygine speaks *paise*. A missed
    conversion does not fail loudly - it charges a hundred times too much.
    """

    @pytest.mark.parametrize("rupees,paise", [
        (1499, 149900), (499, 49900), (0, 0), (1, 100), (99999, 9999900),
    ])
    def test_rupees_to_paise(self, rupees, paise):
        assert rupees_to_paise(rupees) == paise

    def test_round_trip_is_stable(self):
        for rupees in (1, 499, 1499, 99999):
            assert paise_to_rupees(rupees_to_paise(rupees)) == float(rupees)

    def test_fractional_rupees_do_not_drift(self):
        # 1499.99 must be 149999 paise, not 149998 via a float round-down.
        assert rupees_to_paise(1499.99) == 149999
        assert rupees_to_paise(0.01) == 1


class TestPeriod:
    def test_period_is_first_of_month(self):
        assert period_of(date(2026, 9, 14)) == date(2026, 9, 1)
        assert period_of(date(2026, 1, 31)) == date(2026, 1, 1)


# ------------------------------------------------------------- coupons --
@pytest.fixture
def org(db):
    """
    An organisation with one current subscription at a known price.

    make_org already creates a plan and subscription; adding a second would
    leave two rows with is_current=True and whichever came back first would
    decide the price. Adjust what it made instead.
    """
    organisation = make_org(db, "Sunrise PG")
    sub = db.scalars(select(Subscription).where(
        Subscription.organization_id == organisation.id)).first()
    plan = db.get(SubscriptionPlan, sub.plan_id)
    plan.price = 1499
    plan.code = "plan_pro"
    sub.end_date = date.today() + timedelta(days=1)
    db.flush()
    return organisation


@pytest.fixture
def plan(db, org):
    sub = db.scalars(select(Subscription).where(
        Subscription.organization_id == org.id)).first()
    return db.get(SubscriptionPlan, sub.plan_id)


def make_coupon(db, code="SAVE20", **kwargs):
    defaults = dict(kind="percent", value=20, min_amount_paise=0,
                    applies_to_plans=[], applies_to_cycles=1,
                    max_per_org=1, status="active")
    defaults.update(kwargs)
    coupon = Coupon(code=normalise(code), **defaults)
    db.add(coupon)
    db.flush()
    return coupon


class TestCouponMath:
    def test_percent_discount(self, db, org, plan):
        coupon = make_coupon(db)
        svc = CouponService(db)
        assert svc.discount_for(coupon, 149900) == 29980

    def test_percent_is_capped(self, db):
        coupon = make_coupon(db, value=50, max_discount_paise=10000)
        assert CouponService(db).discount_for(coupon, 149900) == 10000

    def test_fixed_discount(self, db):
        coupon = make_coupon(db, kind="fixed", value=50000)
        assert CouponService(db).discount_for(coupon, 149900) == 50000

    def test_discount_never_exceeds_the_charge(self, db):
        """A discount bigger than the bill is a credit note, not a payment."""
        coupon = make_coupon(db, kind="fixed", value=500000)
        assert CouponService(db).discount_for(coupon, 149900) == 149900

    def test_code_is_normalised(self, db):
        make_coupon(db, code="save20")
        assert CouponService(db).by_code("  SaVe20 ") is not None


class TestCouponValidation:
    def test_unknown_code(self, db, org):
        with pytest.raises(CouponError, match="not valid"):
            CouponService(db).validate("NOPE", org.id, 149900)

    def test_paused_coupon(self, db, org):
        make_coupon(db, status="paused")
        with pytest.raises(CouponError, match="not currently active"):
            CouponService(db).validate("SAVE20", org.id, 149900)

    def test_expired_by_date(self, db, org):
        make_coupon(db, valid_until=date.today() - timedelta(days=1))
        with pytest.raises(CouponError, match="expired"):
            CouponService(db).validate("SAVE20", org.id, 149900)

    def test_not_yet_valid(self, db, org):
        make_coupon(db, valid_from=date.today() + timedelta(days=5))
        with pytest.raises(CouponError, match="not valid until"):
            CouponService(db).validate("SAVE20", org.id, 149900)

    def test_below_minimum(self, db, org):
        make_coupon(db, min_amount_paise=200000)
        with pytest.raises(CouponError, match="or more"):
            CouponService(db).validate("SAVE20", org.id, 149900)

    def test_wrong_plan(self, db, org, plan):
        make_coupon(db, applies_to_plans=["plan_enterprise"])
        with pytest.raises(CouponError, match="does not apply"):
            CouponService(db).validate("SAVE20", org.id, 149900, plan)

    def test_targeted_coupon_hides_from_others(self, db, org):
        """
        A stranger gets "not valid", not "not for you".

        Telling someone a code exists but is not theirs is an invitation to go
        looking for one that is.
        """
        other = make_org(db, "Other PG")
        db.flush()
        coupon = make_coupon(db)
        db.add(CouponAssignment(coupon_id=coupon.id, organization_id=org.id))
        db.flush()

        assert CouponService(db).validate("SAVE20", org.id, 149900).discount_paise
        with pytest.raises(CouponError, match="not valid"):
            CouponService(db).validate("SAVE20", other.id, 149900)

    def test_available_for_lists_targeted_only(self, db, org):
        make_coupon(db, code="PUBLIC")
        targeted = make_coupon(db, code="YOURS")
        db.add(CouponAssignment(coupon_id=targeted.id, organization_id=org.id))
        db.flush()

        codes = [c.code for c in CouponService(db).available_for(org.id)]
        assert codes == ["YOURS"]          # a public campaign code is not leaked


class TestCouponReservation:
    def test_reserve_then_confirm(self, db, org, plan):
        make_coupon(db)
        svc = CouponService(db)
        quote, redemption = svc.reserve("SAVE20", org.id, 149900, plan=plan)

        assert quote.discount_paise == 29980
        assert quote.net_paise == 119920
        assert redemption.state == "reserved"

        svc.confirm(redemption)
        assert redemption.state == "confirmed"
        assert redemption.reserved_until is None

    def test_release_frees_the_redemption(self, db, org, plan):
        make_coupon(db, max_redemptions=1)
        svc = CouponService(db)
        _, redemption = svc.reserve("SAVE20", org.id, 149900, plan=plan)

        # Held: a second org cannot take the last one.
        other = make_org(db, "Other PG")
        db.flush()
        with pytest.raises(CouponError, match="fully redeemed"):
            svc.validate("SAVE20", other.id, 149900)

        svc.release(redemption, "payment failed")
        assert svc.validate("SAVE20", other.id, 149900).discount_paise == 29980

    def test_confirmed_redemption_cannot_be_released(self, db, org, plan):
        """Releasing a confirmed one hands back a discount already given."""
        make_coupon(db)
        svc = CouponService(db)
        _, redemption = svc.reserve("SAVE20", org.id, 149900, plan=plan)
        svc.confirm(redemption)
        svc.release(redemption, "oops")
        assert redemption.state == "confirmed"

    def test_expired_reservation_is_not_counted(self, db, org, plan):
        make_coupon(db, max_redemptions=1)
        svc = CouponService(db)
        _, redemption = svc.reserve("SAVE20", org.id, 149900, plan=plan)
        redemption.reserved_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.flush()

        other = make_org(db, "Other PG")
        db.flush()
        # The checkout was abandoned; the redemption is free again even before
        # the sweep gets round to marking the row released.
        assert svc.validate("SAVE20", other.id, 149900).discount_paise == 29980

    def test_sweep_releases_expired(self, db, org, plan):
        make_coupon(db)
        svc = CouponService(db)
        _, redemption = svc.reserve("SAVE20", org.id, 149900, plan=plan)
        redemption.reserved_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.flush()

        assert svc.sweep_expired() == 1
        assert redemption.state == "released"

    def test_same_period_reuses_the_reservation(self, db, org, plan):
        """A retried renewal must not take a second redemption."""
        make_coupon(db, max_per_org=1)
        svc = CouponService(db)
        period = period_of()
        _, first = svc.reserve("SAVE20", org.id, 149900, plan=plan, period=period)
        _, second = svc.reserve("SAVE20", org.id, 149900, plan=plan, period=period)
        assert first.id == second.id

    def test_per_org_limit(self, db, org, plan):
        make_coupon(db, max_per_org=1, applies_to_cycles=None)
        svc = CouponService(db)
        _, redemption = svc.reserve("SAVE20", org.id, 149900, plan=plan,
                                    period=date(2026, 1, 1))
        svc.confirm(redemption)
        with pytest.raises(CouponError, match="already used"):
            svc.validate("SAVE20", org.id, 149900)

    def test_cycle_limit_stops_a_permanent_price_cut(self, db, org, plan):
        """
        applies_to_cycles=1 means the discount applies once, not every month
        forever. Without it a 20% coupon is a permanent price cut.
        """
        make_coupon(db, applies_to_cycles=1, max_per_org=5)
        svc = CouponService(db)
        _, redemption = svc.reserve("SAVE20", org.id, 149900, plan=plan,
                                    period=date(2026, 1, 1))
        svc.confirm(redemption)
        with pytest.raises(CouponError, match="billing cycles"):
            svc.validate("SAVE20", org.id, 149900)


class TestCouponConcurrency:
    """
    Real threads, real Postgres. What is under test *is* the row lock, so a
    mock would prove nothing.

    Note this class does not use the `db` fixture. That fixture holds everything
    in a transaction it rolls back, so data written through it is invisible to
    any other connection - and the threads here need their own connections.
    """

    def test_single_use_coupon_cannot_be_reserved_twice(self):
        """
        Ten organisations race for one redemption. Exactly one wins.

        Without SELECT ... FOR UPDATE on the coupon row every thread counts zero
        existing redemptions, every thread passes, and ten customers get a
        discount that was issued once.
        """
        setup = TestSession(bind=engine)
        coupon_id = None
        org_ids: list[uuid.UUID] = []
        try:
            coupon = Coupon(code=f"RACE{uuid.uuid4().hex[:6].upper()}",
                            kind="percent", value=20, min_amount_paise=0,
                            applies_to_plans=[], applies_to_cycles=1,
                            max_redemptions=1, max_per_org=1, status="active")
            setup.add(coupon)
            setup.flush()
            coupon_id, code = coupon.id, coupon.code

            for i in range(10):
                org = Organization(
                    name=f"Race PG {i}",
                    slug=f"race-pg-{uuid.uuid4().hex[:8]}",
                    owner_name="Owner",
                    owner_email=f"owner@{uuid.uuid4().hex[:8]}.test",
                    status=OrganizationStatus.ACTIVE, city="Bengaluru")
                setup.add(org)
                setup.flush()
                org_ids.append(org.id)
            setup.commit()
        finally:
            setup.close()

        won, refused, errors = [], [], []
        barrier = threading.Barrier(10)

        def worker(org_id):
            barrier.wait()                      # maximise the overlap
            session = TestSession(bind=engine)
            try:
                CouponService(session).reserve(code, org_id, 149900)
                session.commit()
                won.append(org_id)
            except CouponError:
                session.rollback()
                refused.append(org_id)
            except Exception as exc:              # noqa: BLE001
                session.rollback()
                errors.append(exc)
            finally:
                session.close()

        threads = [threading.Thread(target=worker, args=(oid,))
                   for oid in org_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        check = TestSession(bind=engine)
        try:
            assert not errors, f"unexpected failures: {errors[:2]}"
            assert len(won) == 1, f"expected exactly 1 winner, got {len(won)}"
            assert len(refused) == 9

            live = check.scalars(select(CouponRedemption).where(
                CouponRedemption.coupon_id == coupon_id,
                CouponRedemption.state == "reserved")).all()
            assert len(live) == 1, "the coupon was over-issued"
        finally:
            check.query(CouponRedemption).filter(
                CouponRedemption.coupon_id == coupon_id).delete(
                    synchronize_session=False)
            check.query(Coupon).filter(Coupon.id == coupon_id).delete(
                synchronize_session=False)
            check.query(Organization).filter(
                Organization.id.in_(org_ids)).delete(synchronize_session=False)
            check.commit()
            check.close()


# -------------------------------------------------------------- webhook --
class TestWebhookSignature:
    SECRET = "test-webhook-secret-long-enough"

    def _sign(self, body: bytes) -> str:
        import hashlib
        import hmac
        return "sha256=" + hmac.new(self.SECRET.encode(), body,
                                    hashlib.sha256).hexdigest()

    def test_valid_signature_passes(self):
        body = json.dumps({"event": "payment.captured"}).encode()
        assert verify_webhook(self.SECRET, body, self._sign(body))

    def test_tampered_body_fails(self):
        body = json.dumps({"event": "payment.captured", "amount": 100}).encode()
        signature = self._sign(body)
        tampered = json.dumps({"event": "payment.captured",
                               "amount": 999999}).encode()
        assert not verify_webhook(self.SECRET, tampered, signature)

    def test_reserialised_body_fails(self):
        """
        The mistake that leads people to disable verification: parse, re-dump,
        signature no longer matches.
        """
        body = json.dumps({"event": "payment.captured", "a": 1, "b": 2}).encode()
        signature = self._sign(body)
        reserialised = json.dumps(json.loads(body),
                                  separators=(",", ":")).encode()
        assert body != reserialised
        assert not verify_webhook(self.SECRET, reserialised, signature)

    def test_empty_secret_never_verifies(self):
        body = b"{}"
        assert not verify_webhook("", body, self._sign(body))

    def test_missing_signature_fails(self):
        assert not verify_webhook(self.SECRET, b"{}", "")


class TestWebhookEndpoint:
    def test_unsigned_webhook_is_rejected(self, client):
        r = client.post("/api/v1/webhooks/dygine",
                        content=json.dumps({"event": "payment.captured"}))
        # 503 when no secret is configured, 400 when one is and it did not
        # match. Either way nothing was applied.
        assert r.status_code in (400, 503)

    def test_nothing_is_stored_for_an_unverified_body(self, client, db):
        client.post("/api/v1/webhooks/dygine",
                    content=json.dumps({"event": "payment.captured"}),
                    headers={"X-Dygine-Signature": "sha256=deadbeef"})
        assert db.scalars(select(DygineEvent)).first() is None


# -------------------------------------------------------- billing service --
class TestBillingProfile:
    def test_profile_is_created_lazily(self, db, org):
        svc = PlatformBillingService(db)
        assert db.scalars(select(OrgBillingProfile).where(
            OrgBillingProfile.organization_id == org.id)).first() is None

        prof = svc.profile(org.id)
        assert prof.dygine_external_id == str(org.id)
        assert prof.auto_debit_enabled is True

    def test_external_id_is_the_uuid_not_the_name(self, db, org):
        """The mapping has to survive a rename."""
        prof = PlatformBillingService(db).profile(org.id)
        org.name = "Renamed PG"
        db.flush()
        assert prof.dygine_external_id == str(org.id)

    def test_cached_balance_is_marked_stale_when_offline(self, db, org):
        svc = PlatformBillingService(db)
        prof = svc.profile(org.id)
        prof.cached_wallet_paise = 500000
        prof.cached_at = datetime.now(timezone.utc)
        db.flush()

        # Dygine is not configured in tests, so this must fall back and say so.
        balance, as_of, live = svc.wallet_balance(org.id)
        assert balance == 500000
        assert live is False, "a cached balance must never be reported as live"


class TestQuote:
    def test_quote_without_coupon(self, db, org, plan):
        info = PlatformBillingService(db).quote(org.id)
        assert info.quote.gross_paise == 149900
        assert info.quote.discount_paise == 0
        assert info.quote.net_paise == 149900

    def test_quote_with_coupon(self, db, org, plan):
        make_coupon(db)
        info = PlatformBillingService(db).quote(org.id, coupon_code="SAVE20")
        assert info.quote.discount_paise == 29980
        assert info.quote.net_paise == 119920

    def test_wallet_covers_flag(self, db, org, plan):
        svc = PlatformBillingService(db)
        prof = svc.profile(org.id)
        prof.cached_wallet_paise = 200000
        db.flush()
        assert svc.quote(org.id).wallet_covers is True

        prof.cached_wallet_paise = 10000
        db.flush()
        assert svc.quote(org.id).wallet_covers is False


class TestApplyCharge:
    def _paid_charge(self, db, org, plan, period=None):
        charge = PlatformCharge(
            organization_id=org.id, plan_id=plan.id, purpose="subscription",
            method="wallet", period=period or period_of(), gross_paise=149900,
            discount_paise=0, net_paise=149900, status="paid",
            paid_at=datetime.now(timezone.utc),
            idempotency_key=f"sub:{org.id}:{uuid.uuid4().hex[:8]}")
        db.add(charge)
        db.flush()
        return charge

    def test_apply_extends_the_subscription(self, db, org, plan):
        svc = PlatformBillingService(db)
        sub = db.scalars(select(Subscription).where(
            Subscription.organization_id == org.id)).first()
        before = sub.end_date

        assert svc._apply(self._paid_charge(db, org, plan)) is True
        db.refresh(sub)
        assert sub.end_date == before + timedelta(days=30)
        assert sub.status == SubscriptionStatus.ACTIVE

    def test_apply_runs_once_per_charge(self, db, org, plan):
        """
        The guard that stops a redelivered webhook granting two months for one
        payment.
        """
        svc = PlatformBillingService(db)
        charge = self._paid_charge(db, org, plan)
        sub = db.scalars(select(Subscription).where(
            Subscription.organization_id == org.id)).first()
        before = sub.end_date

        assert svc._apply(charge) is True
        assert svc._apply(charge) is False
        db.refresh(sub)
        assert sub.end_date == before + timedelta(days=30)

    def test_paying_early_does_not_lose_days(self, db, org, plan):
        """Extension runs from the existing end date when it is still ahead."""
        sub = db.scalars(select(Subscription).where(
            Subscription.organization_id == org.id)).first()
        sub.end_date = date.today() + timedelta(days=20)
        db.flush()

        PlatformBillingService(db)._apply(self._paid_charge(db, org, plan))
        db.refresh(sub)
        assert sub.end_date == date.today() + timedelta(days=50)

    def test_expired_org_is_reactivated(self, db, org, plan):
        org.status = OrganizationStatus.SUSPENDED
        db.flush()
        PlatformBillingService(db)._apply(self._paid_charge(db, org, plan))
        db.refresh(org)
        assert org.status == OrganizationStatus.ACTIVE

    def test_unpaid_charge_is_never_applied(self, db, org, plan):
        charge = self._paid_charge(db, org, plan)
        charge.status = "created"
        charge.applied_at = None
        db.flush()
        assert PlatformBillingService(db)._apply(charge) is False


class TestChargeIdempotency:
    def test_same_key_returns_the_same_charge(self, db, org, plan):
        svc = PlatformBillingService(db)
        key = f"sub:{org.id}:2026-10-01"
        first = svc._charge(
            organization_id=org.id, purpose="subscription", method="gateway",
            gross=149900, discount=0, net=149900, period=date(2026, 10, 1),
            plan_id=plan.id, idempotency_key=key)
        second = svc._charge(
            organization_id=org.id, purpose="subscription", method="gateway",
            gross=149900, discount=0, net=149900, period=date(2026, 10, 1),
            plan_id=plan.id, idempotency_key=key)
        assert first.id == second.id
        assert len(db.scalars(select(PlatformCharge)).all()) == 1


class TestGatewayUnavailable:
    def test_checkout_fails_cleanly_when_dygine_is_not_configured(self, db, org,
                                                                  plan):
        """
        An operator who has not set up payments gets a clear refusal, not a
        stack trace - and no half-created charge left behind.
        """
        with pytest.raises(DygineError):
            PlatformBillingService(db).start_subscription_checkout(org.id)

    def test_coupon_is_released_when_checkout_fails(self, db, org, plan):
        """A failed payment must not consume the customer's discount."""
        make_coupon(db)
        svc = PlatformBillingService(db)
        with pytest.raises(DygineError):
            svc.start_subscription_checkout(org.id, coupon_code="SAVE20")

        redemption = db.scalars(select(CouponRedemption)).first()
        assert redemption is not None
        assert redemption.state == "released"
