"""
Platform settings.

The screen this backs previously had a Save button that only set React state and
showed a success toast. So the tests that matter are the ones proving a value
survives the request: written, re-read, still there.

The other half is honesty about notification channels. The stored toggle records
what an operator wants; `channels` reports what the deployment can actually
send. A build that collapses those into one flag tells an operator a message
went out when nothing did.
"""
import pytest

from app.models import PlatformSettings
from app.models.platform import SINGLETON_ID
from tests.factories import PASSWORD, make_org, make_role, make_user

API = "/api/v1"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, email: str) -> str:
    r = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


@pytest.fixture
def actors(db, client):
    org = make_org(db, "Sunrise PG")
    owner_role = make_role(db, org, "Owner", ["*"], all_branches=True, is_system=True)
    make_user(db, org, "owner@sunrise.test", role=owner_role)
    make_user(db, None, "root@pgdesk.test", is_master=True)
    db.commit()
    return dict(master=login(client, "root@pgdesk.test"),
                owner=login(client, "owner@sunrise.test"))


# ------------------------------------------------------------ persistence
def test_settings_are_created_on_first_read(db, client, actors):
    """
    No data migration seeds the row, so a fresh database and an upgraded one
    behave the same: the first GET materialises it.
    """
    assert db.get(PlatformSettings, __import__("uuid").UUID(SINGLETON_ID)) is None
    r = client.get(f"{API}/master/settings", headers=auth(actors["master"]))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["default_trial_days"] == 14


def test_a_saved_value_survives_a_re_read(client, actors):
    """The failure this exists to catch: a save that only lived in the browser."""
    patch = client.patch(f"{API}/master/settings",
                         json={"default_trial_days": 30, "grace_period_days": 15},
                         headers=auth(actors["master"]))
    assert patch.status_code == 200, patch.text
    assert patch.json()["data"]["default_trial_days"] == 30

    again = client.get(f"{API}/master/settings", headers=auth(actors["master"]))
    assert again.json()["data"]["default_trial_days"] == 30
    assert again.json()["data"]["grace_period_days"] == 15


def test_a_partial_patch_leaves_other_fields_alone(client, actors):
    client.patch(f"{API}/master/settings", json={"default_trial_days": 30},
                 headers=auth(actors["master"]))
    client.patch(f"{API}/master/settings", json={"platform_name": "Sunrise Cloud"},
                 headers=auth(actors["master"]))
    data = client.get(f"{API}/master/settings",
                      headers=auth(actors["master"])).json()["data"]
    assert data["platform_name"] == "Sunrise Cloud"
    assert data["default_trial_days"] == 30


def test_only_one_settings_row_can_exist(db, client, actors):
    client.get(f"{API}/master/settings", headers=auth(actors["master"]))
    client.patch(f"{API}/master/settings", json={"default_trial_days": 7},
                 headers=auth(actors["master"]))
    assert db.query(PlatformSettings).count() == 1


# ------------------------------------------------------------- validation
@pytest.mark.parametrize("payload", [
    {"default_trial_days": -1},
    {"default_trial_days": 400},
    {"grace_period_days": 91},
    {"expiry_warning_days": -5},
    {"support_email": "not-an-email"},
    {"platform_name": ""},
])
def test_out_of_range_values_are_refused(client, actors, payload):
    """
    Bounds mirror the CHECK constraints, so a bad value fails readably at the
    edge instead of as a database error from deep inside the request.
    """
    r = client.patch(f"{API}/master/settings", json=payload,
                     headers=auth(actors["master"]))
    assert r.status_code == 422, f"{payload} was accepted"


def test_a_rejected_patch_changes_nothing(client, actors):
    before = client.get(f"{API}/master/settings",
                        headers=auth(actors["master"])).json()["data"]
    client.patch(f"{API}/master/settings", json={"grace_period_days": 999},
                 headers=auth(actors["master"]))
    after = client.get(f"{API}/master/settings",
                       headers=auth(actors["master"])).json()["data"]
    assert after["grace_period_days"] == before["grace_period_days"]


# ---------------------------------------------------------- authorisation
def test_a_pg_owner_cannot_read_platform_settings(client, actors):
    assert client.get(f"{API}/master/settings",
                      headers=auth(actors["owner"])).status_code == 403


def test_a_pg_owner_cannot_write_platform_settings(client, actors):
    r = client.patch(f"{API}/master/settings", json={"default_trial_days": 365},
                     headers=auth(actors["owner"]))
    assert r.status_code == 403


def test_anonymous_access_is_rejected(client, actors):
    assert client.get(f"{API}/master/settings").status_code == 401


# -------------------------------------------------------- channel honesty
def test_channels_report_configuration_not_the_toggle(client, actors, monkeypatch):
    """
    Switching WhatsApp on must not make the deployment claim it can send. The
    toggle is intent; `channels` is capability; they are reported separately.
    """
    monkeypatch.delenv("WHATSAPP_PROVIDER_KEY", raising=False)
    r = client.patch(f"{API}/master/settings",
                     json={"notify_whatsapp_enabled": True},
                     headers=auth(actors["master"]))
    data = r.json()["data"]
    assert data["notify_whatsapp_enabled"] is True
    assert data["channels"]["whatsapp"]["configured"] is False


def test_a_configured_provider_is_reported_as_available(client, actors, monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER_KEY", "test-key")
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "12345")
    data = client.get(f"{API}/master/settings",
                      headers=auth(actors["master"])).json()["data"]
    assert data["channels"]["whatsapp"]["configured"] is True


def test_in_app_notifications_are_always_available(client, actors):
    """They are database rows, so there is no provider to be missing."""
    data = client.get(f"{API}/master/settings",
                      headers=auth(actors["master"])).json()["data"]
    assert data["channels"]["in_app"]["configured"] is True


# --------------------------------------------------------------- auditing
def test_a_settings_change_is_audited(db, client, actors):
    from app.models import AuditLog

    client.patch(f"{API}/master/settings", json={"default_trial_days": 30},
                 headers=auth(actors["master"]))
    entry = db.query(AuditLog).filter(AuditLog.module == "Platform").first()
    assert entry is not None
    assert "default_trial_days" in entry.description
