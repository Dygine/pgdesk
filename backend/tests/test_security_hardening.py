"""
Security: authentication, session handling and safe configuration.

`test_security.py` covers the primitives (hashing, token signing). This file
covers how they behave when wired into the running application - the layer where
a correct primitive still gets used wrongly.

Grouped by what is being defended:

  enumeration   the login response must not reveal which addresses have accounts
  brute force   repeated wrong guesses must not be free
  session       revocation must be immediate, everywhere
  cookies       the refresh credential must be unreachable from script
  disclosure    errors must not leak internals
  config        production must refuse to start unsafely
"""
import uuid

import pytest

from app.core.config import Settings
from app.core.session_cookie import CSRF_HEADER
from app.models.enums import CustomerStatus, OrganizationStatus, UserStatus
from tests.factories import (
    PASSWORD, make_branch, make_customer, make_org, make_role, make_user,
)

API = "/api/v1"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def attempt(client, email: str, password: str = PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


@pytest.fixture
def accounts(db):
    org = make_org(db, "Secure PG")
    branch = make_branch(db, org, "Koramangala", "KOR")
    role = make_role(db, org, "Owner", ["*"], all_branches=True, is_system=True)
    owner = make_user(db, org, "owner@secure.test", role=role)
    disabled = make_user(db, org, "disabled@secure.test", role=role, is_active=False)
    suspended_org = make_org(db, "Suspended PG", status=OrganizationStatus.SUSPENDED)
    s_role = make_role(db, suspended_org, "Owner", ["*"], all_branches=True, is_system=True)
    make_user(db, suspended_org, "owner@suspended.test", role=s_role)
    resident = make_customer(db, org, "resident@secure.test", branch=branch,
                             status=CustomerStatus.ACTIVE)
    db.commit()
    return dict(org=org, branch=branch, owner=owner, disabled=disabled,
                resident=resident)


# ------------------------------------------------------ account enumeration
def test_a_wrong_password_and_an_unknown_email_are_indistinguishable(client, accounts):
    """
    If these differ in message, status or shape, the login form becomes a tool
    for discovering which of a leaked address list holds accounts here.
    """
    wrong_password = attempt(client, "owner@secure.test", "definitely-not-it")
    unknown_email = attempt(client, "nobody@secure.test", "definitely-not-it")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["message"] == unknown_email.json()["message"]
    assert wrong_password.json().get("code") == unknown_email.json().get("code")


def test_the_failure_message_names_no_account_detail(client, accounts):
    body = attempt(client, "owner@secure.test", "wrong").json()["message"].lower()
    for leak in ("password", "email", "user", "exists", "found", "incorrect password"):
        if leak in ("password", "email"):
            continue                      # generic wording may mention the fields
        assert leak not in body, f"login failure leaked '{leak}'"


def test_a_disabled_account_does_not_advertise_itself_to_a_guesser(client, accounts):
    """
    With the WRONG password, a disabled account must be indistinguishable from
    an active one — otherwise the login form reveals which addresses exist.

    With the RIGHT password the system answers honestly that the account is
    deactivated, and that is correct rather than a leak: whoever supplied the
    password has already proved they own the account, so telling them why they
    cannot get in reveals nothing they did not know and saves a support call.
    """
    disabled = attempt(client, "disabled@secure.test", "wrong-guess")
    active = attempt(client, "owner@secure.test", "wrong-guess")
    assert disabled.status_code == active.status_code == 401
    assert disabled.json()["message"] == active.json()["message"]


def test_a_disabled_account_is_told_why_once_it_proves_ownership(client, accounts):
    r = attempt(client, "disabled@secure.test")
    assert r.status_code == 403
    assert "deactivat" in r.json()["message"].lower()


# ------------------------------------------------------------- brute force
def test_repeated_failures_are_throttled(client, accounts):
    """
    Unlimited free guesses turn any weak password into a matter of time. After a
    run of failures the endpoint must stop answering normally - by lockout or by
    rate limit; either is acceptable, silence is not.
    """
    statuses = [attempt(client, "owner@secure.test", f"guess-{i}").status_code
                for i in range(12)]
    assert all(s in (401, 423, 429) for s in statuses), statuses
    assert any(s in (423, 429) for s in statuses), (
        "twelve consecutive wrong passwords were all answered as plain 401 - "
        "there is no brute-force protection on this endpoint")


def test_failed_logins_are_audited(client, accounts, db):
    from app.models import AuditLog

    attempt(client, "owner@secure.test", "wrong-one")
    entries = db.query(AuditLog).filter(AuditLog.module == "Auth").all()
    assert any("fail" in (e.description or "").lower()
               or e.action == "LOGIN_FAILED" for e in entries), \
        "a failed login left no audit record"


def test_no_audit_entry_ever_contains_a_password(client, accounts, db):
    from app.models import AuditLog

    attempt(client, "owner@secure.test", "SuperSecret123!")
    for entry in db.query(AuditLog).all():
        assert "SuperSecret123!" not in (entry.description or "")


# ------------------------------------------------------- session lifecycle
def test_deactivating_a_user_kills_their_live_session(client, accounts, db):
    from app.models import User

    token = attempt(client, "owner@secure.test").json()["data"]["access_token"]
    assert client.get(f"{API}/auth/me", headers=auth(token)).status_code == 200

    db.query(User).filter(User.email == "owner@secure.test").first().is_active = False
    db.commit()

    assert client.get(f"{API}/auth/me", headers=auth(token)).status_code == 401


def test_a_suspended_organisation_cannot_sign_in_at_all(client, accounts):
    """
    Refused at the door rather than after the token is issued. Stronger than
    letting them in and blocking each endpoint: there is no window in which a
    suspended tenant holds a working credential.
    """
    r = attempt(client, "owner@suspended.test")
    assert r.status_code == 403
    assert "suspended" in r.json()["message"].lower()
    assert "data" not in r.json() or not r.json().get("data")


def test_a_resident_token_cannot_be_used_as_a_staff_token(client, accounts):
    token = attempt(client, "resident@secure.test").json()["data"]["access_token"]
    for path in ("/residents", "/invoices", "/users", "/audit", "/search?q=test"):
        r = client.get(f"{API}{path}", headers=auth(token))
        assert r.status_code == 403, f"a resident reached {path}"


def test_a_staff_token_cannot_be_used_as_a_resident_token(client, accounts):
    token = attempt(client, "owner@secure.test").json()["data"]["access_token"]
    for path in ("/me/home", "/me/profile", "/me/rent"):
        assert client.get(f"{API}{path}", headers=auth(token)).status_code == 403


# ------------------------------------------------------------ cookie safety
def test_the_refresh_cookie_is_httponly_and_path_scoped(client, accounts):
    from app.core.config import settings

    r = attempt(client, "owner@secure.test")
    raw = r.headers["set-cookie"].lower()
    assert "httponly" in raw, "the refresh cookie is readable by script"
    assert f"path={settings.refresh_cookie_path}".lower() in raw, (
        "the refresh cookie is not path-scoped, so it rides on every request")
    assert "samesite" in raw


def test_the_refresh_token_is_absent_from_every_response_body(client, accounts):
    """The whole point: nothing script can read ever contains it."""
    login = attempt(client, "owner@secure.test")
    assert "refresh_token" not in login.text

    refreshed = client.post(f"{API}/auth/refresh", json={},
                            headers={CSRF_HEADER: "1"})
    assert refreshed.status_code == 200
    assert "refresh_token" not in refreshed.text

    token = login.json()["data"]["access_token"]
    assert "refresh_token" not in client.get(f"{API}/auth/me",
                                             headers=auth(token)).text


def test_a_cookie_without_the_custom_header_is_refused(client, accounts):
    """
    The CSRF factor. A cross-site form post cannot set a custom header, and a
    cross-origin fetch that tries is stopped at the preflight.
    """
    attempt(client, "owner@secure.test")
    assert client.post(f"{API}/auth/refresh", json={}).status_code == 401


# ------------------------------------------------------------- disclosure
def test_errors_do_not_leak_internals(client, accounts):
    token = attempt(client, "owner@secure.test").json()["data"]["access_token"]
    responses = [
        client.get(f"{API}/residents/{uuid.uuid4()}", headers=auth(token)),
        client.get(f"{API}/residents/not-a-uuid", headers=auth(token)),
        client.post(f"{API}/residents", json={"nonsense": True}, headers=auth(token)),
        client.get(f"{API}/nope", headers=auth(token)),
    ]
    for r in responses:
        body = r.text.lower()
        for leak in ("traceback", "sqlalchemy", "psycopg", "select ", "/home/",
                     "site-packages", "secret_key", "password_hash"):
            assert leak not in body, f"{r.request.url} leaked '{leak}'"


def test_a_password_hash_is_never_serialised(client, accounts):
    token = attempt(client, "owner@secure.test").json()["data"]["access_token"]
    for path in ("/auth/me", "/users", "/residents"):
        body = client.get(f"{API}{path}", headers=auth(token)).text
        assert "password_hash" not in body
        assert "$argon2" not in body


def test_kyc_numbers_are_masked_without_the_permission(client, accounts, db):
    from app.models import ResidentKyc
    from app.models.enums import KycIdType, KycStatus

    db.add(ResidentKyc(organization_id=accounts["org"].id,
                       resident_id=accounts["resident"].id,
                       id_type=KycIdType.AADHAAR, id_number="9988 7766 5544",
                       status=KycStatus.VERIFIED))
    role = make_role(db, accounts["org"], "No KYC", ["customers.view"])
    make_user(db, accounts["org"], "nokyc@secure.test", role=role,
              branches=[accounts["branch"]])
    db.commit()

    token = attempt(client, "nokyc@secure.test").json()["data"]["access_token"]
    r = client.get(f"{API}/residents/{accounts['resident'].id}/kyc",
                   headers=auth(token))
    if r.status_code == 200:
        assert "9988 7766 5544" not in r.text, "an unmasked KYC number was returned"


# ------------------------------------------------------ configuration safety
def test_production_refuses_a_default_secret_key():
    s = Settings(environment="production", debug=False,
                 secret_key="dev-only-insecure-key-change-me",
                 cors_origins="https://app.example.com")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        s.assert_production_safe()


def test_production_refuses_wildcard_cors():
    s = Settings(environment="production", debug=False,
                 secret_key="x" * 48, cors_origins="*")
    with pytest.raises(RuntimeError, match="CORS"):
        s.assert_production_safe()


def test_production_refuses_debug_mode():
    s = Settings(environment="production", debug=True, secret_key="x" * 48,
                 cors_origins="https://app.example.com")
    with pytest.raises(RuntimeError, match="DEBUG"):
        s.assert_production_safe()


def test_production_refuses_an_insecure_refresh_cookie():
    s = Settings(environment="production", debug=False, secret_key="x" * 48,
                 cors_origins="https://app.example.com", refresh_cookie_secure=False)
    with pytest.raises(RuntimeError, match="REFRESH_COOKIE_SECURE"):
        s.assert_production_safe()


def test_production_refuses_to_put_the_refresh_token_in_the_body():
    s = Settings(environment="production", debug=False, secret_key="x" * 48,
                 cors_origins="https://app.example.com",
                 expose_refresh_token_in_body=True)
    with pytest.raises(RuntimeError, match="EXPOSE_REFRESH_TOKEN_IN_BODY"):
        s.assert_production_safe()


def test_a_correct_production_configuration_boots():
    s = Settings(environment="production", debug=False, secret_key="x" * 48,
                 cors_origins="https://app.example.com",
                 refresh_cookie_secure=True, expose_refresh_token_in_body=False)
    s.assert_production_safe()      # must not raise
