"""
The RBAC matrix.

Five realistic roles are pointed at the same set of endpoints and every cell of
the grid is asserted - both that a role CAN reach what it should and that it
CANNOT reach what it should not. The second half is the half that matters: a
permission system that grants correctly but denies loosely is not a permission
system.

Roles are built from the permission catalogue rather than hardcoded, because the
brief is explicit that the system must stay dynamic - a PG that invents its own
role names must get the same enforcement. `test_a_custom_role_is_enforced_like_a_named_one`
proves the engine does not privilege the familiar names.

Every assertion here is made against the HTTP API. A service-level check would
prove the service is careful; only the endpoint proves the guard is actually
wired to the route the browser calls.
"""
import uuid

import pytest

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


# The permission sets a real PG hands out. Named for readability; the engine
# knows nothing about the names.
ROLE_PERMISSIONS = {
    "owner": ["*"],
    "manager": [
        "dashboard.view", "customers.view", "customers.create", "customers.edit",
        "customers.assign_bed", "customers.checkout", "beds.view", "rooms.view",
        "invoices.view", "payments.view", "payments.verify", "complaints.view",
        "complaints.manage", "visitors.view", "visitors.approve", "reports.view",
    ],
    "accountant": [
        "dashboard.view", "invoices.view", "invoices.create", "payments.view",
        "payments.create", "expenses.view", "expenses.create", "reports.view",
        "customers.view",
    ],
    "receptionist": [
        "dashboard.view", "customers.view", "customers.create", "visitors.view",
        "visitors.create", "complaints.view", "complaints.create", "beds.view",
    ],
    "security": [
        "dashboard.view", "scan.view", "scan.manage", "visitors.view",
        "visitors.create", "gatepass.view",
    ],
}


@pytest.fixture
def matrix(db, client):
    org = make_org(db, "Matrix PG")
    branch = make_branch(db, org, "Koramangala", "KOR")
    prop = make_property(db, org, branch, beds=2)

    tokens = {}
    for name, perms in ROLE_PERMISSIONS.items():
        role = make_role(db, org, name.title(), perms,
                         all_branches=(name == "owner"), is_system=(name == "owner"))
        make_user(db, org, f"{name}@matrix.test", role=role,
                  branches=None if name == "owner" else [branch])

    resident = make_customer(db, org, "resident@matrix.test", branch=branch)
    db.commit()

    for name in ROLE_PERMISSIONS:
        tokens[name] = login(client, f"{name}@matrix.test")

    return dict(org=org, branch=branch, resident=resident,
                bed=prop["beds"][0], room=prop["room"], tokens=tokens)


# --------------------------------------------------------------- read grid
#: (label, method, path builder) -> {role: expected_allowed}
READ_MATRIX = [
    ("residents", "/residents",
     {"owner": True, "manager": True, "accountant": True,
      "receptionist": True, "security": False}),
    ("invoices", "/invoices",
     {"owner": True, "manager": True, "accountant": True,
      "receptionist": False, "security": False}),
    ("payments", "/payments",
     {"owner": True, "manager": True, "accountant": True,
      "receptionist": False, "security": False}),
    ("expenses", "/expenses",
     {"owner": True, "manager": False, "accountant": True,
      "receptionist": False, "security": False}),
    ("complaints", "/complaints",
     {"owner": True, "manager": True, "accountant": False,
      "receptionist": True, "security": False}),
    ("visitors", "/visitors",
     {"owner": True, "manager": True, "accountant": False,
      "receptionist": True, "security": True}),
    ("roles", "/roles",
     {"owner": True, "manager": False, "accountant": False,
      "receptionist": False, "security": False}),
    ("users", "/users",
     {"owner": True, "manager": False, "accountant": False,
      "receptionist": False, "security": False}),
    ("audit log", "/audit",
     {"owner": True, "manager": False, "accountant": False,
      "receptionist": False, "security": False}),
    ("inventory", "/inventory",
     {"owner": True, "manager": False, "accountant": False,
      "receptionist": False, "security": False}),
    ("reports", "/reports",
     {"owner": True, "manager": True, "accountant": True,
      "receptionist": False, "security": False}),
]


@pytest.mark.parametrize("label,path,expected", READ_MATRIX,
                         ids=[row[0] for row in READ_MATRIX])
def test_read_access_matches_the_permission_grid(client, matrix, label, path, expected):
    for role, allowed in expected.items():
        r = client.get(f"{API}{path}", headers=auth(matrix["tokens"][role]))
        if allowed:
            assert r.status_code == 200, (
                f"{role} should read {label} but got {r.status_code}")
        else:
            assert r.status_code == 403, (
                f"{role} must NOT read {label} but got {r.status_code}")


# -------------------------------------------------------------- write grid
def test_only_authorised_roles_can_create_a_resident(client, matrix):
    body = lambda: {                                                # noqa: E731
        "first_name": "New", "last_name": uuid.uuid4().hex[:6],
        "phone": f"+9198{uuid.uuid4().int % 100000000:08d}",
        "branch_id": str(matrix["branch"].id),
    }
    for role in ("owner", "manager", "receptionist"):
        r = client.post(f"{API}/residents", json=body(),
                        headers=auth(matrix["tokens"][role]))
        assert r.status_code == 201, f"{role} should create residents: {r.text}"

    for role in ("accountant", "security"):
        r = client.post(f"{API}/residents", json=body(),
                        headers=auth(matrix["tokens"][role]))
        assert r.status_code == 403, f"{role} must not create residents"


