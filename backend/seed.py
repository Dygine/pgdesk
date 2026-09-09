"""
Development seed. Idempotent: run it as many times as you like.

Milestone 1 seeds everything the foundation tables can hold:
  * the 4 subscription plans (mirroring src/data/plans.js)
  * the full permission catalogue (mirroring src/data/permissions.js)
  * one master admin
  * Sunrise Living PG with its Professional subscription and 3 branches
  * the 7 roles and 9 staff users the React demo already uses

Rooms, beds, residents, invoices and the rest arrive with the milestones that
introduce their tables.

    python seed.py            # insert or update
    python seed.py --reset    # delete tenant data first, then seed

Every credential here is fictional and for development only.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.security import hash_password
from app.services.resident_service import generate_qr_token
from app.models import (
    AuditLog, Bed, Branch, Building, Customer, Floor, Organization, Permission,
    RefreshToken, Role, Room, Subscription, SubscriptionPlan, User,
)
from app.models.enums import (
    BedStatus, BillingCycle, BranchStatus, BuildingStatus, CustomerStatus,
    FloorStatus, GenderPolicy, OrganizationStatus, PlanStatus, RoomStatus,
    SubscriptionStatus, UserStatus,
)
from app.permissions.catalog import MASTER_PERMISSIONS, catalog_rows
from app.permissions.engine import expand
from app.utils.slugs import slugify

TODAY = date.today()

# ---------------------------------------------------------------------------
# DEVELOPMENT CREDENTIALS ONLY.
#
# Distinct per role rather than one shared password, so that a test which passes
# by accident (wrong account, right password) fails instead. Every one of these
# is fictional and must never appear in a deployed environment.
# ---------------------------------------------------------------------------
DEMO_PASSWORDS = {
    "master": "Master@2024",
    "owner": "Owner@2024",
    "manager": "Manager@2024",
    "staff": "Staff@2024",
    "customer": "Customer@2024",
}


def d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


# --------------------------------------------------------------------- plans
PLANS = [
    dict(code="plan_starter", name="Starter", price=1499, support_level="Email", sort_order=1,
         max_branches=1, max_buildings=2, max_floors=8, max_rooms=25, max_beds=60,
         max_customers=60, max_users=5, max_admins=1, storage_limit_gb=2,
         monthly_transaction_limit=500,
         features=["Rooms & beds", "Residents", "Rent & payments", "Complaints", "Basic reports"]),
    dict(code="plan_growth", name="Growth", price=2499, support_level="Email", sort_order=2,
         max_branches=3, max_buildings=6, max_floors=24, max_rooms=100, max_beds=300,
         max_customers=300, max_users=15, max_admins=3, storage_limit_gb=5,
         monthly_transaction_limit=2000,
         features=["Everything in Starter", "Multi-branch", "Custom roles", "Attendance"]),
    dict(code="plan_professional", name="Professional", price=3999,
         support_level="Email + phone", sort_order=3,
         max_branches=3, max_buildings=9, max_floors=36, max_rooms=150, max_beds=300,
         max_customers=300, max_users=20, max_admins=5, storage_limit_gb=10,
         monthly_transaction_limit=5000,
         features=["Everything in Growth", "Food & laundry", "Visitors & gate passes",
                   "Expense tracking", "QR gate"]),
    dict(code="plan_business", name="Business", price=8999, support_level="Priority",
         sort_order=4,
         max_branches=10, max_buildings=30, max_floors=120, max_rooms=600, max_beds=1200,
         max_customers=1200, max_users=75, max_admins=15, storage_limit_gb=50,
         monthly_transaction_limit=20000,
         features=["Everything in Professional", "Assets & inventory", "Advanced reports",
                   "Audit log export", "Announcement targeting"]),
    dict(code="plan_enterprise", name="Enterprise", price=19999,
         support_level="Dedicated manager", sort_order=5,
         max_branches=50, max_buildings=150, max_floors=600, max_rooms=4000, max_beds=8000,
         max_customers=8000, max_users=400, max_admins=60, storage_limit_gb=250,
         monthly_transaction_limit=100000,
         features=["Everything in Business", "Franchise grouping", "API access",
                   "Custom SLA", "Onboarding assistance"]),
]

# ---------------------------------------------------------------- roles
def P(module: str, *actions: str) -> list[str]:
    return [f"{module}.{a}" for a in actions]


ROLES = [
    dict(name="Owner", is_system_role=True, all_branches=True,
         description="Full control of the organisation, every branch.",
         permissions=["*"]),
    dict(name="Branch Manager", is_system_role=False, all_branches=False,
         description="Runs day-to-day operations at assigned branches.",
         permissions=[
             "dashboard.view", *P("branches", "view"), *P("property", "view"),
             *P("buildings", "view", "create", "edit"), *P("floors", "view", "create", "edit"),
             *P("rooms", "view", "create", "edit"),
             *P("beds", "view", "create", "edit", "assign", "transfer", "block"),
             *P("customers", "view", "create", "edit", "checkin", "checkout", "transfer"),
             *P("invoices", "view", "create"), *P("payments", "view", "create"),
             *P("complaints", "view", "create", "assign", "update", "close"),
             *P("food", "view", "create", "edit", "publish"), *P("laundry", "view", "manage"),
             *P("attendance", "view", "mark", "edit"), *P("visitors", "view", "create", "approve", "checkin"),
             *P("gatepass", "view", "create", "approve"), *P("announcements", "view", "create", "publish"),
             *P("queries", "view", "reply", "close"), *P("staff", "view"),
             *P("reports", "view", "export"), *P("expenses", "view", "create"),
             *P("inventory", "view"), *P("assets", "view"), *P("users", "view"),
         ]),
    dict(name="Accountant", is_system_role=False, all_branches=True,
         description="Money only - billing, collections and expenses across all branches.",
         permissions=[
             "dashboard.view", "branches.view", "customers.view",
             *P("invoices", "view", "create", "edit", "waive"),
             *P("payments", "view", "create", "edit", "approve", "refund"),
             *P("expenses", "view", "create", "edit", "delete"),
             *P("reports", "view", "export"), "audit.view",
         ]),
    dict(name="Receptionist", is_system_role=False, all_branches=False,
         description="Front desk - enquiries, check-ins, visitors and complaints.",
         permissions=[
             "dashboard.view", "branches.view", "buildings.view", "floors.view",
             "rooms.view", "beds.view", "beds.assign",
             *P("customers", "view", "create", "edit", "checkin"),
             *P("visitors", "view", "create", "approve", "checkin"),
             *P("gatepass", "view", "create"), *P("complaints", "view", "create", "update"),
             *P("queries", "view", "reply"), "attendance.view", "attendance.mark",
             "invoices.view", "payments.view", "payments.create", "announcements.view",
         ]),
    dict(name="Security", is_system_role=False, all_branches=False,
         description="Gate duty - scanning, visitor entry and gate pass checks.",
         permissions=[
             "dashboard.view", "attendance.view", "attendance.mark",
             *P("visitors", "view", "checkin"), "gatepass.view", "customers.view", "announcements.view",
         ]),
    dict(name="Maintenance Staff", is_system_role=False, all_branches=False,
         description="Handles assigned complaints and asset condition.",
         permissions=["dashboard.view", "complaints.view", "complaints.update", "complaints.close",
                      "rooms.view", "beds.view", "beds.edit", "buildings.view", "floors.view",
                      "assets.view", "assets.edit", "inventory.view"]),
    dict(name="Food Manager", is_system_role=False, all_branches=False,
         description="Publishes the menu and tracks meal counts.",
         permissions=["dashboard.view", *P("food", "view", "create", "edit", "publish"),
                      "customers.view", "complaints.view", "inventory.view", "inventory.edit",
                      "reports.view"]),
]

BRANCHES = [
    dict(name="Koramangala", code="KOR", address="48, 7th Cross, 4th Block", city="Bengaluru",
         state="Karnataka", pincode="560034", contact_number="+91 8025531100", opened_on=d(-214)),
    dict(name="BTM Layout", code="BTM", address="16, 2nd Stage, 16th Main", city="Bengaluru",
         state="Karnataka", pincode="560076", contact_number="+91 8026681200", opened_on=d(-160)),
    dict(name="HSR Layout", code="HSR", address="5, Sector 6, 27th Main", city="Bengaluru",
         state="Karnataka", pincode="560102", contact_number="+91 8041207700", opened_on=d(-74)),
]

# The brief names four canonical accounts (*.local); the eight below are the
# ones the existing React demo already signs in with. Both are seeded so the
# frontend keeps working and the documented credentials also work.
CANONICAL = [
    dict(email="owner@sunrise.local", name="Sunrise Owner (demo)", role="Owner",
         employee_id="DEMO-001", phone="+91 9800000001", branches=["KOR", "BTM", "HSR"],
         password_key="owner"),
    dict(email="manager@sunrise.local", name="Sunrise Manager (demo)", role="Branch Manager",
         employee_id="DEMO-002", phone="+91 9800000002", branches=["KOR", "BTM"],
         password_key="manager"),
]

STAFF = [
    dict(email="rahul@sunriselivingpg.com", name="Rahul Sharma", role="Owner",
         employee_id="SUN-001", phone="+91 9845012233", branches=["KOR", "BTM", "HSR"]),
    dict(email="priya@sunriselivingpg.com", name="Priya Menon", role="Branch Manager",
         employee_id="SUN-004", phone="+91 9845112244", branches=["KOR", "BTM"]),
    dict(email="deepak@sunriselivingpg.com", name="Deepak Nayak", role="Branch Manager",
         employee_id="SUN-007", phone="+91 9845332255", branches=["HSR"]),
    dict(email="accounts@sunriselivingpg.com", name="Sneha Kulkarni", role="Accountant",
         employee_id="SUN-011", phone="+91 9845443366", branches=["KOR", "BTM", "HSR"]),
    dict(email="reception@sunriselivingpg.com", name="Anita Desai", role="Receptionist",
         employee_id="SUN-014", phone="+91 9845554477", branches=["KOR"]),
    dict(email="security@sunriselivingpg.com", name="Ramesh Yadav", role="Security",
         employee_id="SUN-019", phone="+91 9845665588", branches=["KOR"]),
    dict(email="maintenance@sunriselivingpg.com", name="Suresh Gowda", role="Maintenance Staff",
         employee_id="SUN-022", phone="+91 9845776699", branches=["KOR", "BTM", "HSR"]),
    dict(email="kitchen@sunriselivingpg.com", name="Lakshmi Bai", role="Food Manager",
         employee_id="SUN-025", phone="+91 9845887700", branches=["KOR", "BTM"]),
]

# Residents. Only these can reach the resident portal; Milestone 6 grows the table.
RESIDENTS = [
    dict(email="customer@sunrise.local", full_name="Arjun Mehta (demo)", phone="+91 9812000001",
         branch="KOR", status=CustomerStatus.ACTIVE, password_key="customer"),
    dict(email="kavya@sunrise.local", full_name="Kavya Iyer (demo)", phone="+91 9812000002",
         branch="BTM", status=CustomerStatus.ACTIVE, password_key="customer"),
    # Checked out: proves the status gate refuses a correct password.
    dict(email="former@sunrise.local", full_name="Former Resident (demo)", phone="+91 9812000003",
         branch="KOR", status=CustomerStatus.CHECKED_OUT, password_key="customer"),
]


# ----------------------------------------------------------------- helpers --
def upsert_plans(db: Session) -> dict[str, SubscriptionPlan]:
    out = {}
    for spec in PLANS:
        plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == spec["code"]))
        if plan is None:
            plan = SubscriptionPlan(**spec, billing_cycle=BillingCycle.MONTHLY, status=PlanStatus.ACTIVE)
            db.add(plan)
        else:
            for k, v in spec.items():
                setattr(plan, k, v)
        out[spec["code"]] = plan
    db.flush()
    return out


def upsert_permissions(db: Session) -> dict[str, Permission]:
    existing = {p.code: p for p in db.scalars(select(Permission)).all()}
    for row in catalog_rows():
        perm = existing.get(row["code"])
        if perm is None:
            perm = Permission(**row)
            db.add(perm)
            existing[row["code"]] = perm
        else:
            perm.label, perm.module, perm.action = row["label"], row["module"], row["action"]
            perm.is_master = row["is_master"]
    db.flush()
    return existing


def upsert_master_admin(db: Session) -> User:
    """
    Master admins deliberately hold no Role row.

    `roles` is tenant data - organization_id is NOT NULL - so a platform-wide
    role cannot exist, and inventing one with a NULL tenant would poke a hole in
    the very isolation the column enforces. Their authority comes from the
    `is_master_admin` flag plus the fixed MASTER_PERMISSIONS catalogue, which is
    exactly how the React AuthContext resolves them too.
    """
    made = []
    for email, name in (("master@pgdesk.local", "Platform Admin"),
                        ("master@pgdesk.io", "Platform Admin (legacy alias)")):
        user = db.scalar(select(User).where(User.email == email, User.organization_id.is_(None)))
        if user is None:
            user = User(
                organization_id=None, name=name, email=email, phone="+91 9000000001",
                employee_id="PLT-001", is_master_admin=True, joining_date=d(-800),
            )
            db.add(user)
        user.name = name
        user.password_hash = hash_password(DEMO_PASSWORDS["master"])
        user.is_master_admin = True
        user.status = UserStatus.ACTIVE
        user.is_active = True
        made.append(user)
    db.flush()
    return made[0]


def upsert_organization(db: Session, plans: dict[str, SubscriptionPlan]) -> Organization:
    slug = slugify("Sunrise Living PG")
    org = db.scalar(select(Organization).where(Organization.slug == slug))
    if org is None:
        org = Organization(slug=slug)
        db.add(org)

    org.name = "Sunrise Living PG"
    org.legal_name = "Sunrise Living Accommodations LLP"
    org.owner_name = "Rahul Sharma"
    org.owner_email = "rahul@sunriselivingpg.com"
    org.owner_phone = "+91 9845012233"
    org.address = "24, 5th Block, Koramangala"
    org.city, org.state, org.pincode = "Bengaluru", "Karnataka", "560034"
    org.pg_type, org.gender = "Co-living", "Unisex"
    org.status = OrganizationStatus.ACTIVE
    org.storage_used_gb = 4.2
    org.onboarded_on = d(-214)
    db.flush()

    plan = plans["plan_professional"]
    sub = db.scalar(
        select(Subscription).where(Subscription.organization_id == org.id,
                                   Subscription.is_current.is_(True))
    )
    if sub is None:
        sub = Subscription(organization_id=org.id, is_current=True)
        db.add(sub)
    sub.plan_id = plan.id
    sub.start_date = d(-214)
    sub.end_date = d(151)
    sub.status = SubscriptionStatus.ACTIVE
    db.flush()
    return org


def upsert_branches(db: Session, org: Organization) -> dict[str, Branch]:
    out = {}
    for spec in BRANCHES:
        branch = db.scalar(
            select(Branch).where(Branch.organization_id == org.id, Branch.code == spec["code"])
        )
        if branch is None:
            branch = Branch(organization_id=org.id, status=BranchStatus.ACTIVE, **spec)
            db.add(branch)
        else:
            for k, v in spec.items():
                setattr(branch, k, v)
        out[spec["code"]] = branch
    db.flush()
    return out


def upsert_roles(db: Session, org: Organization, perms: dict[str, Permission]) -> dict[str, Role]:
    out = {}
    for spec in ROLES:
        role = db.scalar(
            select(Role).where(Role.organization_id == org.id, Role.name == spec["name"])
        )
        if role is None:
            role = Role(organization_id=org.id, name=spec["name"])
            db.add(role)
        role.description = spec["description"]
        role.is_system_role = spec["is_system_role"]
        role.all_branches = spec["all_branches"]
        # Wildcards are expanded here, so the database only ever stores concrete codes.
        codes = expand(spec["permissions"])
        role.permissions = [perms[c] for c in sorted(codes) if c in perms]
        out[spec["name"]] = role
    db.flush()
    return out


def _password_for(spec: dict) -> str:
    """Canonical accounts use their documented password; the rest share the demo one."""
    if "password_key" in spec:
        return DEMO_PASSWORDS[spec["password_key"]]
    return settings.demo_password


def upsert_staff(db: Session, org: Organization, roles: dict[str, Role],
                 branches: dict[str, Branch]) -> list[User]:
    made = []
    for spec in STAFF + CANONICAL:
        user = db.scalar(
            select(User).where(User.organization_id == org.id, User.email == spec["email"])
        )
        if user is None:
            user = User(organization_id=org.id, email=spec["email"])
            db.add(user)
        user.name = spec["name"]
        user.phone = spec["phone"]
        user.employee_id = spec["employee_id"]
        # Rehashed every run so a changed password constant actually takes effect.
        user.password_hash = hash_password(_password_for(spec))
        user.must_change_password = False
        user.is_active = True
        user.status = UserStatus.ACTIVE
        user.is_master_admin = False
        user.roles = [roles[spec["role"]]]
        user.branches = [branches[c] for c in spec["branches"]]
        made.append(user)
    db.flush()
    return made


# Enough residents to fill most of the seeded beds, so occupancy figures look
# like a real PG rather than an empty building. Fictional names.
_FILLER_NAMES = [
    "Arjun Nair", "Kavya Rao", "Rohit Menon", "Sneha Pillai", "Vikram Shetty",
    "Ananya Bhat", "Karthik Reddy", "Divya Kamath", "Manish Gupta", "Pooja Hegde",
    "Rahul Verma", "Nisha Prabhu", "Sandeep Kulkarni", "Meghana Rai", "Aditya Shenoy",
    "Lakshmi Iyer", "Praveen Kumar", "Shruti Desai", "Naveen Acharya", "Anjali Pai",
    "Gaurav Salian", "Ritu Bhandari", "Sagar Naik", "Tanvi Joshi", "Harsha Gowda",
    "Deepika Suvarna", "Nikhil Poojary", "Aishwarya Kotian", "Varun Ballal", "Neha Mallya",
    "Kiran Adiga", "Sowmya Bhatt", "Ajay Karkera", "Rekha Amin", "Suhas Devadiga",
    "Priyanka Shenava", "Chetan Alva", "Vidya Kini", "Mohan Baliga", "Swathi Marla",
]


def _filler_residents() -> list[dict]:
    return [
        dict(email=f"resident{i + 1:02d}@sunrise.local",
             full_name=name, phone=f"+91 98{i + 10:02d}{7000 + i * 13:04d}",
             branch=["KOR", "KOR", "BTM", "HSR"][i % 4],
             status=CustomerStatus.ACTIVE, password_key="customer")
        for i, name in enumerate(_FILLER_NAMES)
    ]


def upsert_residents(db: Session, org: Organization,
                     branches: dict[str, Branch]) -> list[Customer]:
    made = []
    for spec in RESIDENTS + _filler_residents():
        cust = db.scalar(
            select(Customer).where(Customer.organization_id == org.id,
                                   Customer.email == spec["email"])
        )
        if cust is None:
            cust = Customer(organization_id=org.id, email=spec["email"])
            db.add(cust)
        cust.full_name = spec["full_name"]
        cust.phone = spec["phone"]
        cust.branch_id = branches[spec["branch"]].id
        cust.status = spec["status"]
        cust.is_active = True
        cust.password_hash = hash_password(DEMO_PASSWORDS[spec["password_key"]])
        cust.joining_date = d(-90 - (len(made) * 3))
        cust.monthly_rent = 0          # set from the bed once placed
        cust.security_deposit = 0
        cust.rent_due_day = 5
        cust.qr_token = generate_qr_token()
        made.append(cust)

    # One resident with no portal login at all, to prove a NULL hash cannot
    # authenticate rather than falling through to some default.
    enquiry = db.scalar(
        select(Customer).where(Customer.organization_id == org.id,
                               Customer.email == "enquiry@sunrise.local")
    )
    if enquiry is None:
        enquiry = Customer(organization_id=org.id, email="enquiry@sunrise.local")
        db.add(enquiry)
    enquiry.full_name = "Walk-in Enquiry (demo)"
    enquiry.phone = "+91 9812000009"
    enquiry.branch_id = branches["KOR"].id
    enquiry.status = CustomerStatus.ENQUIRY
    enquiry.password_hash = None
    enquiry.is_active = True
    made.append(enquiry)

    db.flush()
    return made


PROPERTY_PLAN = {
    # branch code -> buildings -> floors -> rooms per floor
    "KOR": [
        dict(name="Block A", code="A", floors=[
            dict(number=0, rooms=[("101", "Double", 2, 9000), ("102", "Triple", 3, 7500),
                                  ("103", "Single", 1, 13500)]),
            dict(number=1, rooms=[("201", "Triple", 3, 7800), ("202", "Double", 2, 9200),
                                  ("203", "Four Sharing", 4, 6500)]),
            dict(number=2, rooms=[("301", "Double", 2, 9500), ("302", "Triple", 3, 7800)]),
        ]),
        dict(name="Block B", code="B", floors=[
            dict(number=0, rooms=[("B01", "Four Sharing", 4, 6200), ("B02", "Triple", 3, 7400)]),
            dict(number=1, rooms=[("B11", "Double", 2, 8800), ("B12", "Single", 1, 12800)]),
        ]),
    ],
    "BTM": [
        dict(name="Main Block", code="MB", floors=[
            dict(number=0, rooms=[("G01", "Triple", 3, 7200), ("G02", "Double", 2, 8600)]),
            dict(number=1, rooms=[("101", "Double", 2, 8600), ("102", "Four Sharing", 4, 6000),
                                  ("103", "Triple", 3, 7200)]),
            dict(number=2, rooms=[("201", "Single", 1, 12500), ("202", "Double", 2, 8900)]),
        ]),
    ],
    "HSR": [
        dict(name="Tower 1", code="T1", floors=[
            dict(number=0, rooms=[("101", "Double", 2, 9800), ("102", "Triple", 3, 8200)]),
            dict(number=1, rooms=[("201", "Double", 2, 9800), ("202", "Single", 1, 14500)]),
        ]),
    ],
}

# Deterministic bed states, so occupancy figures are stable between seed runs.
_BED_PATTERN = [
    BedStatus.OCCUPIED, BedStatus.OCCUPIED, BedStatus.AVAILABLE, BedStatus.OCCUPIED,
    BedStatus.OCCUPIED, BedStatus.RESERVED, BedStatus.OCCUPIED, BedStatus.AVAILABLE,
    BedStatus.OCCUPIED, BedStatus.MAINTENANCE, BedStatus.OCCUPIED, BedStatus.OCCUPIED,
    BedStatus.AVAILABLE, BedStatus.OCCUPIED, BedStatus.BLOCKED,
]


def _floor_label(number: int) -> str:
    if number == 0:
        return "Ground Floor"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(number if number < 20 else number % 10, "th")
    return f"{number}{suffix} Floor"


def upsert_property(db: Session, org: Organization,
                    branches: dict[str, Branch]) -> dict[str, int]:
    """
    Buildings, floors, rooms and beds for every seeded branch.

    Idempotent by natural key at each level (branch+code, building+number,
    floor+number, room+number), so re-running updates rather than duplicates.
    Bed occupancy is set from a fixed pattern - random states would make the
    dashboard numbers move on every run and hide real regressions.
    """
    made = dict(buildings=0, floors=0, rooms=0, beds=0)
    bed_index = 0

    for branch_code, buildings in PROPERTY_PLAN.items():
        branch = branches.get(branch_code)
        if branch is None:
            continue

        for b_spec in buildings:
            building = db.scalar(select(Building).where(
                Building.branch_id == branch.id, Building.code == b_spec["code"]))
            if building is None:
                building = Building(organization_id=org.id, branch_id=branch.id,
                                    code=b_spec["code"])
                db.add(building)
            building.name = b_spec["name"]
            building.number_of_floors = len(b_spec["floors"])
            building.status = BuildingStatus.ACTIVE
            db.flush()
            made["buildings"] += 1

            for f_spec in b_spec["floors"]:
                floor = db.scalar(select(Floor).where(
                    Floor.building_id == building.id,
                    Floor.floor_number == f_spec["number"]))
                if floor is None:
                    floor = Floor(organization_id=org.id, branch_id=branch.id,
                                  building_id=building.id, floor_number=f_spec["number"])
                    db.add(floor)
                floor.name = _floor_label(f_spec["number"])
                floor.status = FloorStatus.ACTIVE
                db.flush()
                made["floors"] += 1

                for number, room_type, capacity, rent in f_spec["rooms"]:
                    room = db.scalar(select(Room).where(
                        Room.floor_id == floor.id, Room.room_number == number))
                    if room is None:
                        room = Room(organization_id=org.id, branch_id=branch.id,
                                    building_id=building.id, floor_id=floor.id,
                                    room_number=number)
                        db.add(room)
                    room.room_type = room_type
                    room.capacity = capacity
                    room.rent_amount = rent
                    room.deposit_amount = rent * 2
                    room.gender_policy = GenderPolicy.ANY
                    room.has_ac = capacity <= 2
                    room.has_attached_bathroom = True
                    room.status = RoomStatus.ACTIVE
                    db.flush()
                    made["rooms"] += 1

                    for i in range(capacity):
                        letter = chr(ord("A") + i)
                        bed = db.scalar(select(Bed).where(
                            Bed.room_id == room.id, Bed.bed_number == letter))
                        if bed is None:
                            bed = Bed(organization_id=org.id, branch_id=branch.id,
                                      room_id=room.id, bed_number=letter)
                            db.add(bed)
                        bed.bed_code = f"{branch.code}-{f_spec['number']}-{number}-{letter}"
                        bed.rent_amount = rent
                        status = _BED_PATTERN[bed_index % len(_BED_PATTERN)]
                        bed_index += 1
                        # A CHECK constraint ties OCCUPIED to a resident, and the
                        # seeded residents are far fewer than the beds - so the
                        # pattern's OCCUPIED entries become AVAILABLE here and
                        # real occupancy is applied afterwards, once residents exist.
                        bed.status = (BedStatus.AVAILABLE
                                      if status == BedStatus.OCCUPIED else status)
                        bed.current_customer_id = None
                        made["beds"] += 1
                    db.flush()

    return made


def place_residents(db: Session, org: Organization) -> int:
    """
    Put the seeded residents into real beds.

    Occupancy has to be set this way round because the database refuses an
    OCCUPIED bed with no occupant - which is exactly the guarantee we want.
    """
    residents = list(db.scalars(select(Customer).where(
        Customer.organization_id == org.id,
        Customer.status == CustomerStatus.ACTIVE)).all())
    free = list(db.scalars(select(Bed).where(
        Bed.organization_id == org.id, Bed.status == BedStatus.AVAILABLE,
        Bed.current_customer_id.is_(None)).order_by(Bed.bed_code)).all())

    placed = 0
    for resident, bed in zip(residents, free):
        already = db.scalar(select(Bed).where(Bed.current_customer_id == resident.id))
        if already is not None:
            continue
        room = db.get(Room, bed.room_id)
        bed.status = BedStatus.OCCUPIED
        bed.current_customer_id = resident.id
        # The whole placement chain, exactly as ResidentService.assign_bed writes it.
        resident.branch_id = bed.branch_id
        resident.room_id = room.id
        resident.floor_id = room.floor_id
        resident.building_id = room.building_id
        resident.bed_id = bed.id
        resident.monthly_rent = bed.rent_amount
        resident.security_deposit = float(bed.rent_amount) * 2
        placed += 1
    db.flush()
    return placed


def upsert_second_org(db: Session, plans: dict[str, SubscriptionPlan],
                      perms: dict[str, Permission]) -> Organization:
    """
    A second tenant with its own owner.

    Present so that tenant isolation can be exercised against real data rather
    than only in a fixture: sign in as owner@northstar.local and nothing
    belonging to Sunrise Living is reachable.
    """
    slug = slugify("Northstar Residency")
    org = db.scalar(select(Organization).where(Organization.slug == slug))
    if org is None:
        org = Organization(slug=slug)
        db.add(org)
    org.name = "Northstar Residency"
    org.legal_name = "Northstar Residency Pvt Ltd"
    org.owner_name = "Meera Krishnan"
    org.owner_email = "owner@northstar.local"
    org.owner_phone = "+91 9880000011"
    org.address = "9, 1st Main, Jayanagar"
    org.city, org.state, org.pincode = "Bengaluru", "Karnataka", "560041"
    org.pg_type, org.gender = "Ladies PG", "Female"
    org.status = OrganizationStatus.ACTIVE
    org.storage_used_gb = 0.8
    org.onboarded_on = d(-60)
    db.flush()

    sub = db.scalar(select(Subscription).where(Subscription.organization_id == org.id,
                                               Subscription.is_current.is_(True)))
    if sub is None:
        sub = Subscription(organization_id=org.id, is_current=True)
        db.add(sub)
    sub.plan_id = plans["plan_starter"].id
    sub.start_date, sub.end_date = d(-60), d(305)
    sub.status = SubscriptionStatus.ACTIVE
    db.flush()

    branch = db.scalar(select(Branch).where(Branch.organization_id == org.id,
                                            Branch.code == "JAY"))
    if branch is None:
        branch = Branch(organization_id=org.id, code="JAY")
        db.add(branch)
    branch.name = "Jayanagar"
    branch.address = "9, 1st Main"
    branch.city, branch.state, branch.pincode = "Bengaluru", "Karnataka", "560041"
    branch.status = BranchStatus.ACTIVE
    db.flush()

    role = db.scalar(select(Role).where(Role.organization_id == org.id, Role.name == "Owner"))
    if role is None:
        role = Role(organization_id=org.id, name="Owner")
        db.add(role)
    role.description = "Full control of Northstar Residency."
    role.is_system_role = True
    role.all_branches = True
    role.permissions = [perms[c] for c in sorted(expand(["*"])) if c in perms]
    db.flush()

    owner = db.scalar(select(User).where(User.organization_id == org.id,
                                         User.email == "owner@northstar.local"))
    if owner is None:
        owner = User(organization_id=org.id, email="owner@northstar.local")
        db.add(owner)
    owner.name = "Meera Krishnan"
    owner.phone = "+91 9880000011"
    owner.employee_id = "NST-001"
    owner.password_hash = hash_password(DEMO_PASSWORDS["owner"])
    owner.status = UserStatus.ACTIVE
    owner.is_active = True
    owner.roles = [role]
    owner.branches = [branch]
    db.flush()
    return org


def reset(db: Session) -> None:
    """Drops seeded rows in dependency order. Reference data is left alone."""
    print("  resetting tenant data ...")
    db.execute(delete(AuditLog))
    db.execute(delete(RefreshToken))
    for name in ("Sunrise Living PG", "Northstar Residency"):
        org = db.scalar(select(Organization).where(Organization.slug == slugify(name)))
        if not org:
            continue
        from seed_operations import clear_operational
        clear_operational(db, org)
        db.execute(delete(Bed).where(Bed.organization_id == org.id))
        db.execute(delete(Room).where(Room.organization_id == org.id))
        db.execute(delete(Floor).where(Floor.organization_id == org.id))
        db.execute(delete(Building).where(Building.organization_id == org.id))
        db.execute(delete(Customer).where(Customer.organization_id == org.id))
        db.execute(delete(User).where(User.organization_id == org.id))
        db.execute(delete(Subscription).where(Subscription.organization_id == org.id))
        db.execute(delete(Branch).where(Branch.organization_id == org.id))
        db.execute(delete(Role).where(Role.organization_id == org.id))
        db.execute(delete(Organization).where(Organization.id == org.id))
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the PGDesk development database.")
    parser.add_argument("--reset", action="store_true", help="delete seeded tenant data first")
    args = parser.parse_args()

    if settings.is_production:
        print("Refusing to seed a production database.", file=sys.stderr)
        return 1

    print(f"Seeding {engine.url.render_as_string(hide_password=True)}")
    with SessionLocal() as db:
        if args.reset:
            reset(db)

        plans = upsert_plans(db)
        print(f"  plans          {len(plans)}")

        perms = upsert_permissions(db)
        print(f"  permissions    {len(perms)}")

        master = upsert_master_admin(db)
        print(f"  master admin   {master.email} ({len(MASTER_PERMISSIONS)} master permissions)")

        org = upsert_organization(db, plans)
        print(f"  organisation   {org.name}")

        branches = upsert_branches(db, org)
        print(f"  branches       {', '.join(branches)}")

        roles = upsert_roles(db, org, perms)
        print(f"  roles          {len(roles)}")

        staff = upsert_staff(db, org, roles, branches)
        print(f"  staff users    {len(staff)}")

        residents = upsert_residents(db, org, branches)
        print(f"  residents      {len(residents)}")

        counts = upsert_property(db, org, branches)
        print(f"  buildings      {counts['buildings']}")
        print(f"  floors         {counts['floors']}")
        print(f"  rooms          {counts['rooms']}")
        print(f"  beds           {counts['beds']}")

        placed = place_residents(db, org)
        print(f"  beds occupied  {placed}")

        from seed_operations import seed_operations
        ops = seed_operations(db, org)
        for label, key in (("invoices", "invoices"), ("payments", "payments"),
                           ("attendance", "attendance"), ("gate logs", "gate_logs"),
                           ("visitors", "visitors"), ("gate passes", "gate_passes"),
                           ("food menus", "menus"), ("meal records", "meals"),
                           ("laundry slots", "slots"), ("laundry jobs", "requests"),
                           ("complaints", "complaints"), ("queries", "queries"),
                           ("expenses", "expenses"), ("inventory items", "inventory"),
                           ("assets", "assets"), ("announcements", "announcements"),
                           ("notifications", "notifications"), ("KYC records", "kyc")):
            if key in ops:
                print(f"  {label:14s} {ops[key]}")

        second = upsert_second_org(db, plans, perms)
        print(f"  second tenant  {second.name} (owner@northstar.local)")

        db.commit()

    print("""
------------------------------------------------------------------
 DEVELOPMENT DEMO ACCOUNTS - fictional, never use in production
------------------------------------------------------------------
 Master Admin   master@pgdesk.local      {master}
 PG Owner       owner@sunrise.local      {owner}
 Branch Manager manager@sunrise.local    {manager}
 Resident       customer@sunrise.local   {customer}

 Second tenant, for isolation checks:
 PG Owner       owner@northstar.local    {owner}

 The eight accounts the React demo already uses
 (rahul@sunriselivingpg.com and colleagues) keep the password "{legacy}".
------------------------------------------------------------------
""".format(legacy=settings.demo_password, **DEMO_PASSWORDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
