"""
Concurrency.

Every other test in this suite runs inside one transaction on one connection,
which is fast but cannot observe a race: two operations on the same session are
serialised by definition. These tests therefore open real connections and run
real threads, and they commit — so they manage their own cleanup rather than
relying on the fixture rollback.

What is being proved is narrow and specific: when N callers reach for the same
scarce thing at once, exactly the right number succeed. Not "it usually works".

If these look slow, that is the point. A race that only appears under genuine
parallelism cannot be caught by a test that fakes it.
"""
import threading
import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.dependencies import CurrentScope
from app.models import (
    Bed, Branch, Customer, InventoryItem, LaundryRequest, LaundrySlot,
    Organization, Role, User,
)
from app.models.enums import BedStatus, CustomerStatus
from tests.conftest import TEST_URL
from tests.factories import (
    make_branch, make_org, make_property, make_role, make_user,
)

# A separate engine: these tests need real, independently committed connections.
concurrent_engine = create_engine(TEST_URL, pool_size=12, max_overflow=8)
ConcurrentSession = sessionmaker(bind=concurrent_engine, autoflush=False,
                                 expire_on_commit=False)


@pytest.fixture
def committed_world():
    """
    A committed fixture, torn down by hand.

    The usual `db` fixture rolls back, but rolled-back rows are invisible to the
    other connections these tests need, so this one commits and then deletes.
    """
    setup = ConcurrentSession()
    org = make_org(setup, f"Race PG {uuid.uuid4().hex[:6]}")
    branch = make_branch(setup, org, "Koramangala", f"K{uuid.uuid4().hex[:4]}")
    prop = make_property(setup, org, branch, beds=1, rent=9000)
    role = make_role(setup, org, "Owner", ["*"], all_branches=True, is_system=True)
    owner = make_user(setup, org, f"owner-{uuid.uuid4().hex[:6]}@race.test", role=role)
    setup.commit()

    ids = dict(org_id=org.id, branch_id=branch.id, owner_id=owner.id,
               bed_id=prop["beds"][0].id, room_id=prop["room"].id)
    setup.close()

    yield ids

    # Teardown, children first.
    cleanup = ConcurrentSession()
    try:
        cleanup.query(LaundryRequest).filter_by(organization_id=ids["org_id"]).delete()
        cleanup.query(LaundrySlot).filter_by(organization_id=ids["org_id"]).delete()
        cleanup.query(InventoryItem).filter_by(organization_id=ids["org_id"]).delete()
        cleanup.execute(
            Bed.__table__.update()
            .where(Bed.organization_id == ids["org_id"])
            .values(current_customer_id=None, status=BedStatus.AVAILABLE))
        cleanup.query(Customer).filter_by(organization_id=ids["org_id"]).delete()
        cleanup.commit()
    finally:
        cleanup.close()


def scope_for(session, user_id) -> CurrentScope:
    """Build the request scope a handler would receive, on this session."""
    user = session.get(User, user_id)
    branch_ids = list(session.scalars(
        select(Branch.id).where(Branch.organization_id == user.organization_id)).all())
    return CurrentScope(
        user=user, organization_id=user.organization_id, branch_ids=branch_ids,
        permissions=user.permission_codes, is_master=False, all_branches=True)