def test_only_authorised_roles_can_assign_a_bed(client, matrix):
    for role in ("accountant", "receptionist", "security"):
        r = client.post(f"{API}/residents/{matrix['resident'].id}/assign-bed",
                        json={"bed_id": str(matrix["bed"].id)},
                        headers=auth(matrix["tokens"][role]))
        assert r.status_code == 403, f"{role} must not assign beds"

    r = client.post(f"{API}/residents/{matrix['resident'].id}/assign-bed",
                    json={"bed_id": str(matrix["bed"].id)},
                    headers=auth(matrix["tokens"]["manager"]))
    assert r.status_code == 200, r.text


def test_read_permission_does_not_imply_write(client, matrix):
    """
    The accountant can see residents. That must not let them edit one - the
    commonest way a permission system leaks is treating view as a prefix of
    everything else in its module.
    """
    r = client.patch(f"{API}/residents/{matrix['resident'].id}",
                     json={"occupation": "Edited by the accountant"},
                     headers=auth(matrix["tokens"]["accountant"]))
    assert r.status_code == 403


def test_expense_creation_is_limited_to_finance_roles(client, matrix):
    body = {"category": "Utilities", "amount": 500, "description": "Water",
            "spent_on": "2026-01-05", "branch_id": str(matrix["branch"].id)}
    assert client.post(f"{API}/expenses", json=body,
                       headers=auth(matrix["tokens"]["accountant"])).status_code in (200, 201)
    assert client.post(f"{API}/expenses", json=body,
                       headers=auth(matrix["tokens"]["receptionist"])).status_code == 403


def test_role_management_is_owner_only(client, matrix):
    body = {"name": f"Invented {uuid.uuid4().hex[:5]}", "permissions": ["dashboard.view"]}
    for role in ("manager", "accountant", "receptionist", "security"):
        r = client.post(f"{API}/roles", json=body, headers=auth(matrix["tokens"][role]))
        assert r.status_code == 403, f"{role} must not create roles"


def test_master_endpoints_are_closed_to_every_tenant_role(client, matrix):
    for role in ROLE_PERMISSIONS:
        for path in ("/master/organizations", "/master/dashboard", "/master/settings"):
            r = client.get(f"{API}{path}", headers=auth(matrix["tokens"][role]))
            assert r.status_code == 403, f"{role} reached {path}"


# --------------------------------------------------------- dynamic engine
def test_a_custom_role_is_enforced_like_a_named_one(db, client, matrix):
    """
    A PG invents "Night Warden". The engine has never heard of it, and must
    still grant exactly the two permissions it was given and nothing else.
    """
    role = make_role(db, matrix["org"], "Night Warden",
                     ["dashboard.view", "visitors.view"])
    make_user(db, matrix["org"], "warden@matrix.test", role=role,
              branches=[matrix["branch"]])
    db.commit()
    token = login(client, "warden@matrix.test")

    assert client.get(f"{API}/visitors", headers=auth(token)).status_code == 200
    assert client.get(f"{API}/residents", headers=auth(token)).status_code == 403
    assert client.get(f"{API}/invoices", headers=auth(token)).status_code == 403


def test_removing_a_permission_takes_effect_without_a_new_login(db, client, matrix):
    """
    Permissions are resolved per request, not baked into the token. A revoked
    permission that survives until the user next signs in is a revocation that
    did not happen.
    """
    role = make_role(db, matrix["org"], "Temp", ["dashboard.view", "invoices.view"])
    make_user(db, matrix["org"], "temp@matrix.test", role=role,
              branches=[matrix["branch"]])
    db.commit()
    token = login(client, "temp@matrix.test")
    assert client.get(f"{API}/invoices", headers=auth(token)).status_code == 200

    role.permissions = [p for p in role.permissions if p.code != "invoices.view"]
    db.commit()

    assert client.get(f"{API}/invoices", headers=auth(token)).status_code == 403


def test_adding_a_permission_takes_effect_without_a_new_login(db, client, matrix):
    role = make_role(db, matrix["org"], "Growing", ["dashboard.view"])
    make_user(db, matrix["org"], "growing@matrix.test", role=role,
              branches=[matrix["branch"]])
    db.commit()
    token = login(client, "growing@matrix.test")
    assert client.get(f"{API}/complaints", headers=auth(token)).status_code == 403

    from app.models import Permission
    extra = db.query(Permission).filter(Permission.code == "complaints.view").first()
    role.permissions = list(role.permissions) + [extra]
    db.commit()

    assert client.get(f"{API}/complaints", headers=auth(token)).status_code == 200


def test_a_deactivated_user_loses_access_immediately(db, client, matrix):
    from app.models import User

    token = matrix["tokens"]["manager"]
    assert client.get(f"{API}/residents", headers=auth(token)).status_code == 200

    user = db.query(User).filter(User.email == "manager@matrix.test").first()
    user.is_active = False
    db.commit()

    r = client.get(f"{API}/residents", headers=auth(token))
    assert r.status_code == 401, "a deactivated user kept a working session"


def test_a_user_with_no_role_can_reach_nothing(db, client, matrix):
    make_user(db, matrix["org"], "roleless@matrix.test", role=None,
              branches=[matrix["branch"]])
    db.commit()
    token = login(client, "roleless@matrix.test")
    for path in ("/residents", "/invoices", "/complaints", "/visitors"):
        assert client.get(f"{API}{path}", headers=auth(token)).status_code == 403
