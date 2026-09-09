"""
Business workflows, end to end through the API.

Each test walks a whole real-world sequence rather than one endpoint, because
the interesting failures live between the steps: a bed freed on checkout but a
resident left ACTIVE, a payment that verifies without moving the invoice
balance, a transfer that releases the old bed and then fails to take the new one.

Every step is asserted for its effect on state, not merely for a 200. A workflow
test that only checks status codes proves the endpoints answered, not that the
business actually happened.
"""
import uuid
from datetime import date, datetime, time, timedelta

import pytest

from app.models import (
    Bed, Complaint, Customer, GatePass, Invoice, LaundryRequest, LaundrySlot,
    Payment, Visitor,
)
from app.models.enums import (
    BedStatus, ComplaintStatus, CustomerStatus, InvoiceStatus, PaymentStatus,
    VisitorStatus,
)
from tests.factories import (
    PASSWORD, make_branch, make_customer, make_org, make_property, make_role,
    make_user,
)

API = "/api/v1"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, email: str) -> str:
    r = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


@pytest.fixture
def flow(db, client):
    """An owner, a receptionist who cannot verify money, and a furnished branch."""
    org = make_org(db, "Workflow PG")
    branch = make_branch(db, org, "Koramangala", "KOR")
    prop = make_property(db, org, branch, beds=4, rent=9000)

    owner_role = make_role(db, org, "Owner", ["*"], all_branches=True, is_system=True)
    make_user(db, org, "owner@flow.test", role=owner_role)

    # Can take money but not confirm it - the separation the approval flow needs.
    desk_role = make_role(db, org, "Receptionist", [
        "dashboard.view", "customers.view", "customers.create", "invoices.view",
        "payments.view", "payments.create", "visitors.view", "visitors.create",
        "complaints.view", "complaints.create",
    ])
    make_user(db, org, "desk@flow.test", role=desk_role, branches=[branch])

    resident = make_customer(db, org, "arjun@flow.test", branch=branch,
                             status=CustomerStatus.BOOKED)
    db.commit()

    return dict(org=org, branch=branch, beds=prop["beds"], room=prop["room"],
                resident=resident,
                owner=login(client, "owner@flow.test"),
                desk=login(client, "desk@flow.test"))


def _check_in(client, flow, resident_id, bed_id, **kw):
    body = {"bed_id": str(bed_id), "monthly_rent": 9000, "security_deposit": 18000,
            "raise_invoice": True, "meal_plan": "Two meals", "food_charge": 2400}
    body.update(kw)
    return client.post(f"{API}/residents/{resident_id}/check-in", json=body,
                       headers=auth(flow["owner"]))


# ------------------------------------------------- A: new resident, end to end
def test_workflow_new_resident_from_creation_to_paid_invoice(db, client, flow):
    """Create → check in → invoice raised → payment verified → invoice settled."""
    created = client.post(f"{API}/residents", json={
        "first_name": "Priya", "last_name": "Nair", "phone": "+919845000111",
        "branch_id": str(flow["branch"].id),
    }, headers=auth(flow["owner"]))
    assert created.status_code == 201, created.text
    resident_id = created.json()["data"]["id"]

    checked = _check_in(client, flow, resident_id, flow["beds"][0].id)
    assert checked.status_code == 200, checked.text
    invoice_id = checked.json()["data"]["invoice"]["id"]
    total = checked.json()["data"]["invoice"]["total"]

    paid = client.post(f"{API}/payments", json={
        "resident_id": resident_id, "invoice_id": invoice_id,
        "amount": total, "method": "UPI", "reference": "UPI-9931",
    }, headers=auth(flow["owner"]))
    assert paid.status_code in (200, 201), paid.text
    payment_id = paid.json()["data"]["id"]

    verified = client.post(f"{API}/payments/{payment_id}/verify",
                           json={"approved": True}, headers=auth(flow["owner"]))
    assert verified.status_code == 200, verified.text

    db.expire_all()
    invoice = db.get(Invoice, uuid.UUID(invoice_id))
    assert invoice.status == InvoiceStatus.PAID
    assert float(invoice.balance) == 0
    assert db.get(Customer, uuid.UUID(resident_id)).status == CustomerStatus.ACTIVE


# ------------------------------------------------------------- B: transfer
def test_workflow_transfer_releases_the_old_bed_and_takes_the_new_one(db, client, flow):
    old_bed, new_bed = flow["beds"][0], flow["beds"][1]
    _check_in(client, flow, flow["resident"].id, old_bed.id)

    r = client.post(f"{API}/residents/{flow['resident'].id}/transfer",
                    json={"bed_id": str(new_bed.id), "reason": "Requested a window bed"},
                    headers=auth(flow["owner"]))
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(Bed, old_bed.id).status == BedStatus.AVAILABLE
    assert db.get(Bed, old_bed.id).current_customer_id is None
    assert db.get(Bed, new_bed.id).status == BedStatus.OCCUPIED
    assert db.get(Bed, new_bed.id).current_customer_id == flow["resident"].id
    assert db.get(Customer, flow["resident"].id).bed_id == new_bed.id


