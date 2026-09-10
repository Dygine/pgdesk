"""
QR sign-in, portal access after creation, and seeker accounts.

The portal-access tests exist because of a real gap: a resident added without
the "portal login" tick could never be given one afterwards, and ticking it
without an email silently created nobody.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import LoginCode
from app.models.otp import OtpPurpose
from app.services import geocode_service
from app.services.otp_service import OtpService
from app.utils import qr_payload
from tests.factories import (
    PASSWORD, make_branch, make_org, make_property, make_role, make_user,
)

API = "/api/v1"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, email: str, password: str = PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


@pytest.fixture
def pg(db, client):
    org = make_org(db, "QR PG")
    branch = make_branch(db, org, "Indiranagar", "IND")
    make_property(db, org, branch, beds=3, rent=8500)
    owner_role = make_role(db, org, "Owner", ["*"], all_branches=True, is_system=True)
    make_user(db, org, "owner@qrpg.in", role=owner_role)
    db.commit()
    token = login(client, "owner@qrpg.in").json()["data"]["access_token"]
    return dict(org=org, branch=branch, owner=token)


def _create(client, pg, **kw):
    body = {"first_name": "Ravi", "phone": "+919800000001",
            "branch_id": str(pg["branch"].id)}
    body.update(kw)
    return client.post(f"{API}/residents", json=body, headers=auth(pg["owner"]))


# ------------------------------------------------------------- QR sign-in
def test_qr_payload_knows_the_login_kind():
    assert qr_payload.parse("PGD1:L:abcdefgh12") == ("L", "abcdefgh12")
    assert qr_payload.encode(qr_payload.KIND_LOGIN, "xyz").startswith("PGD1:L:")


def test_new_resident_gets_a_qr_that_signs_in_exactly_once(client, pg):
    r = _create(client, pg, email="ravi@qrpg.in", create_portal_login=True)
    assert r.status_code == 201, r.text
    creds = r.json()["data"]["credentials"]
    assert creds["temporary_password"]
    assert creds["login_code"]["valid_minutes"] == 30
    code = creds["login_code"]["payload"]
    assert code.startswith("PGD1:L:")
    assert creds["temporary_password"] not in code      # the password never rides in the QR

    signed = client.post(f"{API}/auth/qr-login", json={"code": code})
    assert signed.status_code == 200, signed.text
    user = signed.json()["data"]["user"]
    assert user["portal"] == "customer"
    assert user["must_change_password"] is True

    again = client.post(f"{API}/auth/qr-login", json={"code": code})
    assert again.status_code == 401
    assert again.json()["code"] == "used_code"


def test_first_password_needs_no_current_one_and_keeps_this_device_signed_in(client, pg):
    created = _create(client, pg, email="meena@qrpg.in", create_portal_login=True).json()["data"]
    signed = client.post(f"{API}/auth/qr-login",
                         json={"code": created["credentials"]["login_code"]["payload"]}).json()["data"]

    r = client.post(f"{API}/auth/change-password", json={"new_password": "Meena@2026x"},
                    headers=auth(signed["access_token"]))
    assert r.status_code == 200, r.text
    fresh = r.json()["data"]
    assert fresh["user"]["must_change_password"] is False
    assert client.get(f"{API}/auth/me", headers=auth(fresh["access_token"])).status_code == 200
    assert login(client, "meena@qrpg.in", "Meena@2026x").status_code == 200

    # Once they have chosen a password, the PG cannot mint a QR into the account.
    blocked = client.post(f"{API}/residents/{created['id']}/login-code",
                          headers=auth(pg["owner"]))
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "password_already_set"


def test_an_ordinary_password_change_still_needs_the_current_password(client, pg):
    r = client.post(f"{API}/auth/change-password", json={"new_password": "Another@2026"},
                    headers=auth(pg["owner"]))
    assert r.status_code == 409


def test_replaced_and_expired_codes_are_refused(client, db, pg):
    created = _create(client, pg, email="kiran@qrpg.in", create_portal_login=True).json()["data"]
    first = created["credentials"]["login_code"]["payload"]
    renewed = client.post(f"{API}/residents/{created['id']}/login-code", headers=auth(pg["owner"]))
    assert renewed.status_code == 200, renewed.text
    second = renewed.json()["data"]["credentials"]["login_code"]["payload"]

    assert client.post(f"{API}/auth/qr-login", json={"code": first}).json()["code"] == "replaced_code"

    live = db.scalars(select(LoginCode).where(
        LoginCode.customer_id == uuid.UUID(created["id"]),
        LoginCode.used_at.is_(None), LoginCode.revoked_at.is_(None))).one()
    live.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.flush()
    r = client.post(f"{API}/auth/qr-login", json={"code": second})
    assert r.status_code == 401
    assert r.json()["code"] == "expired_code"


def test_a_gate_code_is_not_a_sign_in_code(client, pg):
    r = client.post(f"{API}/auth/qr-login", json={"code": "PGD1:G:somegatetoken123"})
    assert r.status_code == 401
    assert r.json()["code"] == "wrong_code"


# ------------------------------------------------ portal access, afterwards
def test_portal_access_can_be_given_after_the_resident_was_created(client, pg):
    created = _create(client, pg).json()["data"]
    assert created["has_portal_login"] is False

    r = client.post(f"{API}/residents/{created['id']}/portal-access", json={},
                    headers=auth(pg["owner"]))
    assert r.status_code == 409
    assert r.json()["code"] == "email_required"

    r = client.patch(f"{API}/residents/{created['id']}", json={"email": "Late@QRPG.in"},
                     headers=auth(pg["owner"]))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["email"] == "late@qrpg.in"

    r = client.post(f"{API}/residents/{created['id']}/portal-access", json={},
                    headers=auth(pg["owner"]))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["has_portal_login"] is True and data["must_change_password"] is True
    assert login(client, "late@qrpg.in",
                 data["credentials"]["temporary_password"]).status_code == 200


def test_portal_access_can_take_the_email_in_the_same_step(client, pg):
    created = _create(client, pg).json()["data"]
    r = client.post(f"{API}/residents/{created['id']}/portal-access",
                    json={"email": "sameStep@qrpg.in"}, headers=auth(pg["owner"]))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["email"] == "samestep@qrpg.in"


def test_a_login_email_cannot_collide_with_a_staff_login(client, pg):
    created = _create(client, pg).json()["data"]
    r = client.post(f"{API}/residents/{created['id']}/portal-access",
                    json={"email": "owner@qrpg.in"}, headers=auth(pg["owner"]))
    assert r.status_code == 409


def test_ticking_portal_login_without_an_email_is_refused_not_skipped(client, pg):
    r = _create(client, pg, create_portal_login=True)
    assert r.status_code == 409


def test_the_email_cannot_be_removed_while_it_is_the_sign_in_id(client, pg):
    created = _create(client, pg, email="keep@qrpg.in", create_portal_login=True).json()["data"]
    r = client.patch(f"{API}/residents/{created['id']}", json={"email": None},
                     headers=auth(pg["owner"]))
    assert r.status_code == 409


def test_reset_and_turning_access_off(client, pg):
    created = _create(client, pg, email="asha@qrpg.in", create_portal_login=True).json()["data"]
    rid = created["id"]

    reset = client.post(f"{API}/residents/{rid}/reset-password", headers=auth(pg["owner"]))
    assert reset.status_code == 200, reset.text
    new_password = reset.json()["data"]["credentials"]["temporary_password"]
    assert login(client, "asha@qrpg.in",
                 created["credentials"]["temporary_password"]).status_code == 401
    assert login(client, "asha@qrpg.in", new_password).status_code == 200

    off = client.delete(f"{API}/residents/{rid}/portal-access", headers=auth(pg["owner"]))
    assert off.status_code == 200
    assert off.json()["data"]["has_portal_login"] is False
    assert login(client, "asha@qrpg.in", new_password).status_code == 401
    code = reset.json()["data"]["credentials"]["login_code"]["payload"]
    assert client.post(f"{API}/auth/qr-login", json={"code": code}).status_code == 401


# ------------------------------------------------------------ seekers
def _verified(db, email: str) -> str:
    otp = OtpService(db)
    code = otp.issue(email=email, purpose=OtpPurpose.SIGNUP_EMAIL)
    return otp.verify(email=email, purpose=OtpPurpose.SIGNUP_EMAIL, code=code)


@pytest.fixture
def listed(db):
    org = make_org(db, "Listed PG")
    branch = make_branch(db, org, "HSR Layout", "HSR")
    branch.listed_publicly = True
    branch.latitude, branch.longitude = 12.9121, 77.6446
    branch.contact_phone_public = "+919812345678"
    make_property(db, org, branch, beds=2, rent=7500)
    db.commit()
    return branch


def test_a_seeker_signs_up_once_and_enquires_without_new_codes(client, db, listed):
    token = _verified(db, "seeker@find.test")

    r = client.post(f"{API}/public/seeker/session", json={"verification_token": token})
    assert r.status_code == 409
    assert r.json()["code"] == "needs_profile"      # and the token survives

    r = client.post(f"{API}/public/seeker/session", json={
        "verification_token": token, "full_name": "Neha Rao", "phone": "+919876500000"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["created"] is True
    h = {"X-PGDesk-Seeker": data["token"]}

    assert client.get(f"{API}/public/seeker/me", headers=h).json()["data"]["full_name"] == "Neha Rao"
    for _ in range(2):
        e = client.post(f"{API}/public/seeker/enquiries",
                        json={"branch_id": str(listed.id), "message": "Double sharing?"},
                        headers=h)
        assert e.status_code == 201, e.text

    mine = client.get(f"{API}/public/seeker/enquiries", headers=h).json()["data"]
    assert len(mine) == 1                      # the repeat folded into one lead
    assert mine[0]["pg_name"] == "Listed PG"
    assert mine[0]["contact_phone"] == "+919812345678"

    client.post(f"{API}/public/seeker/logout", headers=h)
    assert client.get(f"{API}/public/seeker/me", headers=h).status_code == 401


def test_seeker_endpoints_need_a_session(client):
    assert client.get(f"{API}/public/seeker/me").status_code == 401
    assert client.get(f"{API}/public/seeker/me",
                      headers={"X-PGDesk-Seeker": "not-a-token"}).status_code == 401


def test_listings_show_room_types_as_bands_never_counts(client, listed):
    r = client.get(f"{API}/public/pgs",
                   params={"latitude": 12.91, "longitude": 77.64, "radius_km": 5})
    assert r.status_code == 200, r.text
    pg = next(p for p in r.json()["data"] if p["id"] == str(listed.id))
    assert pg["pg_name"] == "Listed PG"
    option = pg["room_options"][0]
    assert option["room_type"] == "Double sharing"
    assert option["from_rent"] == 7500
    assert option["vacancy"] == "a few beds"
    assert not any(isinstance(v, int) and k not in ("sharing",) for k, v in option.items()
                   if k != "from_rent")


def test_area_search_falls_back_to_listings_when_the_geocoder_is_down(client, listed,
                                                                     monkeypatch):
    def down(*_, **__):
        raise geocode_service.GeocodeUnavailable("down")

    monkeypatch.setattr(geocode_service, "search_places", down)
    r = client.get(f"{API}/public/places", params={"q": "Bengaluru"})
    assert r.status_code == 200, r.text
    places = r.json()["data"]["places"]
    assert any(p["latitude"] == listed.latitude for p in places)
