"""
Check-in: the workflow that moves a resident onto a bed and bills them.

These drive the HTTP endpoint rather than the service, because the thing worth
proving is what an authenticated caller can and cannot make the system do -
including a caller who sends a bed id belonging to somebody else.

The atomicity test is the important one. Check-in writes three things (bed
status, resident placement, first invoice); if any of them can land without the
others, the desk ends up with an occupied bed nobody is billed for.
"""
from datetime import date, timedelta

import pytest

from app.models import Bed, Customer, Invoice
from app.models.enums import BedStatus, CustomerStatus, InvoiceStatus
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
def world(db, client):
    """One tenant with a receptionist who can check people in, and a second tenant."""
    org = make_org(db, "Sunrise PG")
    other = make_org(db, "Rival PG")

    branch = make_branch(db, org, "Koramangala", "KOR")
    other_branch = make_branch(db, other, "Indiranagar", "IND")

    prop = make_property(db, org, branch, beds=3, rent=9000)
    other_prop = make_property(db, other, other_branch, beds=1, rent=8000)

    owner_role = make_role(db, org, "Owner", ["*"], all_branches=True, is_system=True)
    owner = make_user(db, org, "owner@sunrise.test", role=owner_role)

    # No customers.assign_bed / beds.assign - used to prove the guard bites.
    viewer_role = make_role(db, org, "Viewer", ["dashboard.view", "customers.view"])
    viewer = make_user(db, org, "viewer@sunrise.test", role=viewer_role, branches=[branch])

    resident = make_customer(db, org, "arjun@sunrise.test", branch=branch,
                             status=CustomerStatus.BOOKED)
    db.commit()

    return dict(org=org, other=other, branch=branch, other_branch=other_branch,
                room=prop["room"], beds=prop["beds"], other_bed=other_prop["beds"][0],
                owner=owner, viewer=viewer, resident=resident,
                owner_token=login(client, "owner@sunrise.test"),
                viewer_token=login(client, "viewer@sunrise.test"))


def check_in(client, token, resident_id, bed_id, **overrides):
    body = {"bed_id": str(bed_id), "monthly_rent": 9000,
            "security_deposit": 18000, "meal_plan": "Two meals",
            "raise_invoice": True, "food_charge": 2400}
    body.update(overrides)
    return client.post(f"{API}/residents/{resident_id}/check-in",
                       json=body, headers=auth(token))


# ------------------------------------------------------------- happy path
def test_check_in_places_the_resident_and_raises_one_invoice(db, client, world):
    bed = world["beds"][0]
    r = check_in(client, world["owner_token"], world["resident"].id, bed.id,
                 joining_date=date.today().isoformat())
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data["bed_id"] == str(bed.id)
    assert data["status"] == CustomerStatus.ACTIVE
    assert data["placement"]["room"] == world["room"].room_number

    db.expire_all()
    assert db.get(Bed, bed.id).status == BedStatus.OCCUPIED
    assert db.get(Bed, bed.id).current_customer_id == world["resident"].id

    invoices = db.query(Invoice).filter(
        Invoice.resident_id == world["resident"].id).all()
    assert len(invoices) == 1
    # rent + food + deposit, and nothing paid yet.
    assert float(invoices[0].total) == pytest.approx(9000 + 2400 + 18000)
    assert invoices[0].status == InvoiceStatus.PENDING
    assert data["invoice"]["invoice_number"] == invoices[0].invoice_number


def test_stay_terms_are_persisted_not_dropped(db, client, world):
    check_in(client, world["owner_token"], world["resident"].id, world["beds"][0].id,
             meal_plan="All meals", billing_cycle="QUARTERLY", rent_due_day=10)
    db.expire_all()
    resident = db.get(Customer, world["resident"].id)
    assert resident.meal_plan == "All meals"
    assert resident.billing_cycle == "QUARTERLY"
    assert resident.rent_due_day == 10


def test_check_in_without_an_invoice_still_places_the_resident(db, client, world):
    r = check_in(client, world["owner_token"], world["resident"].id,
                 world["beds"][0].id, raise_invoice=False)
    assert r.status_code == 200
    assert r.json()["data"]["invoice"] is None
    assert db.query(Invoice).filter(
        Invoice.resident_id == world["resident"].id).count() == 0