def test_workflow_transfer_is_audited(db, client, flow):
    from app.models import AuditLog

    _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)
    client.post(f"{API}/residents/{flow['resident'].id}/transfer",
                json={"bed_id": str(flow["beds"][1].id), "reason": "Noise"},
                headers=auth(flow["owner"]))

    entries = db.query(AuditLog).filter(AuditLog.module == "Residents").all()
    assert any("transfer" in (e.description or "").lower()
               or e.action == "TRANSFER" for e in entries), \
        "a bed transfer left no audit trail"


def test_workflow_transfer_to_an_occupied_bed_is_refused(db, client, flow):
    other = make_customer(db, flow["org"], "other@flow.test", branch=flow["branch"],
                          status=CustomerStatus.BOOKED)
    db.commit()

    _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)
    _check_in(client, flow, other.id, flow["beds"][1].id)

    r = client.post(f"{API}/residents/{flow['resident'].id}/transfer",
                    json={"bed_id": str(flow["beds"][1].id)},
                    headers=auth(flow["owner"]))
    assert r.status_code == 409

    db.expire_all()
    assert db.get(Customer, flow["resident"].id).bed_id == flow["beds"][0].id


# ------------------------------------------------------------- C: checkout
def test_workflow_checkout_frees_the_bed_and_keeps_the_billing_history(db, client, flow):
    """
    The historical invoice must survive. A PG that loses what a departed resident
    owed cannot chase it, and cannot answer a dispute six months later.
    """
    bed = flow["beds"][0]
    checked = _check_in(client, flow, flow["resident"].id, bed.id)
    invoice_id = checked.json()["data"]["invoice"]["id"]

    r = client.post(f"{API}/residents/{flow['resident'].id}/checkout",
                    json={"checkout_date": date.today().isoformat(),
                          "notes": "Moved to Chennai"},
                    headers=auth(flow["owner"]))
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(Bed, bed.id).status == BedStatus.AVAILABLE
    assert db.get(Bed, bed.id).current_customer_id is None

    resident = db.get(Customer, flow["resident"].id)
    assert resident.status == CustomerStatus.CHECKED_OUT
    assert resident.bed_id is None
    assert resident.actual_checkout_date is not None

    invoice = db.get(Invoice, uuid.UUID(invoice_id))
    assert invoice is not None, "checkout destroyed the billing history"
    assert invoice.resident_id == flow["resident"].id


def test_workflow_the_freed_bed_can_take_the_next_resident(db, client, flow):
    bed = flow["beds"][0]
    _check_in(client, flow, flow["resident"].id, bed.id)
    client.post(f"{API}/residents/{flow['resident'].id}/checkout", json={},
                headers=auth(flow["owner"]))

    successor = make_customer(db, flow["org"], "next@flow.test", branch=flow["branch"],
                              status=CustomerStatus.BOOKED)
    db.commit()

    assert _check_in(client, flow, successor.id, bed.id).status_code == 200


# ------------------------------------------------- D: payment approval chain
def test_workflow_payment_needs_a_second_pair_of_eyes(db, client, flow):
    """
    The receptionist takes the cash; only someone with payments.verify confirms
    it. Until then the invoice balance must not move - otherwise recording a
    payment and confirming one are the same act and the control is decorative.
    """
    checked = _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)
    invoice_id = checked.json()["data"]["invoice"]["id"]

    taken = client.post(f"{API}/payments", json={
        "resident_id": str(flow["resident"].id), "invoice_id": invoice_id,
        "amount": 5000, "method": "CASH",
    }, headers=auth(flow["desk"]))
    assert taken.status_code in (200, 201), taken.text
    payment_id = taken.json()["data"]["id"]

    db.expire_all()
    payment = db.get(Payment, uuid.UUID(payment_id))
    assert payment.status == PaymentStatus.PENDING
    before = float(db.get(Invoice, uuid.UUID(invoice_id)).balance)

    # The receptionist cannot wave their own payment through.
    refused = client.post(f"{API}/payments/{payment_id}/verify",
                          json={"approved": True}, headers=auth(flow["desk"]))
    assert refused.status_code == 403
    db.expire_all()
    assert float(db.get(Invoice, uuid.UUID(invoice_id)).balance) == before

    approved = client.post(f"{API}/payments/{payment_id}/verify",
                           json={"approved": True}, headers=auth(flow["owner"]))
    assert approved.status_code == 200

    db.expire_all()
    assert db.get(Payment, uuid.UUID(payment_id)).status == PaymentStatus.VERIFIED
    assert float(db.get(Invoice, uuid.UUID(invoice_id)).balance) == before - 5000


