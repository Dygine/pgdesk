"""
The resident portal.

The guarantee this file exists to prove: a resident sees their own record and
nothing else, and there is no parameter in the request they could change to see
somebody else's. Every /me/* endpoint derives the resident from the token, so
the attack surface is the token itself rather than an id in a path.

Also covered: the KYC number is never sent to the portal. A resident already
knows their own Aadhaar; echoing it back only puts it into response logs, proxy
caches and screenshots for no benefit at all.
"""
import pytest

from app.models import ResidentKyc
from app.models.enums import CustomerStatus, KycIdType, KycStatus
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
def portal(db, client):
    org = make_org(db, "Sunrise PG")
    other = make_org(db, "Rival PG")
    branch = make_branch(db, org, "Koramangala", "KOR")
    other_branch = make_branch(db, other, "Indiranagar", "IND")
    prop = make_property(db, org, branch, beds=2, rent=9000)

    owner_role = make_role(db, org, "Owner", ["*"], all_branches=True, is_system=True)
    make_user(db, org, "owner@sunrise.test", role=owner_role)

    me = make_customer(db, org, "arjun@sunrise.test", branch=branch,
                       status=CustomerStatus.ACTIVE)
    me.full_name = "Arjun Rao"
    me.occupation = "Backend engineer"
    me.emergency_contact_name = "Latha Rao"
    me.emergency_contact_phone = "+91 9800000111"
    me.emergency_contact_relation = "Mother"
    me.monthly_rent = 9000
    me.security_deposit = 18000
    me.meal_plan = "Two meals"
    me.bed_id = prop["beds"][0].id
    me.room_id = prop["room"].id

    neighbour = make_customer(db, org, "neha@sunrise.test", branch=branch,
                              status=CustomerStatus.ACTIVE)
    neighbour.full_name = "Neha Sharma"

    stranger = make_customer(db, other, "raj@rival.test", branch=other_branch,
                             status=CustomerStatus.ACTIVE)

    db.add(ResidentKyc(
        organization_id=org.id, resident_id=me.id, id_type=KycIdType.AADHAAR,
        id_number="4321 8765 9012", status=KycStatus.VERIFIED))
    db.commit()

    return dict(org=org, me=me, neighbour=neighbour, stranger=stranger,
                token=login(client, "arjun@sunrise.test"),
                neighbour_token=login(client, "neha@sunrise.test"),
                staff_token=login(client, "owner@sunrise.test"))


# ------------------------------------------------------------- own record
def test_a_resident_sees_their_own_profile(client, portal):
    r = client.get(f"{API}/me/profile", headers=auth(portal["token"]))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "Arjun Rao"
    assert data["occupation"] == "Backend engineer"
    assert data["emergency_contact"]["name"] == "Latha Rao"
    assert data["stay"]["monthly_rent"] == 9000
    assert data["stay"]["meal_plan"] == "Two meals"


def test_two_residents_get_two_different_profiles(client, portal):
    """
    Same endpoint, same absence of parameters, different answers - which is the
    whole point of deriving identity from the token.
    """
    mine = client.get(f"{API}/me/profile", headers=auth(portal["token"]))
    theirs = client.get(f"{API}/me/profile", headers=auth(portal["neighbour_token"]))
    assert mine.json()["data"]["name"] == "Arjun Rao"
    assert theirs.json()["data"]["name"] == "Neha Sharma"
    assert mine.json()["data"]["id"] != theirs.json()["data"]["id"]


def test_the_profile_response_names_nobody_else(client, portal):
    body = client.get(f"{API}/me/profile", headers=auth(portal["token"])).text
    assert "Neha Sharma" not in body
    assert str(portal["neighbour"].id) not in body
    assert str(portal["stranger"].id) not in body


# ------------------------------------------------------------ kyc secrecy
def test_the_kyc_number_is_never_sent_to_the_portal(client, portal):
    r = client.get(f"{API}/me/profile", headers=auth(portal["token"]))
    body = r.text
    assert "4321" not in body, "the KYC number reached the resident portal"

    identity = r.json()["data"]["identity"]
    assert identity and identity[0]["id_type"] == KycIdType.AADHAAR
    assert identity[0]["status"] == KycStatus.VERIFIED
    assert "id_number" not in identity[0]


# --------------------------------------------------------- token confusion
def test_a_staff_token_cannot_read_the_resident_portal(client, portal):
    """
    Refused at the identity layer rather than by an empty permission set, so a
    handler that forgets to check cannot mistake one principal for the other.
    """
    r = client.get(f"{API}/me/profile", headers=auth(portal["staff_token"]))
    assert r.status_code == 403


def test_a_resident_token_cannot_reach_a_staff_endpoint(client, portal):
    assert client.get(f"{API}/residents",
                      headers=auth(portal["token"])).status_code == 403
    assert client.get(f"{API}/search", params={"q": "Neha"},
                      headers=auth(portal["token"])).status_code == 403


def test_the_profile_endpoint_requires_a_token(client, portal):
    assert client.get(f"{API}/me/profile").status_code == 401


# ------------------------------------------------------------ suspension
def test_a_deactivated_resident_loses_portal_access(db, client, portal):
    portal["me"].is_active = False
    db.commit()
    r = client.get(f"{API}/me/profile", headers=auth(portal["token"]))
    assert r.status_code == 401


# --------------------------------------------------------- announcements
def test_announcements_are_scoped_to_the_residents_organisation(db, client, portal):
    from app.models import Announcement
    from app.models.enums import AnnouncementAudience, PublishStatus

    db.add(Announcement(
        organization_id=portal["org"].id, title="Water cut on Sunday",
        message="Tank cleaning between 9am and 1pm.",
        audience=AnnouncementAudience.ALL, status=PublishStatus.PUBLISHED))
    db.add(Announcement(
        organization_id=portal["stranger"].organization_id,
        title="Rival PG staff party",
        message="Not for Sunrise residents.",
        audience=AnnouncementAudience.ALL, status=PublishStatus.PUBLISHED))
    db.commit()

    rows = client.get(f"{API}/me/announcements",
                      headers=auth(portal["token"])).json()["data"]
    titles = {a["title"] for a in rows}
    assert "Water cut on Sunday" in titles
    assert "Rival PG staff party" not in titles


def test_unpublished_announcements_stay_hidden(db, client, portal):
    from app.models import Announcement
    from app.models.enums import AnnouncementAudience, PublishStatus

    db.add(Announcement(
        organization_id=portal["org"].id, title="Draft rent revision",
        message="Not ready to send.",
        audience=AnnouncementAudience.ALL, status=PublishStatus.DRAFT))
    db.commit()

    rows = client.get(f"{API}/me/announcements",
                      headers=auth(portal["token"])).json()["data"]
    assert "Draft rent revision" not in {a["title"] for a in rows}
