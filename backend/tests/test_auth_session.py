"""
/auth/me, token validation, refresh rotation, logout, password change.

The refresh token is no longer in the response body: it is an HttpOnly cookie,
so these tests read it from the client's cookie jar the way a browser would.
`TestClient` persists cookies across requests, which means the refresh and
logout calls below send an empty body and exercise exactly the path the real
front end uses.
"""
from datetime import timedelta

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.core.session_cookie import CSRF_HEADER
from app.models import RefreshToken
from tests.factories import PASSWORD, make_branch, make_customer, make_org, make_role, make_user


@pytest.fixture
def org_setup(db):
    org = make_org(db, "Session PG")
    kor = make_branch(db, org, "Koramangala", "KOR")
    role = make_role(db, org, "Owner", ["*"], all_branches=True, is_system=True)
    owner = make_user(db, org, "owner@session.test", role=role)
    resident = make_customer(db, org, "resident@session.test", branch=kor)
    db.commit()
    return dict(org=org, owner=owner, resident=resident)


def login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# The header the browser client sends on every state-changing auth call. Its
# presence is the CSRF assertion - see app/core/session_cookie.py.
CSRF = {CSRF_HEADER: "1"}


def refresh_cookie(client) -> str | None:
    """The live refresh token, read the way only the browser can - from the jar."""
    return client.cookies.get(settings.refresh_cookie_name)


def do_refresh(client, token: str | None = None):
    """Refresh through the cookie, or with an explicit token for API clients."""
    body = {"refresh_token": token} if token else {}
    return client.post("/api/v1/auth/refresh", json=body, headers=CSRF)


def present_token_alone(client, token: str):
    """
    Present a bare refresh token with no session cookie.

    This is both the non-browser API client and the attacker who has a copy of a
    token but not the victim's cookie jar. It matters that it is tested this way
    round: with a live cookie present the cookie wins, so replaying an old token
    alongside a good one would succeed for the wrong reason.
    """
    client.cookies.clear()
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


# ------------------------------------------------------------------- /me --
def test_me_returns_the_authenticated_user(client, org_setup):
    tokens = login(client, "owner@session.test")["data"]
    r = client.get("/api/v1/auth/me", headers=auth(tokens["access_token"]))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["email"] == "owner@session.test"
    assert data["organization"]["name"] == "Session PG"
    assert "customers.view" in data["permissions"]


def test_me_requires_a_token(client, org_setup):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["code"] == "not_authenticated"


def test_me_rejects_a_garbage_token(client, org_setup):
    assert client.get("/api/v1/auth/me", headers=auth("not.a.token")).status_code == 401


def test_me_rejects_a_tampered_token(client, org_setup):
    token = login(client, "owner@session.test")["data"]["access_token"]
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    assert client.get("/api/v1/auth/me", headers=auth(tampered)).status_code == 401