def test_workflow_a_rejected_payment_does_not_touch_the_invoice(db, client, flow):
    checked = _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)
    invoice_id = checked.json()["data"]["invoice"]["id"]
    before = float(db.get(Invoice, uuid.UUID(invoice_id)).balance)

    taken = client.post(f"{API}/payments", json={
        "resident_id": str(flow["resident"].id), "invoice_id": invoice_id,
        "amount": 5000, "method": "CASH",
    }, headers=auth(flow["desk"]))
    payment_id = taken.json()["data"]["id"]

    client.post(f"{API}/payments/{payment_id}/verify",
                json={"approved": False, "note": "Cash never arrived"},
                headers=auth(flow["owner"]))

    db.expire_all()
    assert db.get(Payment, uuid.UUID(payment_id)).status == PaymentStatus.REJECTED
    assert float(db.get(Invoice, uuid.UUID(invoice_id)).balance) == before


def test_workflow_only_a_verified_payment_can_be_refunded(db, client, flow):
    checked = _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)
    invoice_id = checked.json()["data"]["invoice"]["id"]

    taken = client.post(f"{API}/payments", json={
        "resident_id": str(flow["resident"].id), "invoice_id": invoice_id,
        "amount": 3000, "method": "UPI",
    }, headers=auth(flow["desk"]))
    payment_id = taken.json()["data"]["id"]

    early = client.post(f"{API}/payments/{payment_id}/refund",
                        json={"reason": "Duplicate transfer"},
                        headers=auth(flow["owner"]))
    assert early.status_code == 409, "a pending payment was refunded"

    client.post(f"{API}/payments/{payment_id}/verify", json={"approved": True},
                headers=auth(flow["owner"]))
    refunded = client.post(f"{API}/payments/{payment_id}/refund",
                           json={"reason": "Duplicate transfer"},
                           headers=auth(flow["owner"]))
    assert refunded.status_code == 200, refunded.text

    db.expire_all()
    assert db.get(Payment, uuid.UUID(payment_id)).status == PaymentStatus.REFUNDED


# -------------------------------------------------------------- E: visitor
def test_workflow_visitor_request_approval_entry_and_exit(db, client, flow):
    _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)

    logged = client.post(f"{API}/visitors", json={
        "resident_id": str(flow["resident"].id), "name": "Ramesh Nair",
        "phone": "+919845222333", "relation": "Father", "purpose": "Weekend visit",
    }, headers=auth(flow["desk"]))
    assert logged.status_code == 201, logged.text
    visitor_id = logged.json()["data"]["id"]

    db.expire_all()
    assert db.get(Visitor, uuid.UUID(visitor_id)).status == VisitorStatus.PENDING

    # The receptionist may log a visitor but not approve one.
    assert client.post(f"{API}/visitors/{visitor_id}/decision",
                       json={"approved": True},
                       headers=auth(flow["desk"])).status_code == 403

    assert client.post(f"{API}/visitors/{visitor_id}/decision",
                       json={"approved": True},
                       headers=auth(flow["owner"])).status_code == 200

    assert client.post(f"{API}/visitors/{visitor_id}/entry",
                       headers=auth(flow["owner"])).status_code == 200
    db.expire_all()
    assert db.get(Visitor, uuid.UUID(visitor_id)).entry_at is not None

    assert client.post(f"{API}/visitors/{visitor_id}/exit",
                       headers=auth(flow["owner"])).status_code == 200
    db.expire_all()
    visitor = db.get(Visitor, uuid.UUID(visitor_id))
    assert visitor.exit_at is not None
    assert visitor.exit_at >= visitor.entry_at


def test_workflow_an_unapproved_visitor_cannot_enter(db, client, flow):
    _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)
    logged = client.post(f"{API}/visitors", json={
        "resident_id": str(flow["resident"].id), "name": "Unknown Caller",
    }, headers=auth(flow["desk"]))
    visitor_id = logged.json()["data"]["id"]

    r = client.post(f"{API}/visitors/{visitor_id}/entry", headers=auth(flow["owner"]))
    assert r.status_code == 409, "an unapproved visitor was let through the gate"


def test_workflow_a_rejected_visitor_cannot_enter(db, client, flow):
    _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)
    logged = client.post(f"{API}/visitors", json={
        "resident_id": str(flow["resident"].id), "name": "Turned Away",
    }, headers=auth(flow["desk"]))
    visitor_id = logged.json()["data"]["id"]

    client.post(f"{API}/visitors/{visitor_id}/decision",
                json={"approved": False, "note": "Resident not expecting anyone"},
                headers=auth(flow["owner"]))
    assert client.post(f"{API}/visitors/{visitor_id}/entry",
                       headers=auth(flow["owner"])).status_code == 409


