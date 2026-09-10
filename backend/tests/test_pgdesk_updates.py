"""
The September 2026 additions: staff list and salaries, checkout notice, the
query centre reaching residents, the weekly menu, resident payments (UPI with a
mandatory UTR, Razorpay with signature checks) and the P&L.
"""
import hashlib
import hmac
import json
from datetime import date, timedelta

import pytest

from app.models import Expense, FoodMenu, Notification, PaymentSettings
from app.models.enums import CustomerStatus
from app.services import payment_gateway_service as gateway
from tests.factories import (
    PASSWORD, make_branch, make_customer, make_org, make_property, make_role, make_user,
)

API = "/api/v1"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, email: str) -> str:
    r = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


@pytest.fixture
def pg(db, client):
    org = make_org(db, "Sunrise PG")
    other = make_org(db, "Rival PG")
    branch = make_branch(db, org, "Koramangala", "KOR")
    make_branch(db, other, "Indiranagar", "IND")
    prop = make_property(db, org, branch, beds=2, rent=9000)
    make_user(db, org, "owner@sunrise.test",
              role=make_role(db, org, "Owner", ["*"], all_branches=True, is_system=True))
    make_user(db, other, "owner@rival.test",
              role=make_role(db, other, "Owner", ["*"], all_branches=True, is_system=True))
    me = make_customer(db, org, "arjun@sunrise.test", branch=branch,
                       status=CustomerStatus.ACTIVE)
    me.full_name = "Arjun Rao"
    me.monthly_rent = 9000
    me.security_deposit = 18000
    me.bed_id = prop["beds"][0].id
    me.room_id = prop["room"].id
    db.commit()
    return {
        "org": org, "branch": branch, "me": me,
        "owner": auth(login(client, "owner@sunrise.test")),
        "resident": auth(login(client, "arjun@sunrise.test")),
        "rival": auth(login(client, "owner@rival.test")),
    }


def raise_invoice(client, pg, items):
    r = client.post(f"{API}/invoices", headers=pg["owner"], json={
        "resident_id": str(pg["me"].id),
        "items": [{"kind": k, "description": d, "quantity": 1, "unit_price": a}
                  for k, d, a in items]})
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ------------------------------------------------------------------ staff
def test_staff_are_people_not_logins_and_salaries_become_expenses(client, pg, db):
    r = client.post(f"{API}/staff", headers=pg["owner"], json={
        "branch_id": str(pg["branch"].id), "full_name": "Lakshmi", "designation": "Cook",
        "phone": "+91 9000000001", "monthly_salary": 14000})
    assert r.status_code == 201, r.text
    staff_id = r.json()["data"]["id"]
    assert r.json()["data"]["user_id"] is None          # a cook needs no login

    listing = client.get(f"{API}/staff", headers=pg["owner"]).json()["data"]
    assert [s["full_name"] for s in listing["items"]] == ["Lakshmi"]
    assert listing["items"][0]["paid_this_period"] is False
    assert listing["summary"]["monthly_payroll"] == 14000

    month = date.today().replace(day=1).isoformat()
    r = client.post(f"{API}/staff/{staff_id}/salary", headers=pg["owner"],
                    json={"period": month, "payment_method": "UPI"})
    assert r.status_code == 201, r.text
    expense = db.get(Expense, __import__("uuid").UUID(r.json()["data"]["id"]))
    assert expense.category == "Salary" and float(expense.amount) == 14000
    assert str(expense.staff_member_id) == staff_id

    again = client.post(f"{API}/staff/{staff_id}/salary", headers=pg["owner"],
                        json={"period": month})
    assert again.status_code == 409                      # same month twice is refused
    assert client.get(f"{API}/staff", headers=pg["owner"]).json()["data"]["items"][0][
        "paid_this_period"] is True
    assert client.get(f"{API}/staff/{staff_id}", headers=pg["rival"]).status_code == 404