def test_me_rejects_an_expired_token(client, org_setup):
    """Forged with an exp in the past, signed with the real key."""
    from datetime import datetime, timezone
    expired = jwt.encode(
        {"sub": str(org_setup["owner"].id), "type": "access", "principal": "user",
         "exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
        settings.secret_key, algorithm=settings.jwt_algorithm,
    )
    assert client.get("/api/v1/auth/me", headers=auth(expired)).status_code == 401


def test_me_rejects_a_token_signed_with_the_wrong_key(client, org_setup):
    forged = jwt.encode(
        {"sub": str(org_setup["owner"].id), "type": "access", "principal": "user"},
        "an-attacker-chosen-key", algorithm="HS256",
    )
    assert client.get("/api/v1/auth/me", headers=auth(forged)).status_code == 401


def test_a_refresh_token_cannot_be_used_as_an_access_token(client, org_setup):
    """Token confusion: the `type` claim is checked, not just the signature."""
    refresh = create_refresh_token(str(org_setup["owner"].id), principal="user")
    assert client.get("/api/v1/auth/me", headers=auth(refresh)).status_code == 401


def test_customer_me_works(client, org_setup):
    tokens = login(client, "resident@session.test")["data"]
    data = client.get("/api/v1/auth/me", headers=auth(tokens["access_token"])).json()["data"]
    assert data["portal"] == "customer"
    assert data["permissions"] == []


# --------------------------------------------------------------- refresh --
def test_login_puts_the_refresh_token_in_an_httponly_cookie(client, org_setup):
    """
    The point of the whole exercise: the long-lived credential is not in the
    body, so a script that can read the response still cannot read it.
    """
    r = client.post("/api/v1/auth/login",
                    json={"email": "owner@session.test", "password": PASSWORD})
    assert r.status_code == 200
    assert "refresh_token" not in r.json()["data"]
    assert r.json()["data"]["access_token"]

    jar = r.cookies.get(settings.refresh_cookie_name)
    assert jar, "no refresh cookie was set"

    raw = r.headers["set-cookie"].lower()
    assert "httponly" in raw
    assert f"path={settings.refresh_cookie_path}".lower() in raw


def test_refresh_returns_a_new_pair(client, org_setup):
    login(client, "owner@session.test")
    before = refresh_cookie(client)

    r = do_refresh(client)
    assert r.status_code == 200
    fresh = r.json()["data"]
    assert fresh["access_token"]
    assert "refresh_token" not in fresh          # still not in the body
    assert refresh_cookie(client) != before      # rotated in the jar
    assert client.get("/api/v1/auth/me", headers=auth(fresh["access_token"])).status_code == 200


def test_refresh_tokens_are_single_use(client, org_setup):
    """Once its replacement has been used, the old token is dead for good."""
    login(client, "owner@session.test")
    original = refresh_cookie(client)

    assert do_refresh(client).status_code == 200      # original -> second
    assert do_refresh(client).status_code == 200      # the replacement is now in use
    assert present_token_alone(client, original).status_code == 401


def test_replaying_a_used_refresh_token_kills_every_session(client, org_setup):
    """
    Reuse means either a replay or a stolen token in play alongside the real
    one. The safe response is to invalidate the whole family.
    """
    login(client, "owner@session.test")
    original = refresh_cookie(client)

    assert do_refresh(client).status_code == 200
    assert do_refresh(client).status_code == 200  # two parties now hold this chain
    rotated = refresh_cookie(client)

    present_token_alone(client, original)        # the replay

    # The legitimate current token is now dead too.
    assert present_token_alone(client, rotated).status_code == 401


def test_refresh_rejects_an_unknown_token(client, org_setup):
    assert present_token_alone(client, "x" * 60).status_code == 401


def test_refresh_without_any_session_is_rejected(client, org_setup):
    assert client.post("/api/v1/auth/refresh", json={}, headers=CSRF).status_code == 401


def test_refresh_with_a_cookie_but_no_csrf_header_is_rejected(client, org_setup):
    """
    A cookie rides along whether or not the page asked for it, so the cookie
    alone must not be sufficient. The header cannot be set by a cross-site form
    post, and a cross-origin fetch that sets it is stopped at the preflight.
    """
    login(client, "owner@session.test")
    assert refresh_cookie(client)
    assert client.post("/api/v1/auth/refresh", json={}).status_code == 401


def test_the_cookie_wins_over_a_stale_body_token(client, org_setup):
    """A pasted stale token must not displace the live browser session."""
    login(client, "owner@session.test")
    live = refresh_cookie(client)
    assert do_refresh(client).status_code == 200      # rotates; `live` now dead

    # Presenting the dead token in the body is ignored: the fresh cookie wins.
    assert do_refresh(client, live).status_code == 200
    # And on its own, with no cookie to fall back on, it is refused.
    assert present_token_alone(client, live).status_code == 401


def test_refresh_token_is_not_stored_in_plaintext(client, org_setup, db):
    login(client, "owner@session.test")
    presented = refresh_cookie(client)
    stored = db.query(RefreshToken).all()
    assert stored
    assert all(row.token_hash != presented for row in stored)
    assert all(len(row.token_hash) == 64 for row in stored)       # sha256 hex


# ---------------------------------------------------------------- logout --
def test_logout_revokes_this_session(client, org_setup):
    tokens = login(client, "owner@session.test")["data"]
    presented = refresh_cookie(client)

    r = client.post("/api/v1/auth/logout", json={},
                    headers={**auth(tokens["access_token"]), **CSRF})
    assert r.status_code == 200
    assert present_token_alone(client, presented).status_code == 401


def test_logout_clears_the_cookie(client, org_setup):
    """
    A cookie left behind means the browser keeps presenting a revoked token,
    which reads to the user as a sign-out that did not work.
    """
    tokens = login(client, "owner@session.test")["data"]
    r = client.post("/api/v1/auth/logout", json={},
                    headers={**auth(tokens["access_token"]), **CSRF})
    assert 'path=%s' % settings.refresh_cookie_path in r.headers["set-cookie"].lower()
    assert not refresh_cookie(client)


def test_logout_all_sessions_revokes_every_device(client, org_setup):
    login(client, "owner@session.test")
    first = refresh_cookie(client)
    second_tokens = login(client, "owner@session.test")["data"]
    second = refresh_cookie(client)

    client.post("/api/v1/auth/logout", json={"all_sessions": True},
                headers={**auth(second_tokens["access_token"]), **CSRF})

    for token in (first, second):
        assert present_token_alone(client, token).status_code == 401


def test_logout_requires_authentication(client, org_setup):
    assert client.post("/api/v1/auth/logout", json={}).status_code == 401


def test_logout_is_idempotent(client, org_setup):
    tokens = login(client, "owner@session.test")["data"]
    headers = {**auth(tokens["access_token"]), **CSRF}
    assert client.post("/api/v1/auth/logout", json={}, headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", json={}, headers=headers).status_code == 200


# ------------------------------------------------------- change password --
def test_change_password_works_and_invalidates_other_sessions(client, org_setup):
    old = login(client, "owner@session.test")["data"]
    login(client, "owner@session.test")
    other = refresh_cookie(client)

    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": PASSWORD, "new_password": "Brand@New99"},
                    headers=auth(old["access_token"]))
    assert r.status_code == 200

    assert login(client, "owner@session.test", PASSWORD).get("success") is not True
    assert login(client, "owner@session.test", "Brand@New99")["success"] is True
    assert present_token_alone(client, other).status_code == 401


def test_change_password_rejects_a_wrong_current_password(client, org_setup):
    tokens = login(client, "owner@session.test")["data"]
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": "nope", "new_password": "Brand@New99"},
                    headers=auth(tokens["access_token"]))
    assert r.status_code == 401