def test_a_gate_qr_is_issued_on_check_in(db, client, world):
    assert db.get(Customer, world["resident"].id).qr_token is None
    check_in(client, world["owner_token"], world["resident"].id, world["beds"][0].id)
    db.expire_all()
    assert db.get(Customer, world["resident"].id).qr_token


# ------------------------------------------------------------- conflicts
def test_an_occupied_bed_cannot_be_taken_twice(db, client, world):
    bed = world["beds"][0]
    first = make_customer(db, world["org"], "first@sunrise.test",
                          branch=world["branch"], status=CustomerStatus.BOOKED)
    db.commit()

    assert check_in(client, world["owner_token"], first.id, bed.id).status_code == 200
    second = check_in(client, world["owner_token"], world["resident"].id, bed.id)
    assert second.status_code == 409, second.text

    db.expire_all()
    assert db.get(Bed, bed.id).current_customer_id == first.id
    # The loser of the race is billed for nothing.
    assert db.query(Invoice).filter(
        Invoice.resident_id == world["resident"].id).count() == 0


@pytest.mark.parametrize("status", [BedStatus.MAINTENANCE, BedStatus.BLOCKED])
def test_an_out_of_service_bed_is_refused(db, client, world, status):
    bed = world["beds"][1]
    bed.status = status
    db.commit()
    r = check_in(client, world["owner_token"], world["resident"].id, bed.id)
    assert r.status_code == 409
    assert db.query(Invoice).filter(
        Invoice.resident_id == world["resident"].id).count() == 0


def test_checking_in_twice_is_refused(db, client, world):
    assert check_in(client, world["owner_token"], world["resident"].id,
                    world["beds"][0].id).status_code == 200
    again = check_in(client, world["owner_token"], world["resident"].id,
                     world["beds"][1].id)
    assert again.status_code == 409
    db.expire_all()
    assert db.get(Bed, world["beds"][1].id).status == BedStatus.AVAILABLE


def test_a_checked_out_resident_cannot_be_checked_in_again(db, client, world):
    world["resident"].status = CustomerStatus.CHECKED_OUT
    db.commit()
    r = check_in(client, world["owner_token"], world["resident"].id, world["beds"][0].id)
    assert r.status_code == 409


# ------------------------------------------------------------ atomicity
def test_a_failed_invoice_leaves_the_bed_free(db, client, world, monkeypatch):
    """
    If the invoice cannot be written, the bed must not stay taken.

    Without a single transaction this is exactly the state that costs money: the
    bed reads as occupied, so nobody else is put in it, and no invoice exists, so
    nobody is billed for it.

    The work happens inside a SAVEPOINT because the whole test session is already
    wrapped in a transaction the fixture rolls back at the end - a plain
    `rollback()` here would discard the fixture data too and prove nothing. The
    savepoint reproduces the real boundary: the endpoint commits only after the
    service returns, so a service that raises must leave no trace.
    """
    from app.services import billing_service

    def explode(self, data):
        raise RuntimeError("invoice generation failed")

    monkeypatch.setattr(billing_service.BillingService, "create_invoice", explode)

    bed = world["beds"][0]
    savepoint = db.begin_nested()

    with pytest.raises(RuntimeError):
        check_in(client, world["owner_token"], world["resident"].id, bed.id)

    savepoint.rollback()
    db.expire_all()

    assert db.get(Bed, bed.id).status == BedStatus.AVAILABLE
    assert db.get(Bed, bed.id).current_customer_id is None
    assert db.get(Customer, world["resident"].id).bed_id is None
    assert db.query(Invoice).filter(
        Invoice.resident_id == world["resident"].id).count() == 0


# -------------------------------------------------------- authorisation
def test_a_role_without_the_permission_is_refused(db, client, world):
    r = check_in(client, world["viewer_token"], world["resident"].id,
                 world["beds"][0].id)
    assert r.status_code == 403
    db.expire_all()
    assert db.get(Bed, world["beds"][0].id).status == BedStatus.AVAILABLE


