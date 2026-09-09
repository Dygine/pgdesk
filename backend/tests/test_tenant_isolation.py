"""
The critical test (brief item 33).

Organisation A and Organisation B both exist. Owner A authenticates. Nothing
Owner A does - including naming B's identifiers explicitly - may reach B's data.

Milestone 2 has no resource endpoints yet, so these tests drive the layer that
every future endpoint is built on: the scope resolved from the token, and the
repository that turns that scope into a query. If this layer is right, a handler
cannot leak across tenants without deliberately bypassing it; if it is wrong,
every endpoint built on top inherits the hole.
"""
import uuid

import pytest
from sqlalchemy import select

from app.core.dependencies import CurrentScope, get_current_scope, require_branch
from app.core.exceptions import PermissionDeniedError, TenantIsolationError
from app.models import Branch, Customer, User
from app.repositories.base import TenantRepository
from tests.factories import (
    PASSWORD, make_branch, make_customer, make_org, make_role, make_user,
)


class BranchRepository(TenantRepository[Branch]):
    model = Branch


class CustomerRepository(TenantRepository[Customer]):
    model = Customer


@pytest.fixture
def two_tenants(db):
    a = make_org(db, "Alpha PG")
    b = make_org(db, "Beta PG")

    a_kor = make_branch(db, a, "Alpha Koramangala", "KOR")
    a_btm = make_branch(db, a, "Alpha BTM", "BTM")
    b_jay = make_branch(db, b, "Beta Jayanagar", "JAY")

    a_owner_role = make_role(db, a, "Owner", ["*"], all_branches=True, is_system=True)
    b_owner_role = make_role(db, b, "Owner", ["*"], all_branches=True, is_system=True)
    a_mgr_role = make_role(db, a, "Branch Manager", ["dashboard.view", "customers.view"])

    owner_a = make_user(db, a, "owner@alpha.test", role=a_owner_role)
    owner_b = make_user(db, b, "owner@beta.test", role=b_owner_role)
    # Assigned to KOR only - BTM belongs to their own tenant but not to them.
    mgr_a = make_user(db, a, "manager@alpha.test", role=a_mgr_role, branches=[a_kor])

    cust_a = make_customer(db, a, "resident@alpha.test", branch=a_kor)
    cust_b = make_customer(db, b, "resident@beta.test", branch=b_jay)
    db.commit()

    return dict(a=a, b=b, a_kor=a_kor, a_btm=a_btm, b_jay=b_jay,
                owner_a=owner_a, owner_b=owner_b, mgr_a=mgr_a,
                cust_a=cust_a, cust_b=cust_b)


def scope_for(db, user: User) -> CurrentScope:
    """Exactly what a request builds, without going through HTTP."""
    return get_current_scope(db=db, user=user)


# ------------------------------------------------------- scope resolution --
def test_owner_scope_is_pinned_to_their_own_organisation(db, two_tenants):
    scope = scope_for(db, two_tenants["owner_a"])
    assert scope.organization_id == two_tenants["a"].id
    assert scope.organization_id != two_tenants["b"].id


def test_owner_a_branch_scope_excludes_organisation_b(db, two_tenants):
    scope = scope_for(db, two_tenants["owner_a"])
    assert set(scope.branch_ids) == {two_tenants["a_kor"].id, two_tenants["a_btm"].id}
    assert two_tenants["b_jay"].id not in scope.branch_ids


def test_manager_sees_only_assigned_branches_within_their_own_tenant(db, two_tenants):
    scope = scope_for(db, two_tenants["mgr_a"])
    assert scope.branch_ids == [two_tenants["a_kor"].id]
    assert two_tenants["a_btm"].id not in scope.branch_ids       # own tenant, not assigned
    assert two_tenants["b_jay"].id not in scope.branch_ids       # other tenant


# ------------------------------------------------------- repository reads --
def test_branch_list_returns_only_the_callers_tenant(db, two_tenants):
    repo = BranchRepository(db, scope_for(db, two_tenants["owner_a"]))
    rows = db.scalars(repo.scoped()).all()
    assert {r.id for r in rows} == {two_tenants["a_kor"].id, two_tenants["a_btm"].id}


def test_owner_a_cannot_fetch_organisation_b_branch_by_id(db, two_tenants):
    """The attack: a valid id from the other tenant, supplied directly."""
    repo = BranchRepository(db, scope_for(db, two_tenants["owner_a"]))
    with pytest.raises(TenantIsolationError):
        repo.get_or_404(two_tenants["b_jay"].id)


def test_owner_a_cannot_fetch_organisation_b_customer_by_id(db, two_tenants):
    repo = CustomerRepository(db, scope_for(db, two_tenants["owner_a"]))
    with pytest.raises(TenantIsolationError):
        repo.get_or_404(two_tenants["cust_b"].id)