# -------------------------------------------------------------- F: laundry
def test_workflow_laundry_booking_fills_and_then_refuses(db, client, flow):
    _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)
    second = make_customer(db, flow["org"], "second@flow.test", branch=flow["branch"],
                           status=CustomerStatus.ACTIVE)

    slot = LaundrySlot(organization_id=flow["org"].id, branch_id=flow["branch"].id,
                       on_date=date.today() + timedelta(days=1),
                       start_time=time(9, 0), end_time=time(10, 0), capacity=1)
    db.add(slot)
    db.commit()

    first = client.post(f"{API}/laundry/bookings", json={
        "resident_id": str(flow["resident"].id), "slot_id": str(slot.id),
        "item_count": 4,
    }, headers=auth(flow["owner"]))
    assert first.status_code == 201, first.text

    full = client.post(f"{API}/laundry/bookings", json={
        "resident_id": str(second.id), "slot_id": str(slot.id), "item_count": 2,
    }, headers=auth(flow["owner"]))
    assert full.status_code == 409, "capacity 1 accepted a second booking"

    db.expire_all()
    assert db.query(LaundryRequest).filter(
        LaundryRequest.slot_id == slot.id).count() == 1


def test_workflow_a_resident_cannot_book_the_same_slot_twice(db, client, flow):
    _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)
    slot = LaundrySlot(organization_id=flow["org"].id, branch_id=flow["branch"].id,
                       on_date=date.today() + timedelta(days=2),
                       start_time=time(14, 0), end_time=time(15, 0), capacity=5)
    db.add(slot)
    db.commit()

    body = {"resident_id": str(flow["resident"].id), "slot_id": str(slot.id),
            "item_count": 2}
    assert client.post(f"{API}/laundry/bookings", json=body,
                       headers=auth(flow["owner"])).status_code == 201
    assert client.post(f"{API}/laundry/bookings", json=body,
                       headers=auth(flow["owner"])).status_code == 409


# ------------------------------------------------------------ G: complaint
def test_workflow_complaint_from_raised_to_resolved(db, client, flow):
    _check_in(client, flow, flow["resident"].id, flow["beds"][0].id)

    raised = client.post(f"{API}/complaints", json={
        "resident_id": str(flow["resident"].id), "branch_id": str(flow["branch"].id),
        "category": "Plumbing", "subject": "Shower runs cold",
        "description": "No hot water after 7am.", "priority": "HIGH",
    }, headers=auth(flow["desk"]))
    assert raised.status_code == 201, raised.text
    complaint_id = raised.json()["data"]["id"]

    db.expire_all()
    complaint = db.get(Complaint, uuid.UUID(complaint_id))
    assert complaint.status == ComplaintStatus.OPEN
    assert complaint.ticket_number

    # The receptionist may raise one but not resolve it.
    assert client.patch(f"{API}/complaints/{complaint_id}",
                        json={"status": "RESOLVED"},
                        headers=auth(flow["desk"])).status_code == 403

    progressed = client.patch(f"{API}/complaints/{complaint_id}",
                              json={"status": "IN_PROGRESS"},
                              headers=auth(flow["owner"]))
    assert progressed.status_code == 200, progressed.text

    resolved = client.patch(f"{API}/complaints/{complaint_id}",
                            json={"status": "RESOLVED",
                                  "resolution": "Geyser thermostat replaced"},
                            headers=auth(flow["owner"]))
    assert resolved.status_code == 200, resolved.text

    db.expire_all()
    complaint = db.get(Complaint, uuid.UUID(complaint_id))
    assert complaint.status == ComplaintStatus.RESOLVED
    assert complaint.resolved_at is not None


def test_workflow_the_resident_sees_their_own_complaint_progress(db, client, flow):
    """The loop only closes if the person who complained can see the outcome."""
    resident = make_customer(db, flow["org"], "portal@flow.test", branch=flow["branch"],
                             status=CustomerStatus.ACTIVE)
    db.commit()
    resident_token = login(client, "portal@flow.test")

    raised = client.post(f"{API}/me/complaints", json={
        "category": "Electrical", "subject": "Fan not working",
        "description": "Bedroom fan is dead.",
    }, headers=auth(resident_token))
    assert raised.status_code == 201, raised.text
    complaint_id = raised.json()["data"]["id"]

    client.patch(f"{API}/complaints/{complaint_id}",
                 json={"status": "RESOLVED", "resolution": "Capacitor replaced"},
                 headers=auth(flow["owner"]))

    mine = client.get(f"{API}/me/complaints", headers=auth(resident_token))
    assert mine.status_code == 200
    rows = mine.json()["data"]
    match = [c for c in rows if c["id"] == complaint_id]
    assert match and match[0]["status"] == ComplaintStatus.RESOLVED
