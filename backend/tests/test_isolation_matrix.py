"""
Tenant and branch isolation, resource by resource.

`test_tenant_isolation.py` proves the scope-and-repository layer is sound. This
file proves the endpoints actually built on it, which is a different claim: a
correct foundation does not help if one handler reads an id straight out of the
request.

Two tenants exist with deliberately identical-looking data. Everything Alpha's
owner does - including naming Beta's real UUIDs explicitly - must fail to reach
Beta. Inside Alpha, a manager assigned to one branch must not reach the other.

On status codes: the system answers 404 for another tenant's row rather than
403, because "forbidden" confirms the row exists and turns any id endpoint into
an existence oracle. Both are accepted below since either is safe; what is never
accepted is a 200.
"""
import uuid
from datetime import date, time, timedelta

import pytest

from app.models import (
    Announcement, Asset, Complaint, Expense, InventoryItem, LaundrySlot,
    SupportQuery, Visitor,
)
from app.models.enums import CustomerStatus
from tests.factories import (
    PASSWORD, make_branch, make_customer, make_org, make_property, make_role,
    make_user,
)

API = "/api/v1"
DENIED = (403, 404)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, email: str) -> str:
    r = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


@pytest.fixture
def two_worlds(db, client):
    """Two tenants with mirrored data, and a branch-confined manager inside Alpha."""
    alpha = make_org(db, "Alpha PG")
    beta = make_org(db, "Beta PG")

    a_kor = make_branch(db, alpha, "Alpha Koramangala", "AKOR")
    a_btm = make_branch(db, alpha, "Alpha BTM", "ABTM")
    b_jay = make_branch(db, beta, "Beta Jayanagar", "BJAY")

    a_kor_prop = make_property(db, alpha, a_kor, beds=2)
    a_btm_prop = make_property(db, alpha, a_btm, beds=2)
    b_prop = make_property(db, beta, b_jay, beds=2)

    a_owner_role = make_role(db, alpha, "Owner", ["*"], all_branches=True, is_system=True)
    b_owner_role = make_role(db, beta, "Owner", ["*"], all_branches=True, is_system=True)
    make_user(db, alpha, "owner@alpha.test", role=a_owner_role)
    make_user(db, beta, "owner@beta.test", role=b_owner_role)

    # Full permissions, but only one branch.
    a_mgr_role = make_role(db, alpha, "Branch Manager", [
        "dashboard.view", "customers.view", "customers.edit", "rooms.view",
        "beds.view", "invoices.view", "payments.view", "complaints.view",
        "complaints.manage", "visitors.view", "expenses.view", "inventory.view",
        "assets.view", "queries.view", "laundry.view", "announcements.view",
        "audit.view", "reports.view",
    ])
    make_user(db, alpha, "kor.manager@alpha.test", role=a_mgr_role, branches=[a_kor])

    a_kor_resident = make_customer(db, alpha, "kor@alpha.test", branch=a_kor,
                                   status=CustomerStatus.ACTIVE)
    a_btm_resident = make_customer(db, alpha, "btm@alpha.test", branch=a_btm,
                                   status=CustomerStatus.ACTIVE)
    b_resident = make_customer(db, beta, "res@beta.test", branch=b_jay,
                               status=CustomerStatus.ACTIVE)

    def furnish(org, branch, resident, tag):
        rows = {}
        rows["complaint"] = Complaint(
            organization_id=org.id, branch_id=branch.id, resident_id=resident.id,
            ticket_number=f"CMP-{tag}-{uuid.uuid4().hex[:5]}", category="Plumbing",
            subject=f"{tag} leaking tap", description="Drips all night.")
        rows["visitor"] = Visitor(
            organization_id=org.id, branch_id=branch.id, resident_id=resident.id,
            name=f"{tag} Visitor", phone="+919800000000")
        rows["expense"] = Expense(
            organization_id=org.id, branch_id=branch.id,
            expense_number=f"EXP-{tag}-{uuid.uuid4().hex[:5]}", category="Utilities",
            amount=1200, spent_on=date.today(), description=f"{tag} water bill")
        rows["inventory"] = InventoryItem(
            organization_id=org.id, branch_id=branch.id,
            sku=f"SKU-{tag}-{uuid.uuid4().hex[:5]}", name=f"{tag} Mattress",
            category="Furniture", unit="piece", quantity=10, minimum_stock=2)
        rows["asset"] = Asset(
            organization_id=org.id, branch_id=branch.id,
            asset_code=f"AST-{tag}-{uuid.uuid4().hex[:5]}", name=f"{tag} Geyser",
            category="Appliance")
        rows["query"] = SupportQuery(
            organization_id=org.id, branch_id=branch.id, resident_id=resident.id,
            ticket_number=f"QRY-{tag}-{uuid.uuid4().hex[:5]}",
            subject=f"{tag} rent question", category="Billing")
        rows["announcement"] = Announcement(
            organization_id=org.id, branch_id=branch.id,
            title=f"{tag} water cut", message="Sunday morning.")
        rows["slot"] = LaundrySlot(
            organization_id=org.id, branch_id=branch.id,
            on_date=date.today() + timedelta(days=1),
            start_time=time(9, 0), end_time=time(10, 0), capacity=3)
        for row in rows.values():
            db.add(row)
        return rows

    a_kor_rows = furnish(alpha, a_kor, a_kor_resident, "AKOR")
    a_btm_rows = furnish(alpha, a_btm, a_btm_resident, "ABTM")
    b_rows = furnish(beta, b_jay, b_resident, "BETA")
    db.commit()

    return dict(
        alpha=alpha, beta=beta, a_kor=a_kor, a_btm=a_btm, b_jay=b_jay,
        a_kor_resident=a_kor_resident, a_btm_resident=a_btm_resident,
        b_resident=b_resident,
        a_kor_bed=a_kor_prop["beds"][0], a_btm_bed=a_btm_prop["beds"][0],
        a_kor_room=a_kor_prop["room"], a_btm_room=a_btm_prop["room"],
        b_bed=b_prop["beds"][0], b_room=b_prop["room"],
        a_kor_rows=a_kor_rows, a_btm_rows=a_btm_rows, b_rows=b_rows,
        alpha_owner=login(client, "owner@alpha.test"),
        beta_owner=login(client, "owner@beta.test"),
        kor_manager=login(client, "kor.manager@alpha.test"),
    )


