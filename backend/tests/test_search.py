"""
Global search.

Search reaches across nine tables at once, which makes it the easiest place in
the product to accidentally build a side door: a receptionist who cannot open
the expenses page must not be able to read expense descriptions by typing in the
search box, and a manager assigned to one branch must not learn who lives in
another.

So the tests here are mostly negative. The happy path is one assertion; the rest
prove what search refuses to return.
"""
import pytest

from app.models.enums import CustomerStatus
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


def search(client, token, q, **params):
    r = client.get(f"{API}/search", params={"q": q, **params}, headers=auth(token))
    return r


def titles(response) -> set[str]:
    return {hit["title"] for hit in response.json()["data"]["results"]}


def types(response) -> set[str]:
    return {hit["type"] for hit in response.json()["data"]["results"]}


@pytest.fixture
def world(db, client):
    """
    Two tenants. Inside tenant A, two branches and a manager confined to one.
    Every searchable name contains "Kumar" so one query reaches everything.
    """
    a = make_org(db, "Alpha PG")
    b = make_org(db, "Beta PG")

    kor = make_branch(db, a, "Alpha Koramangala", "KOR")
    btm = make_branch(db, a, "Alpha BTM", "BTM")
    jay = make_branch(db, b, "Beta Jayanagar", "JAY")

    make_property(db, a, kor, beds=1)
    make_property(db, a, btm, beds=1)
    make_property(db, b, jay, beds=1)

    owner_role = make_role(db, a, "Owner", ["*"], all_branches=True, is_system=True)
    owner_a = make_user(db, a, "owner@alpha.test", role=owner_role)

    b_owner_role = make_role(db, b, "Owner", ["*"], all_branches=True, is_system=True)
    make_user(db, b, "owner@beta.test", role=b_owner_role)

    # Confined to KOR, and holds customers.view but NOT expenses/payments/users.
    desk_role = make_role(db, a, "Receptionist",
                          ["dashboard.view", "customers.view"])
    make_user(db, a, "desk@alpha.test", role=desk_role, branches=[kor])

    # Holds nothing that search exposes.
    blind_role = make_role(db, a, "Blind", ["dashboard.view"])
    make_user(db, a, "blind@alpha.test", role=blind_role, branches=[kor])

    make_customer(db, a, "kumar.kor@alpha.test", branch=kor,
                  status=CustomerStatus.ACTIVE)
    make_customer(db, a, "kumar.btm@alpha.test", branch=btm,
                  status=CustomerStatus.ACTIVE)
    make_customer(db, b, "kumar.beta@beta.test", branch=jay,
                  status=CustomerStatus.ACTIVE)
    db.commit()

    return dict(
        a=a, b=b, kor=kor, btm=btm,
        owner_a=login(client, "owner@alpha.test"),
        owner_b=login(client, "owner@beta.test"),
        desk=login(client, "desk@alpha.test"),
        blind=login(client, "blind@alpha.test"),
    )


# ------------------------------------------------------------- happy path
def test_an_owner_finds_residents_across_their_own_branches(client, world):
    found = titles(search(client, world["owner_a"], "Kumar"))
    assert "Kumar.Kor" in found
    assert "Kumar.Btm" in found


def test_results_carry_a_link_the_ui_can_navigate_to(client, world):
    hits = search(client, world["owner_a"], "Kumar").json()["data"]["results"]
    residents = [h for h in hits if h["type"] == "resident"]
    assert residents and all(h["link"].startswith("/app/residents/") for h in residents)


# --------------------------------------------------------- tenant isolation
def test_search_never_crosses_into_another_tenant(client, world):
    """The other tenant's resident matches the term and must still not appear."""
    assert "Kumar.Beta" not in titles(search(client, world["owner_a"], "Kumar"))
    assert "Kumar.Kor" not in titles(search(client, world["owner_b"], "Kumar"))


def test_searching_another_tenants_exact_name_returns_nothing(client, world):
    r = search(client, world["owner_a"], "Kumar.Beta")
    assert r.status_code == 200
    assert r.json()["data"]["results"] == []


# --------------------------------------------------------- branch isolation
def test_a_branch_confined_user_sees_only_their_branch(client, world):
    """
    Same tenant, same permission, different branch. The BTM resident is one the
    receptionist has no business knowing exists.
    """
    found = titles(search(client, world["desk"], "Kumar"))
    assert "Kumar.Kor" in found
    assert "Kumar.Btm" not in found


# ------------------------------------------------------- permission gating
def test_entities_the_caller_cannot_view_are_absent(client, world):
    """
    The receptionist holds customers.view only. Search must not hand them staff
    records, payments or expenses just because the query matched.
    """
    found = types(search(client, world["desk"], "Kumar"))
    assert found <= {"resident"}, f"leaked entity types: {found - {'resident'}}"


def test_a_user_with_no_module_permissions_gets_nothing(client, world):
    r = search(client, world["blind"], "Kumar")
    assert r.status_code == 200
    assert r.json()["data"]["results"] == []


def test_staff_records_are_gated_by_the_users_permission(client, world):
    """An owner holds users.view, so staff surface for them and not the desk."""
    assert "staff" in types(search(client, world["owner_a"], "alpha"))
    assert "staff" not in types(search(client, world["desk"], "alpha"))


def test_the_types_filter_cannot_widen_beyond_permissions(client, world):
    """Asking for an entity you cannot see is refused, not honoured."""
    r = search(client, world["desk"], "Kumar", types="staff,payment,invoice")
    assert r.status_code == 200
    assert r.json()["data"]["results"] == []


# -------------------------------------------------------------- guardrails
def test_a_single_character_query_is_rejected(client, world):
    """An unbounded prefix match across nine tables is a self-inflicted outage."""
    assert search(client, world["owner_a"], "a").status_code == 422


def test_the_per_type_limit_is_capped(client, world):
    """The ceiling is the server's, not the caller's."""
    assert search(client, world["owner_a"], "Kumar", limit=500).status_code == 422


def test_search_requires_authentication(client, world):
    assert client.get(f"{API}/search", params={"q": "Kumar"}).status_code == 401


def test_a_master_admin_has_no_tenant_to_search(db, client, world):
    """
    Search is a tenant operation. A master admin holds no organisation scope, so
    the endpoint refuses rather than quietly searching everything.
    """
    make_user(db, None, "root@pgdesk.test", is_master=True)
    db.commit()
    token = login(client, "root@pgdesk.test")
    assert search(client, token, "Kumar").status_code == 403