def test_another_tenants_bed_is_not_reachable(db, client, world):
    """The bed id is real - it just belongs to somebody else."""
    r = check_in(client, world["owner_token"], world["resident"].id,
                 world["other_bed"].id)
    assert r.status_code in (403, 404), r.text
    db.expire_all()
    assert db.get(Bed, world["other_bed"].id).status == BedStatus.AVAILABLE


def test_a_branch_the_user_is_not_assigned_to_is_refused(db, client, world):
    """Same tenant, different branch, no assignment."""
    far = make_branch(db, world["org"], "Whitefield", "WHF")
    far_prop = make_property(db, world["org"], far, beds=1)
    role = make_role(db, world["org"], "Desk", ["customers.view", "customers.assign_bed"])
    make_user(db, world["org"], "desk@sunrise.test", role=role,
              branches=[world["branch"]])
    db.commit()

    token = login(client, "desk@sunrise.test")
    r = check_in(client, token, world["resident"].id, far_prop["beds"][0].id)
    assert r.status_code in (403, 404), r.text


def test_anonymous_callers_are_rejected(client, world):
    r = client.post(f"{API}/residents/{world['resident'].id}/check-in",
                    json={"bed_id": str(world["beds"][0].id), "monthly_rent": 9000})
    assert r.status_code == 401


# ------------------------------------------------------------ validation
@pytest.mark.parametrize("rent", [0, -1])
def test_rent_must_be_positive(client, world, rent):
    """
    A resident checked in at zero rent bills nothing every month afterwards,
    which nobody notices until the month closes.
    """
    r = check_in(client, world["owner_token"], world["resident"].id,
                 world["beds"][0].id, monthly_rent=rent)
    assert r.status_code == 422


def test_a_negative_deposit_is_refused(client, world):
    r = check_in(client, world["owner_token"], world["resident"].id,
                 world["beds"][0].id, security_deposit=-500)
    assert r.status_code == 422


def test_an_out_of_range_due_day_is_refused(client, world):
    r = check_in(client, world["owner_token"], world["resident"].id,
                 world["beds"][0].id, rent_due_day=31)
    assert r.status_code == 422


def test_a_nonexistent_bed_is_not_found(client, world):
    import uuid
    r = check_in(client, world["owner_token"], world["resident"].id, uuid.uuid4())
    assert r.status_code == 404


# ------------------------------------------------- reserved-bed visibility
def test_a_bed_reserved_for_this_resident_is_offered_to_them(db, client, world):
    """
    Reserving a bed takes it out of AVAILABLE. Without the `for_resident`
    widening, the one bed guaranteed to this resident would be the one bed
    missing from their list.
    """
    bed = world["beds"][0]
    reserve = client.post(
        f"{API}/residents/{world['resident'].id}/reserve-bed",
        json={"bed_id": str(bed.id)}, headers=auth(world["owner_token"]))
    assert reserve.status_code == 200, reserve.text

    plain = client.get(f"{API}/residents/available-beds",
                       headers=auth(world["owner_token"])).json()["data"]
    assert str(bed.id) not in {b["id"] for b in plain}

    widened = client.get(
        f"{API}/residents/available-beds",
        params={"for_resident": str(world["resident"].id)},
        headers=auth(world["owner_token"])).json()["data"]
    held = [b for b in widened if b["id"] == str(bed.id)]
    assert held and held[0]["reserved_for_this_resident"] is True


def test_a_reserved_bed_is_not_offered_to_a_different_resident(db, client, world):
    bed = world["beds"][0]
    client.post(f"{API}/residents/{world['resident'].id}/reserve-bed",
                json={"bed_id": str(bed.id)}, headers=auth(world["owner_token"]))
    someone_else = make_customer(db, world["org"], "other@sunrise.test",
                                 branch=world["branch"], status=CustomerStatus.BOOKED)
    db.commit()

    rows = client.get(f"{API}/residents/available-beds",
                      params={"for_resident": str(someone_else.id)},
                      headers=auth(world["owner_token"])).json()["data"]
    assert str(bed.id) not in {b["id"] for b in rows}
