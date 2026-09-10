"""
Scanned ID documents: three per resident, images only, 5 KB each - strictly.

"Strictly" is tested at every layer: the API refuses 5,121 bytes, and the
database refuses it too even when the API is bypassed entirely.
"""
import base64

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import ResidentDocument
from app.models.enums import CustomerStatus
from tests.factories import PASSWORD, make_branch, make_customer, make_org, make_role, make_user

API = "/api/v1"
LIMIT = 5 * 1024


def jpeg(size: int) -> str:
    """A body that sniffs as JPEG, exactly `size` bytes, as a data URL."""
    raw = b"\xff\xd8\xff\xe0" + b"\x00" * (size - 4)
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def login(client, email):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.fixture
def setup(db, client):
    org = make_org(db, "Docs PG")
    other = make_org(db, "Other PG")
    branch = make_branch(db, org, "Main", "MAIN")
    make_branch(db, other, "Else", "ELSE")
    make_user(db, org, "owner@docs.test",
              role=make_role(db, org, "Owner", ["*"], all_branches=True, is_system=True))
    make_user(db, org, "desk@docs.test", role=make_role(
        db, org, "Desk", ["customers.view", "customers.edit"], all_branches=True))
    make_user(db, other, "owner@other.test",
              role=make_role(db, other, "Owner", ["*"], all_branches=True, is_system=True))
    resident = make_customer(db, org, "ravi@docs.test", branch=branch,
                             status=CustomerStatus.ACTIVE)
    db.commit()
    return {"resident": resident, "owner": login(client, "owner@docs.test"),
            "desk": login(client, "desk@docs.test"), "other": login(client, "owner@other.test")}


def url(s):
    return f"{API}/residents/{s['resident'].id}/documents"


def test_a_document_up_to_exactly_5kb_is_saved_and_shown(client, setup):
    r = client.post(url(setup), headers=setup["owner"],
                    json={"doc_type": "AADHAAR", "label": "Front", "image": jpeg(LIMIT)})
    assert r.status_code == 201, r.text
    assert r.json()["data"]["size_bytes"] == LIMIT
    listed = client.get(url(setup), headers=setup["owner"]).json()["data"]
    assert listed["max_bytes"] == LIMIT and listed["max_documents"] == 3
    assert listed["items"][0]["data_url"].startswith("data:image/jpeg;base64,")


def test_one_byte_over_5kb_is_refused(client, setup):
    r = client.post(url(setup), headers=setup["owner"],
                    json={"doc_type": "PAN", "image": jpeg(LIMIT + 1)})
    assert r.status_code == 400
    assert r.json()["code"] == "document_too_large"
    assert "under 5 KB" in r.json()["message"]


def test_a_fourth_document_is_refused(client, setup):
    for kind in ("AADHAAR", "PAN", "OTHER"):
        assert client.post(url(setup), headers=setup["owner"],
                           json={"doc_type": kind, "image": jpeg(900)}).status_code == 201
    r = client.post(url(setup), headers=setup["owner"],
                    json={"doc_type": "PASSPORT", "image": jpeg(900)})
    assert r.status_code == 409 and r.json()["code"] == "document_limit"


def test_only_real_images_are_accepted(client, setup):
    pdf = "data:image/jpeg;base64," + base64.b64encode(b"%PDF-1.4 fake").decode()
    r = client.post(url(setup), headers=setup["owner"], json={"doc_type": "PAN", "image": pdf})
    assert r.status_code == 400 and r.json()["code"] == "document_type"


def test_the_image_needs_the_kyc_view_permission(client, setup):
    client.post(url(setup), headers=setup["owner"], json={"doc_type": "PAN", "image": jpeg(500)})
    desk = client.get(url(setup), headers=setup["desk"]).json()["data"]
    assert desk["can_view_images"] is False
    assert len(desk["items"]) == 1 and "data_url" not in desk["items"][0]


def test_another_pg_cannot_see_or_add_documents(client, setup):
    assert client.get(url(setup), headers=setup["other"]).status_code == 404
    assert client.post(url(setup), headers=setup["other"],
                       json={"doc_type": "PAN", "image": jpeg(500)}).status_code == 404


def test_deleting_frees_a_slot(client, setup):
    ids = [client.post(url(setup), headers=setup["owner"],
                       json={"doc_type": "OTHER", "image": jpeg(400)}).json()["data"]["id"]
           for _ in range(3)]
    assert client.delete(f"{url(setup)}/{ids[0]}", headers=setup["owner"]).status_code == 200
    assert client.post(url(setup), headers=setup["owner"],
                       json={"doc_type": "PAN", "image": jpeg(400)}).status_code == 201


def test_the_database_itself_refuses_an_oversized_document(db, setup):
    row = ResidentDocument(
        organization_id=setup["resident"].organization_id, resident_id=setup["resident"].id,
        doc_type="PAN", mime_type="image/jpeg", size_bytes=100,       # the size lies...
        content=b"\xff\xd8\xff" + b"\x00" * LIMIT)                    # ...the bytes do not
    db.add(row)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