# ---------------------------------------------------------- checkout notice
def test_resident_gives_notice_and_the_office_is_told(client, pg, db):
    leaving = (date.today() + timedelta(days=10)).isoformat()
    r = client.post(f"{API}/me/checkout-notice", headers=pg["resident"],
                    json={"planned_checkout_date": leaving, "reason": "New job in Pune"})
    assert r.status_code == 201, r.text
    notice = r.json()["data"]
    assert notice["short_notice"] is True               # 10 days against a 30-day policy
    db.refresh(pg["me"])
    assert pg["me"].status == CustomerStatus.NOTICE     # still living here, still billed
    assert pg["me"].bed_id is not None

    assert client.post(f"{API}/me/checkout-notice", headers=pg["resident"],
                       json={"planned_checkout_date": leaving}).status_code == 409

    office = client.get(f"{API}/checkout-notices", headers=pg["owner"]).json()["data"]
    assert [n["resident"] for n in office] == ["Arjun Rao"]
    assert office[0]["days_left"] == 10
    assert db.query(Notification).filter(Notification.title == "Checkout notice").count() == 1

    r = client.post(f"{API}/checkout-notices/{notice['id']}/acknowledge",
                    headers=pg["owner"], json={"note": "Deposit settles on the day"})
    assert r.json()["data"]["status"] == "ACKNOWLEDGED"

    r = client.post(f"{API}/me/checkout-notice/withdraw", headers=pg["resident"])
    assert r.json()["data"]["status"] == "WITHDRAWN"
    db.refresh(pg["me"])
    assert pg["me"].status == CustomerStatus.ACTIVE
    assert client.get(f"{API}/checkout-notices", headers=pg["rival"]).json()["data"] == []


def test_checkout_closes_the_notice(client, pg):
    client.post(f"{API}/me/checkout-notice", headers=pg["resident"],
                json={"planned_checkout_date": date.today().isoformat()})
    r = client.post(f"{API}/residents/{pg['me'].id}/checkout", headers=pg["owner"], json={})
    assert r.status_code == 200, r.text
    done = client.get(f"{API}/checkout-notices?status=COMPLETED", headers=pg["owner"])
    assert len(done.json()["data"]) == 1


def test_notice_period_setting_decides_what_is_short(client, pg):
    client.patch(f"{API}/settings", headers=pg["owner"], json={"checkout_notice_days": 15})
    r = client.post(f"{API}/me/checkout-notice", headers=pg["resident"], json={
        "planned_checkout_date": (date.today() + timedelta(days=20)).isoformat()})
    assert r.json()["data"]["short_notice"] is False


# -------------------------------------------------------------- query centre
def test_a_query_the_office_opens_reaches_the_resident(client, pg, db):
    r = client.post(f"{API}/queries", headers=pg["owner"], json={
        "resident_id": str(pg["me"].id), "subject": "Aadhaar copy needed",
        "message": "Please drop a copy at the desk this week."})
    assert r.status_code == 201, r.text
    assert r.json()["data"]["opened_by"] == "staff"

    mine = client.get(f"{API}/me/queries", headers=pg["resident"]).json()["data"]
    assert len(mine) == 1
    q = mine[0]
    assert q["opened_by"] == "staff" and q["needs_reply"] is True
    assert q["messages"][0]["is_staff"] is True
    assert q["messages"][0]["author"] != "Arjun Rao"    # was the resident's own name
    note = db.query(Notification).filter(
        Notification.resident_id == pg["me"].id,
        Notification.title == "Message from the office").one()
    assert note.link == "/me/queries"

    client.post(f"{API}/me/queries/{q['id']}/reply", headers=pg["resident"],
                json={"message": "Will do tomorrow."})
    office = client.get(f"{API}/queries", headers=pg["owner"]).json()["data"]
    assert office[0]["status"] == "OPEN"                # ball back with the office


# -------------------------------------------------------------- weekly menu
def test_weekly_menu_feeds_residents_and_specials_override_it(client, pg, db):
    today = date.today()
    r = client.put(f"{API}/food/week", headers=pg["owner"], json={
        "branch_id": str(pg["branch"].id),
        "entries": [{"weekday": today.weekday(), "meal": "LUNCH", "items": "Rice, dal, curd"}]})
    assert r.status_code == 200, r.text

    menus = client.get(f"{API}/me/food", headers=pg["resident"]).json()["data"]["menus"]
    lunch = [m for m in menus if m["on_date"] == today.isoformat() and m["meal"] == "LUNCH"]
    assert lunch[0]["items"] == "Rice, dal, curd" and lunch[0]["source"] == "weekly"
    # Next week's same day repeats it without anyone publishing again.
    assert any(m["on_date"] == (today + timedelta(days=7)).isoformat()
               for m in client.get(f"{API}/me/food?days=7", headers=pg["resident"])
               .json()["data"]["menus"])

    old = FoodMenu(organization_id=pg["org"].id, branch_id=pg["branch"].id,
                   on_date=today - timedelta(days=10), meal="LUNCH", items="Old")
    db.add(old)
    db.commit()
    client.put(f"{API}/food/menus", headers=pg["owner"], json={
        "branch_id": str(pg["branch"].id), "on_date": today.isoformat(),
        "meal": "LUNCH", "items": "Festival biryani"})
    menus = client.get(f"{API}/me/food", headers=pg["resident"]).json()["data"]["menus"]
    lunch = [m for m in menus if m["on_date"] == today.isoformat() and m["meal"] == "LUNCH"]
    assert lunch[0]["items"] == "Festival biryani" and lunch[0]["source"] == "special"
    assert db.query(FoodMenu).filter(FoodMenu.items == "Old").count() == 0   # pruned

    r = client.put(f"{API}/food/schedule", headers=pg["owner"], json={"meals": {
        "SNACK": {"enabled": True, "label": "Evening tea", "serve_from": "17:00",
                  "serve_to": "17:45"}}})
    assert r.json()["data"]["SNACK"]["label"] == "Evening tea"