def run_in_parallel(worker, count: int) -> list:
    """
    Fire `count` threads at once and collect (ok, detail) from each.

    A barrier is used rather than plain thread starts so they contend at the
    same instant; staggered starts would let each finish before the next began
    and quietly prove nothing.
    """
    barrier = threading.Barrier(count)
    results: list = []
    lock = threading.Lock()

    def wrapped(index: int):
        session = ConcurrentSession()
        try:
            barrier.wait(timeout=10)
            outcome = worker(session, index)
            with lock:
                results.append((True, outcome))
        except Exception as exc:                       # noqa: BLE001 - recorded
            session.rollback()
            with lock:
                results.append((False, f"{type(exc).__name__}: {exc}"))
        finally:
            session.close()

    threads = [threading.Thread(target=wrapped, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


# ------------------------------------------------------- bed assignment
def test_only_one_of_five_residents_gets_the_last_bed(committed_world):
    """
    The race the row lock exists for.

    Without SELECT ... FOR UPDATE all five read the bed as AVAILABLE and all five
    write their resident to it. The database CHECK would not catch that: a bed
    with one occupant pointer is perfectly consistent — it is just the wrong
    occupant for four of the five people who think they live there.
    """
    from app.services.resident_service import ResidentService

    ids = committed_world
    setup = ConcurrentSession()
    residents = []
    for i in range(5):
        c = Customer(organization_id=ids["org_id"], branch_id=ids["branch_id"],
                     full_name=f"Racer {i}", phone=f"+9198000000{i:02d}",
                     status=CustomerStatus.BOOKED, monthly_rent=9000)
        setup.add(c)
        residents.append(c)
    setup.commit()
    resident_ids = [c.id for c in residents]
    setup.close()

    def worker(session, index):
        service = ResidentService(session, scope_for(session, ids["owner_id"]))
        service.assign_bed(resident_ids[index], ids["bed_id"])
        session.commit()
        return resident_ids[index]

    results = run_in_parallel(worker, 5)
    winners = [detail for ok, detail in results if ok]
    assert len(winners) == 1, f"{len(winners)} residents were given the same bed: {results}"

    check = ConcurrentSession()
    try:
        bed = check.get(Bed, ids["bed_id"])
        assert bed.status == BedStatus.OCCUPIED
        assert bed.current_customer_id == winners[0]
        placed = check.scalars(
            select(Customer).where(Customer.bed_id == ids["bed_id"])).all()
        assert len(placed) == 1, "two residents point at the same bed"
    finally:
        check.close()


# ---------------------------------------------------------- laundry slot
def test_a_laundry_slot_never_exceeds_its_capacity(committed_world):
    """Two places, six people, all booking at once."""
    from app.services.operations_service import OperationsService

    ids = committed_world
    setup = ConcurrentSession()
    slot = LaundrySlot(
        organization_id=ids["org_id"], branch_id=ids["branch_id"],
        on_date=date.today() + timedelta(days=1),
        start_time=time(9, 0), end_time=time(10, 0), capacity=2)
    setup.add(slot)

    residents = []
    for i in range(6):
        c = Customer(organization_id=ids["org_id"], branch_id=ids["branch_id"],
                     full_name=f"Washer {i}", phone=f"+9198111100{i:02d}",
                     status=CustomerStatus.ACTIVE, monthly_rent=9000)
        setup.add(c)
        residents.append(c)
    setup.commit()
    slot_id = slot.id
    resident_ids = [c.id for c in residents]
    setup.close()

    def worker(session, index):
        service = OperationsService(session, scope_for(session, ids["owner_id"]))
        service.book_slot({"resident_id": resident_ids[index], "slot_id": slot_id,
                           "item_count": 3})
        session.commit()
        return resident_ids[index]

    results = run_in_parallel(worker, 6)
    booked = [d for ok, d in results if ok]
    assert len(booked) == 2, f"capacity 2 but {len(booked)} bookings landed: {results}"

    check = ConcurrentSession()
    try:
        rows = check.scalars(
            select(LaundryRequest).where(LaundryRequest.slot_id == slot_id)).all()
        assert len(rows) == 2
    finally:
        check.close()


def test_the_same_resident_cannot_double_book_one_slot(committed_world):
    from app.services.operations_service import OperationsService

    ids = committed_world
    setup = ConcurrentSession()
    slot = LaundrySlot(
        organization_id=ids["org_id"], branch_id=ids["branch_id"],
        on_date=date.today() + timedelta(days=2),
        start_time=time(11, 0), end_time=time(12, 0), capacity=5)
    setup.add(slot)
    resident = Customer(organization_id=ids["org_id"], branch_id=ids["branch_id"],
                        full_name="Eager Washer", phone="+919822220000",
                        status=CustomerStatus.ACTIVE, monthly_rent=9000)
    setup.add(resident)
    setup.commit()
    slot_id, resident_id = slot.id, resident.id
    setup.close()

    def worker(session, index):
        service = OperationsService(session, scope_for(session, ids["owner_id"]))
        service.book_slot({"resident_id": resident_id, "slot_id": slot_id,
                           "item_count": 1})
        session.commit()
        return index

    results = run_in_parallel(worker, 4)
    assert len([1 for ok, _ in results if ok]) == 1, f"double booking landed: {results}"


# ------------------------------------------------------ inventory stock
def test_parallel_withdrawals_cannot_drive_stock_negative(committed_world):
    """
    Ten callers each take 2 from a stock of 10. All ten may succeed, but the
    total must be exactly 10 - a lost update would leave stock above zero having
    handed out more than existed.
    """
    from app.services.support_service import SupportService

    ids = committed_world
    setup = ConcurrentSession()
    item = InventoryItem(
        organization_id=ids["org_id"], branch_id=ids["branch_id"],
        sku=f"LIN-{uuid.uuid4().hex[:6].upper()}",
        name="Bedsheets", category="Linen", unit="piece",
        quantity=10, minimum_stock=2)
    setup.add(item)
    setup.commit()
    item_id = item.id
    setup.close()

    def worker(session, index):
        service = SupportService(session, scope_for(session, ids["owner_id"]))
        service.adjust_stock(item_id, {"txn_type": "STOCK_OUT", "quantity": 2,
                                       "reason": "Issued to room"})
        session.commit()
        return index

    results = run_in_parallel(worker, 10)
    succeeded = len([1 for ok, _ in results if ok])

    check = ConcurrentSession()
    try:
        item = check.get(InventoryItem, item_id)
        assert item.quantity >= 0, "stock went negative"
        assert item.quantity == 10 - (succeeded * 2), (
            f"lost update: {succeeded} withdrawals of 2 from 10 left {item.quantity}")
        assert succeeded <= 5, f"{succeeded} withdrawals of 2 succeeded against stock of 10"
    finally:
        check.close()
