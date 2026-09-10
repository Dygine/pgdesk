"""
Operational demo data: residents, invoices, payments, attendance, gate logs,
visitors, gate passes, menus, meals, laundry, complaints, queries, expenses,
inventory, assets, announcements and notifications.

Kept out of `seed.py` so that file stays readable. Everything here is
deterministic - a fixed PRNG seed and fixed patterns - because dashboards that
move on every run hide regressions rather than revealing them.
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Announcement, Asset, Attendance, Bed, Branch, Complaint, ComplaintUpdate,
    Customer, Expense, FoodMenu, GateLog, GatePass, InventoryItem,
    InventoryTransaction, Invoice, InvoiceItem, LaundryRequest, LaundrySlot,
    MealAttendance, Notification, Organization, OrganizationSettings, Payment,
    QueryMessage, ResidentKyc, Room, SupportQuery, User, Visitor,
)
from app.models.enums import (
    AnnouncementAudience, AssetStatus, AttendanceStatus, AttendanceSubject,
    ComplaintStatus, CustomerStatus, GateDirection, GatePassStatus,
    InventoryTxnType, InvoiceItemKind, InvoiceStatus, KycIdType, KycStatus,
    LaundryRequestStatus, LaundrySlotStatus, MealStatus, MealType,
    NotificationType, PaymentMethod, PaymentStatus, PublishStatus, QueryStatus,
    TicketPriority, VisitorStatus,
)

RNG = random.Random(20260908)
TODAY = date.today()
NOW = datetime.now(timezone.utc)


def d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def dt(days: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime.combine(d(days), time(hour, minute), tzinfo=timezone.utc)


OPERATIONAL_TABLES = (
    Notification, Announcement, Asset, InventoryTransaction, InventoryItem,
    Expense, QueryMessage, SupportQuery, ComplaintUpdate, Complaint,
    LaundryRequest, LaundrySlot, MealAttendance, FoodMenu, GatePass, GateLog,
    Visitor, Attendance, Payment, InvoiceItem, Invoice, ResidentKyc,
)


def clear_operational(db: Session, org: Organization) -> None:
    """Delete in dependency order so foreign keys never block the reset."""
    for model in OPERATIONAL_TABLES:
        db.execute(delete(model).where(model.organization_id == org.id))
    db.flush()


# --------------------------------------------------------------------- KYC
def seed_kyc(db: Session, org: Organization, residents: list[Customer]) -> int:
    made = 0
    for i, resident in enumerate(residents):
        if i % 4 == 3:
            continue                       # a quarter have not submitted anything
        id_type = [KycIdType.AADHAAR, KycIdType.PAN, KycIdType.DRIVING_LICENCE][i % 3]
        # Obviously fake numbers - the digits are sequential from the index.
        number = f"{9000 + i:04d}{1000 + i * 7:04d}{2000 + i * 3:04d}"
        db.add(ResidentKyc(
            organization_id=org.id, resident_id=resident.id, id_type=id_type,
            id_number=number, document_reference=f"kyc/{resident.id}/{id_type.lower()}.pdf",
            status=KycStatus.VERIFIED if i % 3 else KycStatus.SUBMITTED,
            verified_at=NOW - timedelta(days=i) if i % 3 else None))
        made += 1
    db.flush()
    return made


# ---------------------------------------------------------------- billing
def seed_billing(db: Session, org: Organization, residents: list[Customer],
                 staff: list[User]) -> dict:
    """
    Three months of rent, with a realistic collection pattern: older months
    almost fully paid, the current month part-collected and some overdue.
    """
    settings = db.scalars(select(OrganizationSettings).where(
        OrganizationSettings.organization_id == org.id)).first()
    prefix = settings.invoice_prefix if settings else "INV"
    accountant = next((u for u in staff if "accounts" in (u.email or "")), staff[0])

    live = [r for r in residents
            if r.status in (CustomerStatus.ACTIVE, CustomerStatus.NOTICE)
            and float(r.monthly_rent) > 0]

    invoice_n = payment_n = 0
    counts = {"invoices": 0, "payments": 0}

    for month_offset in (-2, -1, 0):
        period = (TODAY.replace(day=1) + timedelta(days=32 * month_offset)).replace(day=1)
        for i, resident in enumerate(live):
            invoice_n += 1
            due = period.replace(day=min(resident.rent_due_day or 5, 28))
            invoice = Invoice(
                organization_id=org.id, branch_id=resident.branch_id,
                resident_id=resident.id,
                invoice_number=f"{prefix}-{invoice_n:05d}",
                invoice_date=period, due_date=due, period=period,
                status=InvoiceStatus.PENDING)
            db.add(invoice)
            db.flush()

            rent = float(resident.monthly_rent)
            items = [(InvoiceItemKind.RENT,
                      f"Room rent — {period.strftime('%B %Y')}", rent)]
            # Food and electricity on some residents, so invoices are not all
            # identical single-line documents.
            if i % 3 == 0:
                items.append((InvoiceItemKind.FOOD, "Mess charges", 2500.0))
            if i % 5 == 0:
                items.append((InvoiceItemKind.ELECTRICITY, "Electricity share", 480.0))

            for kind, description, amount in items:
                item = InvoiceItem(
                    organization_id=org.id, invoice_id=invoice.id, kind=kind,
                    description=description, quantity=1, unit_price=amount,
                    amount=amount)
                db.add(item)
                invoice.items.append(item)

            total = sum(a for _, _, a in items)

            # Collection pattern by age of the invoice.
            if month_offset <= -2:
                paid_fraction = 1.0
            elif month_offset == -1:
                paid_fraction = 1.0 if i % 7 else 0.0
            else:
                paid_fraction = 1.0 if i % 3 == 0 else (0.5 if i % 3 == 1 else 0.0)

            if paid_fraction > 0:
                payment_n += 1
                amount = round(total * paid_fraction, 2)
                method = [PaymentMethod.UPI, PaymentMethod.CASH,
                          PaymentMethod.BANK_TRANSFER, PaymentMethod.CARD][i % 4]
                # The newest month keeps a few payments unverified, so the
                # verification queue on the payments screen is not empty.
                verified = not (month_offset == 0 and i % 6 == 0)
                payment = Payment(
                    organization_id=org.id, branch_id=resident.branch_id,
                    resident_id=resident.id, invoice_id=invoice.id,
                    payment_number=f"PAY-{payment_n:05d}", amount=amount,
                    payment_date=min(due + timedelta(days=i % 5), TODAY),
                    method=method,
                    reference=(f"UTR{700000 + payment_n}"
                               if method != PaymentMethod.CASH else None),
                    status=PaymentStatus.VERIFIED if verified else PaymentStatus.PENDING,
                    received_by_id=accountant.id,
                    verified_by_id=accountant.id if verified else None,
                    verified_at=NOW - timedelta(days=2) if verified else None)
                db.add(payment)
                invoice.payments.append(payment)
                counts["payments"] += 1

            db.flush()
            invoice.recalculate()
            counts["invoices"] += 1

    db.flush()
    return counts


# ------------------------------------------------------------- operations
def seed_attendance(db: Session, org: Organization, residents: list[Customer]) -> int:
    live = [r for r in residents if r.status == CustomerStatus.ACTIVE]
    made = 0
    for day_offset in range(-20, 1):
        on_date = d(day_offset)
        if on_date > TODAY:
            continue
        for i, resident in enumerate(live):
            roll = (i * 7 + day_offset) % 20
            status = (AttendanceStatus.ABSENT if roll == 0
                      else AttendanceStatus.ON_LEAVE if roll == 1
                      else AttendanceStatus.LATE if roll == 2
                      else AttendanceStatus.PRESENT)
            db.add(Attendance(
                organization_id=org.id, branch_id=resident.branch_id,
                subject=AttendanceSubject.RESIDENT, resident_id=resident.id,
                on_date=on_date, status=status, source="gate" if roll > 4 else "manual",
                check_in_at=(dt(day_offset, 8, 30 + (i % 25))
                             if status != AttendanceStatus.ABSENT else None)))
            made += 1
    db.flush()
    return made


def seed_gate_logs(db: Session, org: Organization, residents: list[Customer]) -> int:
    live = [r for r in residents if r.status == CustomerStatus.ACTIVE][:20]
    made = 0
    now = datetime.now(timezone.utc)
    for day_offset in range(-6, 1):
        for i, resident in enumerate(live):
            db.add(GateLog(
                organization_id=org.id, branch_id=resident.branch_id,
                resident_id=resident.id, direction=GateDirection.EXIT,
                occurred_at=dt(day_offset, 9, i % 50), gate="Main gate",
                source="qr", allowed=True))
            # Today's evening return has not happened yet if the seed runs in
            # the morning. A gate log dated in the future is not just untidy: it
            # sorts above every real movement, so "last movement" becomes an
            # event that has not occurred and the gate starts inferring the
            # wrong direction.
            evening = dt(day_offset, 19, i % 50)
            if evening <= now:
                db.add(GateLog(
                    organization_id=org.id, branch_id=resident.branch_id,
                    resident_id=resident.id, direction=GateDirection.ENTRY,
                    occurred_at=evening, gate="Main gate",
                    source="qr", allowed=True))
                made += 1
            made += 1
    db.flush()
    return made


def seed_visitors(db: Session, org: Organization, residents: list[Customer],
                  staff: list[User]) -> int:
    approver = next((u for u in staff if "reception" in (u.email or "")), staff[0])
    names = ["Ramesh Kumar", "Sunita Devi", "Anil Joshi", "Farida Sheikh",
             "Vikas Rane", "Geeta Nayak", "Imran Qureshi", "Sarita Pillai",
             "Mahesh Gowda", "Rekha Kamath"]
    relations = ["Father", "Mother", "Friend", "Sibling", "Cousin", "Colleague"]
    statuses = [VisitorStatus.COMPLETED, VisitorStatus.COMPLETED,
                VisitorStatus.APPROVED, VisitorStatus.PENDING,
                VisitorStatus.INSIDE, VisitorStatus.REJECTED]
    live = [r for r in residents if r.status == CustomerStatus.ACTIVE]

    for i, name in enumerate(names):
        resident = live[i % len(live)]
        status = statuses[i % len(statuses)]
        visitor = Visitor(
            organization_id=org.id, branch_id=resident.branch_id,
            resident_id=resident.id, name=name, phone=f"+91 90{i:02d}0{11000 + i}",
            relation=relations[i % len(relations)], purpose="Personal visit",
            expected_at=dt(-(i % 5), 11), status=status,
            approved_by_id=(approver.id if status not in (VisitorStatus.PENDING,)
                            else None),
            id_proof_reference=f"ID-{5000 + i}")
        if status in (VisitorStatus.COMPLETED, VisitorStatus.INSIDE):
            visitor.entry_at = dt(-(i % 5), 11, 10)
        if status == VisitorStatus.COMPLETED:
            visitor.exit_at = dt(-(i % 5), 13, 40)
        db.add(visitor)
    db.flush()
    return len(names)


def seed_gate_passes(db: Session, org: Organization, residents: list[Customer],
                     staff: list[User]) -> int:
    approver = staff[0]
    reasons = ["Home visit", "Medical appointment", "Family function",
               "Job interview", "Weekend trip", "Exam at college"]
    statuses = [GatePassStatus.COMPLETED, GatePassStatus.APPROVED,
                GatePassStatus.PENDING, GatePassStatus.ACTIVE,
                GatePassStatus.REJECTED, GatePassStatus.COMPLETED]
    live = [r for r in residents if r.status == CustomerStatus.ACTIVE]

    for i in range(12):
        resident = live[i % len(live)]
        status = statuses[i % len(statuses)]
        db.add(GatePass(
            organization_id=org.id, branch_id=resident.branch_id,
            resident_id=resident.id, pass_number=f"GP-{i + 1:05d}",
            reason=reasons[i % len(reasons)],
            destination=["Mysuru", "Mangaluru", "Hubballi", "Chennai"][i % 4],
            from_at=dt(-(i % 8), 7), to_at=dt(-(i % 8) + 2, 20),
            is_emergency=i % 9 == 0, status=status,
            approved_by_id=approver.id if status != GatePassStatus.PENDING else None,
            approved_at=NOW - timedelta(days=i % 8) if status != GatePassStatus.PENDING else None))
    db.flush()
    return 12


def seed_food(db: Session, org: Organization, branches: list[Branch],
              residents: list[Customer]) -> dict:
    menu_plan = {
        MealType.BREAKFAST: ["Idli, sambar, chutney", "Poha, banana", "Upma, coconut chutney",
                             "Dosa, potato masala", "Bread, jam, boiled eggs",
                             "Pongal, vada", "Puri, bhaji"],
        MealType.LUNCH: ["Rice, dal, beans palya, curd", "Chapati, rajma, salad",
                         "Bisi bele bath, raita", "Rice, sambar, cabbage palya",
                         "Jeera rice, chole", "Curd rice, pickle, papad",
                         "Veg pulao, raita"],
        MealType.SNACK: ["Tea, biscuits", "Coffee, banana chips", "Tea, groundnuts",
                         "Buttermilk, murukku", "Tea, bhel", "Coffee, cake",
                         "Tea, samosa"],
        MealType.DINNER: ["Chapati, paneer curry", "Rice, rasam, poriyal",
                          "Chapati, mixed veg", "Fried rice, gobi manchurian",
                          "Rice, dal fry, salad", "Chapati, egg curry",
                          "Rice, sambar, papad"],
    }
    times = {MealType.BREAKFAST: (time(7, 30), time(9, 30)),
             MealType.LUNCH: (time(12, 30), time(14, 30)),
             MealType.SNACK: (time(17, 0), time(18, 30)),
             MealType.DINNER: (time(20, 0), time(22, 0))}

    menus = 0
    for branch in branches:
        for day_offset in range(-3, 8):
            on_date = d(day_offset)
            for meal, options in menu_plan.items():
                serve_from, serve_to = times[meal]
                db.add(FoodMenu(
                    organization_id=org.id, branch_id=branch.id, on_date=on_date,
                    meal=meal, items=options[on_date.weekday()],
                    calories={"BREAKFAST": 420, "LUNCH": 720, "SNACK": 210,
                              "DINNER": 640}[meal],
                    serve_from=serve_from, serve_to=serve_to))
                menus += 1
    db.flush()

    live = [r for r in residents if r.status == CustomerStatus.ACTIVE]
    meals = 0
    for day_offset in range(-5, 2):
        on_date = d(day_offset)
        for i, resident in enumerate(live):
            for j, meal in enumerate(MealType):
                roll = (i * 3 + j + day_offset) % 12
                if roll == 0:
                    status = MealStatus.OPTED_OUT
                elif roll == 1:
                    status = MealStatus.SKIPPED
                elif on_date > TODAY:
                    status = MealStatus.EXPECTED
                else:
                    status = MealStatus.ATTENDED
                db.add(MealAttendance(
                    organization_id=org.id, branch_id=resident.branch_id,
                    resident_id=resident.id, on_date=on_date, meal=meal,
                    status=status))
                meals += 1
    db.flush()
    return {"menus": menus, "meals": meals}


def seed_laundry(db: Session, org: Organization, branches: list[Branch],
                 residents: list[Customer]) -> dict:
    live = [r for r in residents if r.status == CustomerStatus.ACTIVE]
    slots = []
    for branch in branches:
        for day_offset in range(-2, 8):
            for start, end in ((time(8, 0), time(11, 0)),
                               (time(14, 0), time(17, 0)),
                               (time(18, 0), time(21, 0))):
                slot = LaundrySlot(
                    organization_id=org.id, branch_id=branch.id, on_date=d(day_offset),
                    start_time=start, end_time=end, capacity=8,
                    status=LaundrySlotStatus.AVAILABLE)
                db.add(slot)
                slots.append(slot)
    db.flush()

    statuses = [LaundryRequestStatus.COLLECTED, LaundryRequestStatus.READY,
                LaundryRequestStatus.PROCESSING, LaundryRequestStatus.RECEIVED,
                LaundryRequestStatus.BOOKED]
    requests = 0
    for i, slot in enumerate(slots):
        if i % 3:
            continue
        for j in range(min(3, len(live))):
            resident = live[(i + j) % len(live)]
            if resident.branch_id != slot.branch_id:
                continue
            db.add(LaundryRequest(
                organization_id=org.id, branch_id=slot.branch_id,
                resident_id=resident.id, slot_id=slot.id,
                item_count=3 + ((i + j) % 8),
                status=statuses[(i + j) % len(statuses)]))
            requests += 1
    db.flush()
    return {"slots": len(slots), "requests": requests}


# ----------------------------------------------------------------- support
def seed_complaints(db: Session, org: Organization, residents: list[Customer],
                    staff: list[User]) -> int:
    subjects = [
        ("Plumbing", "Tap leaking in the bathroom", TicketPriority.MEDIUM),
        ("Electrical", "Fan not working in room", TicketPriority.HIGH),
        ("Internet", "Wi-Fi keeps dropping in the evening", TicketPriority.MEDIUM),
        ("Housekeeping", "Corridor not cleaned since Monday", TicketPriority.LOW),
        ("Food", "Dinner was cold yesterday", TicketPriority.MEDIUM),
        ("Security", "Main gate left unlocked at night", TicketPriority.URGENT),
        ("Room", "Cupboard door hinge broken", TicketPriority.LOW),
        ("Maintenance", "Water heater not heating", TicketPriority.HIGH),
        ("Electrical", "Power socket sparking", TicketPriority.URGENT),
        ("Plumbing", "Slow drainage in the washroom", TicketPriority.MEDIUM),
        ("Internet", "Cannot connect on the second floor", TicketPriority.MEDIUM),
        ("Food", "Request for more variety at breakfast", TicketPriority.LOW),
    ]
    statuses = [ComplaintStatus.RESOLVED, ComplaintStatus.IN_PROGRESS,
                ComplaintStatus.OPEN, ComplaintStatus.CLOSED,
                ComplaintStatus.WAITING, ComplaintStatus.OPEN]
    maintenance = next((u for u in staff if "maintenance" in (u.email or "")), staff[0])
    live = [r for r in residents if r.status == CustomerStatus.ACTIVE]

    for i, (category, subject, priority) in enumerate(subjects):
        resident = live[i % len(live)]
        status = statuses[i % len(statuses)]
        complaint = Complaint(
            organization_id=org.id, branch_id=resident.branch_id,
            resident_id=resident.id, room_id=resident.room_id,
            ticket_number=f"CMP-{i + 1:05d}", category=category, subject=subject,
            description=f"{subject}. Reported from room "
                        f"{resident.room_id and 'assigned' or 'unassigned'}.",
            priority=priority, status=status,
            assigned_to_id=maintenance.id if status != ComplaintStatus.OPEN else None,
            resolved_at=(NOW - timedelta(days=i)
                         if status in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)
                         else None),
            resolution=("Attended and fixed."
                        if status in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)
                        else None))
        db.add(complaint)
        db.flush()
        db.add(ComplaintUpdate(
            organization_id=org.id, complaint_id=complaint.id,
            author_resident_id=resident.id, author_name=resident.full_name,
            message=subject, status_after=ComplaintStatus.OPEN))
        if status != ComplaintStatus.OPEN:
            db.add(ComplaintUpdate(
                organization_id=org.id, complaint_id=complaint.id,
                author_user_id=maintenance.id, author_name=maintenance.name,
                message="Looked into this, working on it now.",
                status_after=status))
    db.flush()
    return len(subjects)


def seed_queries(db: Session, org: Organization, residents: list[Customer],
                 staff: list[User]) -> int:
    items = [
        ("Billing", "Why is there an electricity charge this month?"),
        ("Room", "Can I move to a single room next month?"),
        ("Food", "Is a Jain meal option available?"),
        ("Policy", "What is the notice period for leaving?"),
        ("General", "Is there parking for a two-wheeler?"),
        ("Billing", "Can I pay rent in two instalments?"),
    ]
    responder = next((u for u in staff if "reception" in (u.email or "")), staff[0])
    live = [r for r in residents if r.status == CustomerStatus.ACTIVE]

    for i, (category, subject) in enumerate(items):
        resident = live[i % len(live)]
        answered = i % 3 != 2
        query = SupportQuery(
            organization_id=org.id, branch_id=resident.branch_id,
            resident_id=resident.id, ticket_number=f"QRY-{i + 1:05d}",
            category=category, subject=subject,
            status=QueryStatus.ANSWERED if answered else QueryStatus.OPEN)
        db.add(query)
        db.flush()
        db.add(QueryMessage(
            organization_id=org.id, query_id=query.id,
            author_resident_id=resident.id, author_name=resident.full_name,
            is_staff=False, message=subject))
        if answered:
            db.add(QueryMessage(
                organization_id=org.id, query_id=query.id,
                author_user_id=responder.id, author_name=responder.name,
                is_staff=True,
                message="Thanks for asking — the front desk will confirm today."))
    db.flush()
    return len(items)


# -------------------------------------------------------------- back office
def seed_expenses(db: Session, org: Organization, branches: list[Branch],
                  staff: list[User]) -> int:
    plan = [
        ("Electricity", 18500, "BESCOM"), ("Water", 6200, "BWSSB"),
        ("Internet", 4500, "ACT Fibernet"), ("Food", 92000, "Sri Lakshmi Provisions"),
        ("Housekeeping", 14000, "Sparkle Services"), ("Maintenance", 8600, "Ravi Plumbing"),
        ("Salary", 165000, "Payroll"), ("Laundry", 11200, "Fresh & Clean"),
        ("Other", 3400, "Miscellaneous"),
    ]
    creator = next((u for u in staff if "accounts" in (u.email or "")), staff[0])
    n = 0
    for month_offset in (-2, -1, 0):
        base = (TODAY.replace(day=1) + timedelta(days=32 * month_offset)).replace(day=1)
        for branch in branches:
            for i, (category, amount, vendor) in enumerate(plan):
                n += 1
                jitter = 1 + ((i + month_offset) % 7) / 100
                db.add(Expense(
                    organization_id=org.id, branch_id=branch.id,
                    expense_number=f"EXP-{n:05d}", category=category,
                    amount=round(amount * jitter / len(branches), 2),
                    spent_on=min(base + timedelta(days=3 + i), TODAY),
                    vendor=vendor,
                    payment_method=["BANK_TRANSFER", "UPI", "CASH"][i % 3],
                    reference=f"REF{40000 + n}",
                    description=f"{category} for {base.strftime('%B %Y')}",
                    created_by_id=creator.id))
    db.flush()
    return n


def seed_inventory(db: Session, org: Organization, branches: list[Branch],
                   staff: list[User]) -> int:
    catalogue = [
        ("HK-SOAP", "Hand soap refill", "Housekeeping", "bottle", 40, 15, 85),
        ("HK-PHEN", "Floor cleaner", "Housekeeping", "litre", 24, 10, 120),
        ("HK-BRSH", "Toilet brush", "Housekeeping", "pcs", 12, 6, 65),
        ("KIT-RICE", "Rice", "Kitchen", "kg", 180, 60, 58),
        ("KIT-DAL", "Toor dal", "Kitchen", "kg", 45, 25, 140),
        ("KIT-OIL", "Sunflower oil", "Kitchen", "litre", 30, 20, 135),
        ("KIT-GAS", "LPG cylinder", "Kitchen", "pcs", 4, 3, 1120),
        ("MNT-BULB", "LED bulb 9W", "Maintenance", "pcs", 60, 25, 95),
        ("MNT-TAP", "Tap washer", "Maintenance", "pcs", 8, 20, 15),
        ("MNT-WIRE", "Electrical wire", "Maintenance", "metre", 120, 50, 22),
        ("LIN-SHEET", "Bed sheet", "Linen", "pcs", 90, 40, 320),
        ("LIN-PILL", "Pillow cover", "Linen", "pcs", 35, 40, 110),
    ]
    creator = staff[0]
    n = 0
    for branch in branches:
        for i, (sku, name, category, unit, qty, minimum, price) in enumerate(catalogue):
            # Vary stock per branch so some items sit below their minimum and
            # the low-stock alert has something to show.
            quantity = max(0, qty - (i * 3 if branch is branches[0] else i * 5))
            item = InventoryItem(
                organization_id=org.id, branch_id=branch.id, sku=sku, name=name,
                category=category, unit=unit, quantity=quantity,
                minimum_stock=minimum, location=f"{category} store",
                supplier=["Sri Lakshmi Provisions", "MetroMart", "Local vendor"][i % 3],
                purchase_price=price)
            db.add(item)
            db.flush()
            db.add(InventoryTransaction(
                organization_id=org.id, item_id=item.id, branch_id=branch.id,
                txn_type=InventoryTxnType.STOCK_IN, quantity_delta=quantity,
                balance_after=quantity, notes="Opening stock",
                created_by_id=creator.id))
            n += 1
    db.flush()
    return n


def seed_assets(db: Session, org: Organization, branches: list[Branch]) -> int:
    catalogue = [
        ("Water purifier", "Appliance", 18500, AssetStatus.ACTIVE),
        ("Washing machine", "Appliance", 24500, AssetStatus.ACTIVE),
        ("Refrigerator", "Appliance", 32000, AssetStatus.ACTIVE),
        ("CCTV camera set", "Security", 42000, AssetStatus.ACTIVE),
        ("Inverter & battery", "Electrical", 38000, AssetStatus.MAINTENANCE),
        ("Wi-Fi router", "Network", 4200, AssetStatus.ACTIVE),
        ("Geyser 15L", "Appliance", 9800, AssetStatus.ACTIVE),
        ("Dining tables", "Furniture", 26000, AssetStatus.ACTIVE),
        ("Vacuum cleaner", "Housekeeping", 7600, AssetStatus.DAMAGED),
        ("Fire extinguisher", "Safety", 3400, AssetStatus.ACTIVE),
    ]
    n = 0
    for branch in branches:
        for i, (name, category, price, status) in enumerate(catalogue):
            n += 1
            db.add(Asset(
                organization_id=org.id, branch_id=branch.id,
                asset_code=f"AST-{n:05d}", name=name, category=category,
                purchase_date=d(-400 + i * 17), purchase_price=price,
                warranty_until=d(330 - i * 11), location=f"{branch.code} · common area",
                status=status))
    db.flush()
    return n


def seed_announcements(db: Session, org: Organization, branches: list[Branch],
                       staff: list[User], residents: list[Customer]) -> int:
    owner = staff[0]
    items = [
        ("Water supply interruption on Sunday",
         "The tank will be cleaned on Sunday between 10am and 2pm. Please store water.",
         TicketPriority.HIGH, AnnouncementAudience.ALL),
        ("Rent due on the 5th",
         "A reminder that rent for this month is due on the 5th. UPI is preferred.",
         TicketPriority.MEDIUM, AnnouncementAudience.RESIDENTS),
        ("New mess timings from Monday",
         "Breakfast moves to 7:30–9:30am. Lunch and dinner are unchanged.",
         TicketPriority.MEDIUM, AnnouncementAudience.RESIDENTS),
        ("Staff meeting on Friday",
         "All branch staff to meet at 4pm in the Koramangala office.",
         TicketPriority.LOW, AnnouncementAudience.STAFF),
        ("Diwali celebration",
         "Sweets and a short get-together in the common room at 7pm on Saturday.",
         TicketPriority.LOW, AnnouncementAudience.ALL),
    ]
    for i, (title, message, priority, audience) in enumerate(items):
        db.add(Announcement(
            organization_id=org.id,
            branch_id=branches[0].id if i == 3 else None,
            title=title, message=message, priority=priority, audience=audience,
            status=PublishStatus.PUBLISHED, starts_on=d(-i * 2),
            ends_on=d(20 - i), created_by_id=owner.id))
    db.flush()
    return len(items)


def seed_notifications(db: Session, org: Organization, residents: list[Customer],
                       staff: list[User]) -> int:
    """A handful of unread items so the bell has something in it."""
    made = 0
    live = [r for r in residents if r.status == CustomerStatus.ACTIVE][:12]
    for i, resident in enumerate(live):
        db.add(Notification(
            organization_id=org.id, resident_id=resident.id,
            kind=NotificationType.RENT_DUE, title="Rent due soon",
            message="Your rent for this month is due on the 5th.",
            link="/me/rent", read_at=None if i % 2 else NOW))
        made += 1
    for i, user in enumerate(staff[:6]):
        db.add(Notification(
            organization_id=org.id, user_id=user.id,
            kind=NotificationType.SYSTEM, title="Low stock",
            message="Tap washers are below the minimum level.",
            read_at=None if i % 2 else NOW))
        made += 1
    db.flush()
    return made


# --------------------------------------------------------------- entrypoint
def seed_operations(db: Session, org: Organization) -> dict:
    """Everything above, in dependency order. Returns counts for the summary."""
    branches = list(db.scalars(select(Branch).where(
        Branch.organization_id == org.id).order_by(Branch.code)).all())
    residents = list(db.scalars(select(Customer).where(
        Customer.organization_id == org.id).order_by(Customer.full_name)).all())
    staff = list(db.scalars(select(User).where(
        User.organization_id == org.id).order_by(User.name)).all())

    if not (branches and residents and staff):
        return {}

    settings = db.scalars(select(OrganizationSettings).where(
        OrganizationSettings.organization_id == org.id)).first()
    if settings is None:
        settings = OrganizationSettings(
            organization_id=org.id, contact_email=org.owner_email,
            contact_phone=org.owner_phone, rent_due_day=5,
            late_fee_amount=250, late_fee_after_days=5)
        db.add(settings)
        db.flush()

    clear_operational(db, org)

    counts = {"kyc": seed_kyc(db, org, residents)}
    counts.update(seed_billing(db, org, residents, staff))
    counts["attendance"] = seed_attendance(db, org, residents)
    counts["gate_logs"] = seed_gate_logs(db, org, residents)
    counts["visitors"] = seed_visitors(db, org, residents, staff)
    counts["gate_passes"] = seed_gate_passes(db, org, residents, staff)
    counts.update(seed_food(db, org, branches, residents))
    counts.update(seed_laundry(db, org, branches, residents))
    counts["complaints"] = seed_complaints(db, org, residents, staff)
    counts["queries"] = seed_queries(db, org, residents, staff)
    counts["expenses"] = seed_expenses(db, org, branches, staff)
    counts["inventory"] = seed_inventory(db, org, branches, staff)
    counts["assets"] = seed_assets(db, org, branches)
    counts["announcements"] = seed_announcements(db, org, branches, staff, residents)
    counts["notifications"] = seed_notifications(db, org, residents, staff)
    return counts