# ----------------------------------------------------------------- payments
def configure_payments(client, pg, **extra):
    body = {"upi_enabled": True, "upi_id": "sunrisepg@okhdfc", "upi_payee_name": "Sunrise PG",
            "razorpay_key_id": "rzp_test_ABC123", "razorpay_key_secret": "key-secret-xyz",
            "razorpay_webhook_secret": "hook-secret-xyz", "razorpay_enabled": True}
    body.update(extra)
    r = client.put(f"{API}/payment-settings", headers=pg["owner"], json=body)
    assert r.status_code == 200, r.text
    return r


def test_payment_settings_never_give_the_secret_back(client, pg, db):
    r = configure_payments(client, pg)
    for response in (r, client.get(f"{API}/payment-settings", headers=pg["owner"])):
        assert "key-secret-xyz" not in response.text and "hook-secret-xyz" not in response.text
        assert response.json()["data"]["has_key_secret"] is True
    row = db.query(PaymentSettings).one()
    assert row.razorpay_key_secret_encrypted and "key-secret" not in row.razorpay_key_secret_encrypted
    options = client.get(f"{API}/me/payments/options", headers=pg["resident"])
    assert "key-secret" not in options.text
    assert options.json()["data"]["online"] is True
    assert options.json()["data"]["upi"]["upi_id"] == "sunrisepg@okhdfc"
    bad = client.put(f"{API}/payment-settings", headers=pg["owner"], json={"upi_id": "not-a-upi"})
    assert bad.status_code == 409


def test_upi_payment_needs_a_real_unique_utr_and_stays_pending(client, pg):
    configure_payments(client, pg)
    inv = raise_invoice(client, pg, [("RENT", "Rent", 9000)])
    base = {"invoice_id": inv["id"], "method": "UPI", "amount": 9000}

    assert client.post(f"{API}/me/payments/manual", headers=pg["resident"],
                       json=base).status_code == 400                    # UTR is mandatory
    assert client.post(f"{API}/me/payments/manual", headers=pg["resident"],
                       json={**base, "utr": "12345"}).status_code == 400   # not 12 digits
    r = client.post(f"{API}/me/payments/manual", headers=pg["resident"],
                    json={**base, "utr": "4123 5678 9012"})
    assert r.status_code == 201, r.text
    assert r.json()["data"]["status"] == "PENDING"

    detail = client.get(f"{API}/invoices/{inv['id']}", headers=pg["owner"]).json()["data"]
    assert detail["balance"] == 9000                    # a claim does not move the balance
    dup = client.post(f"{API}/me/payments/manual", headers=pg["resident"],
                      json={**base, "amount": 1, "utr": "412356789012"})
    assert dup.status_code == 409

    pay = client.get(f"{API}/payments", headers=pg["owner"]).json()["data"][0]
    assert pay["source"] == "resident" and pay["reference"] == "412356789012"
    client.post(f"{API}/payments/{pay['id']}/verify", headers=pg["owner"],
                json={"approved": True})
    detail = client.get(f"{API}/invoices/{inv['id']}", headers=pg["owner"]).json()["data"]
    assert detail["balance"] == 0 and detail["status"] == "PAID"


