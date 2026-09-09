"""Small builders so auth tests read as scenarios rather than ORM setup."""
import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Branch, Customer, Organization, Permission, Role, Subscription, SubscriptionPlan, User,
)
from app.models.enums import (
    BillingCycle, BranchStatus, CustomerStatus, OrganizationStatus,
    PlanStatus, SubscriptionStatus, UserStatus,
)
from app.permissions.catalog import catalog_rows
from app.permissions.engine import expand

PASSWORD = "Test@12345"


def ensure_permissions(db: Session) -> dict[str, Permission]:
    existing = {p.code: p for p in db.query(Permission).all()}
    for row in catalog_rows():
        if row["code"] not in existing:
            perm = Permission(**row)
            db.add(perm)
            existing[row["code"]] = perm
    db.flush()
    return existing


def make_plan(db: Session, name: str = "Test Plan") -> SubscriptionPlan:
    plan = SubscriptionPlan(
        code=f"plan_{uuid.uuid4().hex[:8]}", name=f"{name} {uuid.uuid4().hex[:4]}",
        price=999, billing_cycle=BillingCycle.MONTHLY, status=PlanStatus.ACTIVE,
        max_branches=3, max_users=10, max_beds=100, max_customers=100, storage_limit_gb=5,
    )
    db.add(plan)
    db.flush()
    return plan


def make_org(db: Session, name: str, status=OrganizationStatus.ACTIVE,
             with_subscription: bool = True) -> Organization:
    org = Organization(
        name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
        owner_name=f"{name} Owner", owner_email=f"owner@{uuid.uuid4().hex[:6]}.test",
        status=status, city="Bengaluru",
    )
    db.add(org)
    db.flush()
    if with_subscription:
        db.add(Subscription(
            organization_id=org.id, plan_id=make_plan(db).id,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=300),
            status=SubscriptionStatus.ACTIVE, is_current=True,
        ))
        db.flush()
    return org


def make_branch(db: Session, org: Organization, name: str, code: str) -> Branch:
    branch = Branch(organization_id=org.id, name=name, code=code,
                    city="Bengaluru", status=BranchStatus.ACTIVE)
    db.add(branch)
    db.flush()
    return branch


def make_role(db: Session, org: Organization, name: str, permissions: list[str],
              all_branches: bool = False, is_system: bool = False) -> Role:
    perms = ensure_permissions(db)
    role = Role(organization_id=org.id, name=name, description=name,
                all_branches=all_branches, is_system_role=is_system)
    role.permissions = [perms[c] for c in sorted(expand(permissions)) if c in perms]
    db.add(role)
    db.flush()
    return role


def make_user(db: Session, org: Organization | None, email: str, *, role: Role | None = None,
              branches: list[Branch] | None = None, password: str = PASSWORD,
              status: str = UserStatus.ACTIVE, is_master: bool = False,
              is_active: bool = True, must_change: bool = False) -> User:
    user = User(
        organization_id=None if is_master else (org.id if org else None),
        name=email.split("@")[0].replace(".", " ").title(), email=email,
        phone="+91 9800000000", password_hash=hash_password(password),
        status=status, is_active=is_active, is_master_admin=is_master,
        must_change_password=must_change,
    )
    db.add(user)
    db.flush()
    if role:
        user.roles = [role]
    if branches:
        user.branches = branches
    db.flush()
    return user


def make_customer(db: Session, org: Organization, email: str, *, branch: Branch | None = None,
                  password: str | None = PASSWORD, status: str = CustomerStatus.ACTIVE,
                  is_active: bool = True) -> Customer:
    cust = Customer(
        organization_id=org.id, branch_id=branch.id if branch else None,
        full_name=email.split("@")[0].title(), email=email, phone="+91 9812000000",
        password_hash=hash_password(password) if password else None,
        status=status, is_active=is_active,
    )
    db.add(cust)
    db.flush()
    return cust


# --------------------------------------------------------------- property
def make_building(db: Session, org: Organization, branch: Branch,
                  name: str = "Block A", code: str = "A") -> "Building":
    from app.models import Building
    b = Building(organization_id=org.id, branch_id=branch.id, name=name,
                 code=f"{code}{uuid.uuid4().hex[:4]}")
    db.add(b)
    db.flush()
    return b


def make_floor(db: Session, org: Organization, branch: Branch, building,
               number: int = 1) -> "Floor":
    from app.models import Floor
    f = Floor(organization_id=org.id, branch_id=branch.id, building_id=building.id,
              floor_number=number, name=f"Floor {number}")
    db.add(f)
    db.flush()
    return f


def make_room(db: Session, org: Organization, branch: Branch, building, floor,
              number: str = "101", rent: float = 9000) -> "Room":
    from app.models import Room
    r = Room(organization_id=org.id, branch_id=branch.id, building_id=building.id,
             floor_id=floor.id, room_number=number, room_type="Double sharing",
             rent_amount=rent)
    db.add(r)
    db.flush()
    return r


def make_bed(db: Session, org: Organization, branch: Branch, room,
             number: str = "A", rent: float = 9000, status=None) -> "Bed":
    from app.models import Bed
    from app.models.enums import BedStatus
    bed = Bed(organization_id=org.id, branch_id=branch.id, room_id=room.id,
              bed_number=number, bed_code=f"{room.room_number}-{number}",
              rent_amount=rent, status=status or BedStatus.AVAILABLE)
    db.add(bed)
    db.flush()
    return bed


def make_property(db: Session, org: Organization, branch: Branch, *,
                  beds: int = 2, rent: float = 9000) -> dict:
    """A branch with one building, one floor, one room and `beds` beds in it."""
    building = make_building(db, org, branch)
    floor = make_floor(db, org, branch, building)
    room = make_room(db, org, branch, building, floor, rent=rent)
    made = [make_bed(db, org, branch, room, number=chr(ord("A") + i), rent=rent)
            for i in range(beds)]
    return {"building": building, "floor": floor, "room": room, "beds": made}
