"""Connectivity and the schema-level guarantees Milestone 1 promises."""
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.database import check_database_connection, engine
from app.models import Branch, Organization, User
from app.models.enums import OrganizationStatus, UserStatus


def test_database_reachable():
    connected, detail = check_database_connection()
    assert connected, f"database unreachable: {detail}"


def test_expected_tables_exist():
    """
    Inspects the engine the suite actually built its schema on.

    This previously inspected `app.core.database.engine` - the *application*
    engine, which points at the development database. That made the test pass
    or fail depending on whether the person running it happened to have migrated
    their local dev database, which is not something a test should depend on.
    """
    from tests.conftest import engine as test_engine

    tables = set(inspect(test_engine).get_table_names())
    expected = {
        "organizations", "subscription_plans", "subscriptions", "branches",
        "users", "roles", "permissions", "role_permissions", "user_roles",
        "user_branches", "audit_logs",
    }
    assert expected <= tables, f"missing: {expected - tables}"


def _org(db, name="Acme PG", slug=None):
    org = Organization(
        name=name, slug=slug or name.lower().replace(" ", "-"),
        owner_name="Owner", owner_email="owner@example.com",
        status=OrganizationStatus.ACTIVE,
    )
    db.add(org)
    db.flush()
    return org


def test_uuid_primary_keys_are_generated(db):
    org = _org(db)
    assert isinstance(org.id, uuid.UUID)


def test_timestamps_populate(db):
    org = _org(db, "Timestamp PG")
    assert org.created_at is not None
    assert org.updated_at is not None


def test_branch_code_unique_within_org_but_reusable_across_orgs(db):
    a = _org(db, "Org A", "org-a")
    b = _org(db, "Org B", "org-b")

    db.add(Branch(organization_id=a.id, name="Koramangala", code="KOR"))
    db.flush()

    # Same code in a different tenant is fine - codes are not globally unique.
    db.add(Branch(organization_id=b.id, name="Koramangala", code="KOR"))
    db.flush()

    # ... but a duplicate inside one tenant must be rejected by the database.
    db.add(Branch(organization_id=a.id, name="Koramangala Two", code="KOR"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_non_master_user_must_belong_to_an_organization(db):
    """The CHECK constraint, not application code, enforces this."""
    db.add(User(
        organization_id=None, name="Orphan", email="orphan@example.com",
        password_hash="x", is_master_admin=False, status=UserStatus.ACTIVE,
    ))
    with pytest.raises(IntegrityError):
        db.flush()


def test_master_admin_must_not_belong_to_an_organization(db):
    org = _org(db, "Master Check PG", "master-check")
    db.add(User(
        organization_id=org.id, name="Bad Master", email="bad@example.com",
        password_hash="x", is_master_admin=True, status=UserStatus.ACTIVE,
    ))
    with pytest.raises(IntegrityError):
        db.flush()


def test_user_email_unique_per_tenant_not_globally(db):
    a = _org(db, "Email A", "email-a")
    b = _org(db, "Email B", "email-b")

    db.add(User(organization_id=a.id, name="P", email="same@example.com", password_hash="x"))
    db.flush()
    db.add(User(organization_id=b.id, name="P", email="same@example.com", password_hash="x"))
    db.flush()      # allowed: different tenants

    db.add(User(organization_id=a.id, name="P2", email="same@example.com", password_hash="x"))
    with pytest.raises(IntegrityError):
        db.flush()