def test_change_password_rejects_reusing_the_same_password(client, org_setup):
    tokens = login(client, "owner@session.test")["data"]
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": PASSWORD, "new_password": PASSWORD},
                    headers=auth(tokens["access_token"]))
    assert r.status_code == 409


def test_change_password_enforces_a_minimum_length(client, org_setup):
    tokens = login(client, "owner@session.test")["data"]
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": PASSWORD, "new_password": "short"},
                    headers=auth(tokens["access_token"]))
    assert r.status_code == 422


def test_must_change_password_flag_is_reported_then_cleared(client, db):
    """The temporary-password flow an owner will hit on first sign-in."""
    org = make_org(db, "Temp Password PG")
    role = make_role(db, org, "Owner", ["*"], all_branches=True)
    make_user(db, org, "new.owner@temp.test", role=role, must_change=True)
    db.commit()

    tokens = login(client, "new.owner@temp.test")["data"]
    assert tokens["user"]["must_change_password"] is True

    client.post("/api/v1/auth/change-password",
                json={"current_password": PASSWORD, "new_password": "Chosen@2024"},
                headers=auth(tokens["access_token"]))
    assert login(client, "new.owner@temp.test", "Chosen@2024")["data"]["user"][
        "must_change_password"] is False


# ------------------------------------------------- lost replies (the app's case)
NATIVE = {**CSRF, "X-PGDesk-Client": "native"}


def native_login(client) -> str:
    r = client.post("/api/v1/auth/login", headers={"X-PGDesk-Client": "native"},
                    json={"email": "owner@session.test", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]["refresh_token"]


def native_refresh(client, token: str):
    client.cookies.clear()
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token}, headers=NATIVE)


def test_a_retry_after_a_lost_reply_restores_the_session(client, org_setup):
    """
    The phone sends its token, the server rotates it, the reply never arrives
    (signal dropped, or a sleeping server answered after the app gave up). The
    app asks again with the same token. That is a retry, not a theft: it must
    get a session back, not sign the user out of every device.
    """
    t1 = native_login(client)
    lost = native_refresh(client, t1)
    assert lost.status_code == 200
    undelivered = lost.json()["data"]["refresh_token"]

    retry = native_refresh(client, t1)
    assert retry.status_code == 200, retry.text
    fresh = retry.json()["data"]["refresh_token"]
    assert fresh not in (t1, undelivered)
    assert native_refresh(client, fresh).status_code == 200


def test_the_undelivered_replacement_is_retired(client, org_setup):
    """Nobody legitimate holds it, so if it ever turns up, that is theft."""
    t1 = native_login(client)
    undelivered = native_refresh(client, t1).json()["data"]["refresh_token"]
    fresh = native_refresh(client, t1).json()["data"]["refresh_token"]

    assert native_refresh(client, undelivered).status_code == 401
    assert native_refresh(client, fresh).status_code == 401      # everyone signed out


def test_a_late_replay_still_signs_every_session_out(client, org_setup, db):
    from app.services import auth_service
    t1 = native_login(client)
    t2 = native_refresh(client, t1).json()["data"]["refresh_token"]
    row = db.query(RefreshToken).filter(
        RefreshToken.token_hash == auth_service.hash_token(t1)).one()
    row.revoked_at = row.revoked_at - timedelta(minutes=11)      # outside the grace window
    db.flush()

    assert native_refresh(client, t1).status_code == 401
    assert native_refresh(client, t2).status_code == 401