def test_razorpay_payment_is_recorded_only_with_a_valid_signature(client, pg, monkeypatch):
    configure_payments(client, pg)
    calls = []
    monkeypatch.setattr(gateway, "razorpay_request",
                        lambda *a, **k: calls.append(a) or {"id": "order_TEST123"})
    inv = raise_invoice(client, pg, [("RENT", "Rent", 9000)])

    r = client.post(f"{API}/me/payments/razorpay/order", headers=pg["resident"],
                    json={"invoice_id": inv["id"]})
    assert r.status_code == 200, r.text
    order = r.json()["data"]
    assert order["order_id"] == "order_TEST123" and order["amount_paise"] == 900000
    assert calls[0][2] == "rzp_test_ABC123" and calls[0][3] == "key-secret-xyz"

    forged = client.post(f"{API}/me/payments/razorpay/verify", headers=pg["resident"], json={
        "razorpay_order_id": "order_TEST123", "razorpay_payment_id": "pay_ABC",
        "razorpay_signature": "0" * 64})
    assert forged.status_code == 409

    good = hmac.new(b"key-secret-xyz", b"order_TEST123|pay_ABC", hashlib.sha256).hexdigest()
    body = {"razorpay_order_id": "order_TEST123", "razorpay_payment_id": "pay_ABC",
            "razorpay_signature": good}
    first = client.post(f"{API}/me/payments/razorpay/verify", headers=pg["resident"], json=body)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["status"] == "VERIFIED"
    second = client.post(f"{API}/me/payments/razorpay/verify", headers=pg["resident"], json=body)
    assert second.json()["data"]["payment_number"] == first.json()["data"]["payment_number"]

    detail = client.get(f"{API}/invoices/{inv['id']}", headers=pg["owner"]).json()["data"]
    assert detail["status"] == "PAID" and len(detail["payments"]) == 1


def test_razorpay_webhook_completes_an_order_and_refuses_a_bad_signature(client, pg,
                                                                        monkeypatch):
    configure_payments(client, pg)
    monkeypatch.setattr(gateway, "razorpay_request", lambda *a, **k: {"id": "order_HOOK1"})
    inv = raise_invoice(client, pg, [("RENT", "Rent", 9000)])
    client.post(f"{API}/me/payments/razorpay/order", headers=pg["resident"],
                json={"invoice_id": inv["id"]})
    raw = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_HOOK1", "order_id": "order_HOOK1", "amount": 900000}}}}).encode()
    url = f"{API}/payments/razorpay/webhook/{pg['org'].id}"

    bad = client.post(url, content=raw, headers={"X-Razorpay-Signature": "nope"})
    assert bad.status_code == 403
    sig = hmac.new(b"hook-secret-xyz", raw, hashlib.sha256).hexdigest()
    ok = client.post(url, content=raw, headers={"X-Razorpay-Signature": sig})
    assert ok.status_code == 200 and ok.json()["data"]["handled"] is True
    again = client.post(url, content=raw, headers={"X-Razorpay-Signature": sig})
    assert again.json()["data"]["payment_number"] == ok.json()["data"]["payment_number"]


# ---------------------------------------------------------------------- P&L
def test_profit_and_loss_keeps_deposits_out_of_profit(client, pg):
    inv = raise_invoice(client, pg, [("RENT", "Rent", 9000), ("DEPOSIT", "Deposit", 18000)])
    r = client.post(f"{API}/payments", headers=pg["owner"], json={
        "resident_id": str(pg["me"].id), "invoice_id": inv["id"], "amount": 27000,
        "method": "CASH", "auto_verify": True})
    assert r.status_code == 201, r.text
    client.post(f"{API}/expenses", headers=pg["owner"], json={
        "branch_id": str(pg["branch"].id), "category": "Electricity", "amount": 2000})

    pnl = client.get(f"{API}/accounts/pnl", headers=pg["owner"]).json()["data"]
    assert pnl["income"]["total"] == 9000
    assert pnl["not_in_profit"]["deposits_collected"] == 18000
    assert pnl["expenses"]["total"] == 2000
    assert pnl["net_profit"] == 7000
    assert len(pnl["trend"]) == 6
    csv = client.get(f"{API}/accounts/pnl/export", headers=pg["owner"])
    assert csv.status_code == 200 and "Net profit" in csv.text


# ------------------------------------------------------------------- gate
def test_the_gate_desk_can_show_the_gate_code(client, pg):
    rows = client.get(f"{API}/scan/gate-codes", headers=pg["owner"]).json()["data"]
    assert [b["name"] for b in rows] == ["Koramangala"]
    assert client.get(f"{API}/scan/gate-codes", headers=pg["rival"]).json()["data"][0][
        "name"] == "Indiranagar"