def test_cross_tenant_and_nonexistent_are_indistinguishable(db, two_tenants):
    """
    Both raise the same error type and map to 404. A 403 here would confirm the
    row exists in someone else's tenant, which is itself a leak.
    """
    repo = BranchRepository(db, scope_for(db, two_tenants["owner_a"]))

    with pytest.raises(TenantIsolationError) as cross:
        repo.get_or_404(two_tenants["b_jay"].id)
    with pytest.raises(TenantIsolationError) as missing:
        repo.get_or_404(uuid.uuid4())

    assert str(cross.value) == str(missing.value)
    assert cross.value.status_code == missing.value.status_code == 404


def test_owner_b_sees_only_their_own_side(db, two_tenants):
    repo = BranchRepository(db, scope_for(db, two_tenants["owner_b"]))
    rows = db.scalars(repo.scoped()).all()
    assert {r.id for r in rows} == {two_tenants["b_jay"].id}
    with pytest.raises(TenantIsolationError):
        repo.get_or_404(two_tenants["a_kor"].id)


def test_counts_do_not_leak_across_tenants(db, two_tenants):
    """Even an aggregate must not reveal the other tenant's volume."""
    a_repo = CustomerRepository(db, scope_for(db, two_tenants["owner_a"]))
    b_repo = CustomerRepository(db, scope_for(db, two_tenants["owner_b"]))
    assert a_repo.count() == 1
    assert b_repo.count() == 1


# ------------------------------------------------------ repository writes --
def test_writes_are_stamped_with_the_session_tenant_not_the_payload(db, two_tenants):
    """
    The forgery attempt: a create payload naming organisation B. The repository
    overwrites it from the authenticated scope, so the row lands in A.
    """
    repo = BranchRepository(db, scope_for(db, two_tenants["owner_a"]))
    forged = Branch(organization_id=two_tenants["b"].id, name="Injected", code="INJ")
    saved = repo.add(forged)
    assert saved.organization_id == two_tenants["a"].id


def test_a_repository_cannot_be_built_for_non_tenant_data(db, two_tenants):
    """Guard against pointing the scoped repository at a platform-wide table."""
    from app.models import SubscriptionPlan

    class PlanRepository(TenantRepository[SubscriptionPlan]):
        model = SubscriptionPlan

    with pytest.raises(TypeError, match="not tenant data"):
        PlanRepository(db, scope_for(db, two_tenants["owner_a"]))


# ---------------------------------------------------------- branch guard --
def test_require_branch_rejects_another_tenants_branch(db, two_tenants):
    scope = scope_for(db, two_tenants["owner_a"])
    with pytest.raises(PermissionDeniedError):
        require_branch(scope, two_tenants["b_jay"].id)


def test_require_branch_rejects_an_unassigned_branch_in_the_same_tenant(db, two_tenants):
    scope = scope_for(db, two_tenants["mgr_a"])
    require_branch(scope, two_tenants["a_kor"].id)              # assigned: fine
    with pytest.raises(PermissionDeniedError):
        require_branch(scope, two_tenants["a_btm"].id)          # same tenant, not theirs


# --------------------------------------------------------------- over HTTP --
def test_token_from_tenant_a_describes_only_tenant_a(client, two_tenants):
    r = client.post("/api/v1/auth/login",
                    json={"email": "owner@alpha.test", "password": PASSWORD})
    data = r.json()["data"]["user"]
    assert data["organization"]["name"] == "Alpha PG"
    assert {b["code"] for b in data["branches"]} == {"KOR", "BTM"}
    assert "Beta" not in r.text


def test_a_token_carries_no_organisation_the_client_could_edit(client, two_tenants):
    """
    The access token holds only a subject and a principal kind. There is no
    organisation claim to tamper with, because the server resolves the tenant
    from the user record on every request.
    """
    from app.core.security import decode_token

    token = client.post("/api/v1/auth/login",
                        json={"email": "owner@alpha.test", "password": PASSWORD}
                        ).json()["data"]["access_token"]
    payload = decode_token(token, expected_type="access")
    assert set(payload) == {"sub", "type", "iat", "exp", "principal"}
    assert "org" not in payload
    assert "organization_id" not in payload


def test_resident_token_cannot_reach_a_staff_dependency(client, two_tenants):
    """A resident token must not satisfy get_current_user."""
    from app.core.dependencies import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials

    token = client.post("/api/v1/auth/login",
                        json={"email": "resident@alpha.test", "password": PASSWORD}
                        ).json()["data"]["access_token"]

    with pytest.raises(PermissionDeniedError):
        get_current_user(
            db=None,
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
        )
