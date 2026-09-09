"""Login, /auth/me, refresh, logout, and everything that must fail."""
import pytest

from app.models.enums import CustomerStatus, OrganizationStatus, UserStatus
from tests.factories import (
    PASSWORD, make_branch, make_customer, make_org, make_role, make_user,
)


@pytest.fixture
def sunrise(db):
    org = make_org(db, "Sunrise Living")
    kor = make_branch(db, org, "Koramangala", "KOR")
    btm = make_branch(db, org, "BTM Layout", "BTM")
    owner_role = make_role(db, org, "Owner", ["*"], all_branches=True, is_system=True)
    mgr_role = make_role(db, org, "Branch Manager",
                         ["dashboard.view", "customers.view", "rooms.view", "beds.assign"])
    owner = make_user(db, org, "owner@sunrise.test", role=owner_role)
    manager = make_user(db, org, "manager@sunrise.test", role=mgr_role, branches=[kor, btm])
    resident = make_customer(db, org, "resident@sunrise.test", branch=kor)
    db.commit()
    return dict(org=org, kor=kor, btm=btm, owner=owner, manager=manager,
                resident=resident, owner_role=owner_role, mgr_role=mgr_role)


def login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# ------------------------------------------------------------------ success
def test_owner_login_succeeds(client, sunrise):
    r = login(client, "owner@sunrise.test")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["token_type"] == "bearer"
    # The refresh token is an HttpOnly cookie now, not a body field.
    assert data["access_token"]
    assert "refresh_token" not in data
    assert data["expires_in"] > 0


def test_login_never_returns_a_password_field(client, sunrise):
    raw = login(client, "owner@sunrise.test").text
    assert "password_hash" not in raw
    assert PASSWORD not in raw


def test_owner_response_carries_role_org_branches_and_permissions(client, sunrise):
    data = login(client, "owner@sunrise.test").json()["data"]["user"]
    assert data["portal"] == "org"
    assert data["role"]["name"] == "Owner"
    assert data["organization"]["name"] == "Sunrise Living"
    assert data["all_branches"] is True
    assert {b["code"] for b in data["branches"]} == {"KOR", "BTM"}
    assert "customers.view" in data["permissions"]

    # Derived from the catalogue rather than hard-coded: an owner holds every
    # tenant permission, so this keeps holding as the catalogue grows.
    from app.permissions.catalog import ALL_PERMISSIONS
    assert set(data["permissions"]) == set(ALL_PERMISSIONS)


def test_manager_gets_only_assigned_branches_and_a_narrow_permission_set(client, sunrise):
    data = login(client, "manager@sunrise.test").json()["data"]["user"]
    assert data["all_branches"] is False
    assert sorted(data["permissions"]) == [
        "beds.assign", "customers.view", "dashboard.view", "rooms.view"
    ]


def test_master_admin_login(client, db):
    make_user(db, None, "master@platform.test", is_master=True)
    db.commit()
    data = login(client, "master@platform.test").json()["data"]["user"]
    assert data["portal"] == "master"
    assert data["is_master_admin"] is True
    assert data["organization"] is None          # master admins hold no tenant scope
    assert data["branches"] == []
    assert all(p.startswith("master.") for p in data["permissions"])


def test_customer_login(client, sunrise):
    data = login(client, "resident@sunrise.test").json()["data"]["user"]
    assert data["portal"] == "customer"
    assert data["principal"] == "customer"
    assert data["permissions"] == []             # residents hold no module permissions
    assert data["organization"]["name"] == "Sunrise Living"


def test_subscription_context_is_exposed_for_milestone_3(client, sunrise):
    org = login(client, "owner@sunrise.test").json()["data"]["user"]["organization"]
    sub = org["subscription"]
    assert sub["status"] == "ACTIVE"
    assert sub["days_remaining"] > 0
    assert sub["limits"]["branches"] == 3


def test_last_login_is_recorded(client, sunrise, db):
    assert sunrise["owner"].last_login_at is None
    login(client, "owner@sunrise.test")
    db.refresh(sunrise["owner"])
    assert sunrise["owner"].last_login_at is not None


# ----------------------------------------------------------------- failures
def test_wrong_password_is_rejected(client, sunrise):
    r = login(client, "owner@sunrise.test", "wrong-password")
    assert r.status_code == 401
    assert r.json()["success"] is False


def test_unknown_email_is_rejected(client, sunrise):
    assert login(client, "nobody@nowhere.test").status_code == 401


def test_unknown_email_and_wrong_password_are_indistinguishable(client, sunrise):
    """Account enumeration: the two responses must be byte-identical."""
    unknown = login(client, "nobody@nowhere.test")
    wrong = login(client, "owner@sunrise.test", "wrong-password")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_suspended_user_cannot_sign_in(client, db):
    org = make_org(db, "Suspended Staff PG")
    role = make_role(db, org, "Owner", ["*"], all_branches=True)
    make_user(db, org, "suspended@pg.test", role=role, status=UserStatus.SUSPENDED)
    db.commit()
    r = login(client, "suspended@pg.test")
    assert r.status_code == 403
    assert "suspended" in r.json()["message"].lower()


def test_deactivated_user_cannot_sign_in(client, db):
    org = make_org(db, "Deactivated PG")
    role = make_role(db, org, "Owner", ["*"], all_branches=True)
    make_user(db, org, "gone@pg.test", role=role,
              status=UserStatus.DEACTIVATED, is_active=False)
    db.commit()
    assert login(client, "gone@pg.test").status_code == 403


def test_status_is_not_revealed_without_the_correct_password(client, db):
    """A suspended account must not be discoverable by guessing emails."""
    org = make_org(db, "Quiet PG")
    role = make_role(db, org, "Owner", ["*"], all_branches=True)
    make_user(db, org, "quiet@pg.test", role=role, status=UserStatus.SUSPENDED)
    db.commit()
    r = login(client, "quiet@pg.test", "not-the-password")
    assert r.status_code == 401
    assert "suspend" not in r.text.lower()


def test_user_of_a_suspended_organisation_cannot_sign_in(client, db):
    org = make_org(db, "Frozen PG", status=OrganizationStatus.SUSPENDED)
    role = make_role(db, org, "Owner", ["*"], all_branches=True)
    make_user(db, org, "owner@frozen.test", role=role)
    db.commit()
    r = login(client, "owner@frozen.test")
    assert r.status_code == 403
    assert "suspended" in r.json()["message"].lower()


def test_checked_out_resident_cannot_sign_in(client, db):
    org = make_org(db, "Checkout PG")
    make_customer(db, org, "left@pg.test", status=CustomerStatus.CHECKED_OUT)
    db.commit()
    r = login(client, "left@pg.test")
    assert r.status_code == 403
    assert "checked out" in r.json()["message"].lower()


def test_resident_without_a_password_cannot_sign_in(client, db):
    """An enquiry has a NULL hash; it must not fall through to any default."""
    org = make_org(db, "Enquiry PG")
    make_customer(db, org, "enquiry@pg.test", password=None,
                  status=CustomerStatus.ENQUIRY)
    db.commit()
    r = login(client, "enquiry@pg.test", "anything")
    assert r.status_code == 401


def test_malformed_email_is_a_validation_error(client):
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