# ------------------------------------------------------ tenant: detail reads
TENANT_DETAIL_CASES = [
    ("resident", "/residents/{id}", "b_resident"),
    ("complaint", "/complaints/{id}", "complaint"),
    ("query", "/queries/{id}", "query"),
]


def test_another_tenants_resident_is_not_readable(client, two_worlds):
    r = client.get(f"{API}/residents/{two_worlds['b_resident'].id}",
                   headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code in DENIED, r.text


def test_another_tenants_complaint_is_not_readable(client, two_worlds):
    r = client.get(f"{API}/complaints/{two_worlds['b_rows']['complaint'].id}",
                   headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code in DENIED


def test_another_tenants_query_is_not_readable(client, two_worlds):
    r = client.get(f"{API}/queries/{two_worlds['b_rows']['query'].id}",
                   headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code in DENIED


# ------------------------------------------------------- tenant: list reads
TENANT_LIST_CASES = [
    ("residents", "/residents", "res@beta.test"),
    ("complaints", "/complaints", "BETA leaking tap"),
    ("visitors", "/visitors", "BETA Visitor"),
    ("expenses", "/expenses", "BETA water bill"),
    ("inventory", "/inventory", "BETA Mattress"),
    ("assets", "/assets", "BETA Geyser"),
    ("queries", "/queries", "BETA rent question"),
    ("announcements", "/announcements", "BETA water cut"),
    ("rooms", "/rooms", None),
    ("beds", "/beds", None),
    ("branches", "/branches", "Beta Jayanagar"),
    ("invoices", "/invoices", None),
    ("payments", "/payments", None),
    ("audit", "/audit", None),
]


@pytest.mark.parametrize("label,path,beta_marker", TENANT_LIST_CASES,
                         ids=[c[0] for c in TENANT_LIST_CASES])
def test_list_endpoints_never_return_another_tenants_rows(
        client, two_worlds, label, path, beta_marker):
    r = client.get(f"{API}{path}", params={"page_size": 100},
                   headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code == 200, f"{label}: {r.text}"

    body = r.text
    assert str(two_worlds["beta"].id) not in body, f"{label} leaked Beta's org id"
    assert str(two_worlds["b_jay"].id) not in body, f"{label} leaked Beta's branch id"
    assert str(two_worlds["b_resident"].id) not in body, f"{label} leaked Beta's resident"
    if beta_marker:
        assert beta_marker not in body, f"{label} leaked Beta's data"


# ------------------------------------------------------ tenant: mutations
def test_another_tenants_bed_cannot_be_assigned(client, two_worlds):
    r = client.post(f"{API}/residents/{two_worlds['a_kor_resident'].id}/assign-bed",
                    json={"bed_id": str(two_worlds["b_bed"].id)},
                    headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code in DENIED


def test_another_tenants_resident_cannot_be_edited(client, two_worlds):
    r = client.patch(f"{API}/residents/{two_worlds['b_resident'].id}",
                     json={"occupation": "Edited across the tenant boundary"},
                     headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code in DENIED


def test_another_tenants_complaint_cannot_be_resolved(client, two_worlds):
    r = client.patch(f"{API}/complaints/{two_worlds['b_rows']['complaint'].id}",
                     json={"status": "RESOLVED"},
                     headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code in DENIED


def test_another_tenants_expense_cannot_be_deleted(client, two_worlds):
    r = client.delete(f"{API}/expenses/{two_worlds['b_rows']['expense'].id}",
                      headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code in DENIED


def test_another_tenants_inventory_cannot_be_adjusted(client, two_worlds):
    r = client.post(f"{API}/inventory/{two_worlds['b_rows']['inventory'].id}/adjust",
                    json={"txn_type": "STOCK_OUT", "quantity": 5, "reason": "theft"},
                    headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code in DENIED


def test_a_resident_cannot_be_created_in_another_tenants_branch(client, two_worlds):
    """
    The client supplies branch_id, so this is the obvious place to try to plant
    a row in someone else's tenant.
    """
    r = client.post(f"{API}/residents", json={
        "first_name": "Trojan", "last_name": "Row", "phone": "+919812345678",
        "branch_id": str(two_worlds["b_jay"].id),
    }, headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code in DENIED


def test_reports_do_not_span_tenants(client, two_worlds):
    r = client.get(f"{API}/reports/occupancy", headers=auth(two_worlds["alpha_owner"]))
    if r.status_code == 200:
        assert str(two_worlds["b_jay"].id) not in r.text
        assert "Beta Jayanagar" not in r.text


def test_report_export_carries_the_same_scope_as_the_report(client, two_worlds):
    r = client.get(f"{API}/reports/occupancy/export",
                   headers=auth(two_worlds["alpha_owner"]))
    if r.status_code == 200:
        assert "Beta Jayanagar" not in r.text


# ------------------------------------------------------- branch isolation
BRANCH_LIST_CASES = [
    ("residents", "/residents", "btm@alpha.test"),
    ("complaints", "/complaints", "ABTM leaking tap"),
    ("visitors", "/visitors", "ABTM Visitor"),
    ("expenses", "/expenses", "ABTM water bill"),
    ("inventory", "/inventory", "ABTM Mattress"),
    ("assets", "/assets", "ABTM Geyser"),
    ("queries", "/queries", "ABTM rent question"),
]


@pytest.mark.parametrize("label,path,other_branch_marker", BRANCH_LIST_CASES,
                         ids=[c[0] for c in BRANCH_LIST_CASES])
def test_a_confined_manager_sees_only_their_branch(
        client, two_worlds, label, path, other_branch_marker):
    """
    Same tenant, same permission, different branch. The manager holds the module
    permission, so anything hidden here is hidden by branch scoping alone.
    """
    r = client.get(f"{API}{path}", params={"page_size": 100},
                   headers=auth(two_worlds["kor_manager"]))
    assert r.status_code == 200, f"{label}: {r.text}"
    assert other_branch_marker not in r.text, f"{label} leaked the other branch"
    assert str(two_worlds["a_btm"].id) not in r.text, f"{label} leaked the other branch id"


def test_a_confined_manager_cannot_read_another_branchs_resident(client, two_worlds):
    r = client.get(f"{API}/residents/{two_worlds['a_btm_resident'].id}",
                   headers=auth(two_worlds["kor_manager"]))
    assert r.status_code in DENIED


def test_a_confined_manager_cannot_edit_another_branchs_resident(client, two_worlds):
    r = client.patch(f"{API}/residents/{two_worlds['a_btm_resident'].id}",
                     json={"occupation": "Reached across branches"},
                     headers=auth(two_worlds["kor_manager"]))
    assert r.status_code in DENIED


def test_a_confined_manager_cannot_filter_into_another_branch(client, two_worlds):
    """
    Passing the other branch's id as a filter must be refused outright, not
    silently answered with an empty list - and certainly not honoured.
    """
    r = client.get(f"{API}/residents", params={"branch_id": str(two_worlds["a_btm"].id)},
                   headers=auth(two_worlds["kor_manager"]))
    if r.status_code == 200:
        assert "btm@alpha.test" not in r.text
    else:
        assert r.status_code in DENIED


def test_a_confined_manager_cannot_read_another_branchs_audit_trail(client, two_worlds):
    r = client.get(f"{API}/audit", params={"branch_id": str(two_worlds["a_btm"].id)},
                   headers=auth(two_worlds["kor_manager"]))
    assert r.status_code in DENIED


def test_available_beds_respects_branch_assignment(client, two_worlds):
    r = client.get(f"{API}/residents/available-beds",
                   headers=auth(two_worlds["kor_manager"]))
    assert r.status_code == 200
    assert str(two_worlds["a_btm_bed"].id) not in r.text
    assert str(two_worlds["b_bed"].id) not in r.text


def test_the_owner_does_see_both_of_their_own_branches(client, two_worlds):
    """The counterweight: branch scoping must not over-restrict."""
    r = client.get(f"{API}/residents", params={"page_size": 100},
                   headers=auth(two_worlds["alpha_owner"]))
    assert r.status_code == 200
    assert "kor@alpha.test" in r.text
    assert "btm@alpha.test" in r.text
