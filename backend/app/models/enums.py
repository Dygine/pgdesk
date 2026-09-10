"""
Domain enumerations.

Stored as VARCHAR plus a CHECK constraint rather than a native Postgres ENUM:
adding a value to a native enum inside a migration is awkward and locks the
table, whereas a CHECK can be dropped and recreated cheaply. The database still
rejects an unknown value.

The constraints are created explicitly in migration 0004 - SQLAlchemy 2.0
defaults `Enum(create_constraint=False)`, so declaring the type here is not on
its own enough to enforce anything.
"""
from enum import StrEnum


class OrganizationStatus(StrEnum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    EXPIRING = "EXPIRING"        # inside the renewal window, still fully usable
    EXPIRED = "EXPIRED"          # lapsed: read-only, data retained
    SUSPENDED = "SUSPENDED"      # operator action: frozen, data retained
    INACTIVE = "INACTIVE"        # owner-requested pause
    CANCELLED = "CANCELLED"


class SubscriptionStatus(StrEnum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class BillingCycle(StrEnum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


class PlanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INVITED = "INVITED"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"


class BranchStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class CustomerStatus(StrEnum):
    """Resident lifecycle. Milestone 6 drives the transitions; auth only reads it."""
    ENQUIRY = "ENQUIRY"
    BOOKED = "BOOKED"
    RESERVED = "RESERVED"
    ACTIVE = "ACTIVE"
    NOTICE = "NOTICE"
    CHECKED_OUT = "CHECKED_OUT"
    ARCHIVED = "ARCHIVED"


class PrincipalKind(StrEnum):
    """Who is holding a token. Staff and residents are separate tables."""
    USER = "user"
    CUSTOMER = "customer"


class BuildingStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    UNDER_CONSTRUCTION = "UNDER_CONSTRUCTION"


class FloorStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class RoomStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"


class BedStatus(StrEnum):
    """
    Bed-level inventory is the unit a PG actually sells, so its state machine is
    the most important enum in the system.
    """
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"
    BLOCKED = "BLOCKED"

    @classmethod
    def sellable(cls) -> set[str]:
        return {cls.AVAILABLE, cls.RESERVED}

    @classmethod
    def filled(cls) -> set[str]:
        return {cls.OCCUPIED}


class GenderPolicy(StrEnum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    ANY = "ANY"


# --------------------------------------------------------------- finance --
class InvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class InvoiceItemKind(StrEnum):
    """Open-ended on purpose - a PG invents charges constantly."""
    RENT = "RENT"
    DEPOSIT = "DEPOSIT"
    FOOD = "FOOD"
    LAUNDRY = "LAUNDRY"
    ELECTRICITY = "ELECTRICITY"
    MAINTENANCE = "MAINTENANCE"
    LATE_FEE = "LATE_FEE"
    DISCOUNT = "DISCOUNT"
    OTHER = "OTHER"


class PaymentMethod(StrEnum):
    CASH = "CASH"
    UPI = "UPI"
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    ONLINE = "ONLINE"
    CHEQUE = "CHEQUE"
    ADJUSTMENT = "ADJUSTMENT"
    OTHER = "OTHER"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    REFUNDED = "REFUNDED"


# ------------------------------------------------------------ operations --
class AttendanceStatus(StrEnum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    ON_LEAVE = "ON_LEAVE"


class AttendanceSubject(StrEnum):
    RESIDENT = "RESIDENT"
    STAFF = "STAFF"


class GateDirection(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class VisitorStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INSIDE = "INSIDE"
    COMPLETED = "COMPLETED"


class GatePassStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class MealType(StrEnum):
    BREAKFAST = "BREAKFAST"
    LUNCH = "LUNCH"
    SNACK = "SNACK"
    DINNER = "DINNER"


class MealStatus(StrEnum):
    EXPECTED = "EXPECTED"
    ATTENDED = "ATTENDED"
    SKIPPED = "SKIPPED"
    OPTED_OUT = "OPTED_OUT"


class LaundrySlotStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    FULL = "FULL"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class LaundryRequestStatus(StrEnum):
    BOOKED = "BOOKED"
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    COLLECTED = "COLLECTED"
    CANCELLED = "CANCELLED"


class TicketPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ComplaintStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


class QueryStatus(StrEnum):
    OPEN = "OPEN"
    ANSWERED = "ANSWERED"
    CLOSED = "CLOSED"


class InventoryTxnType(StrEnum):
    STOCK_IN = "STOCK_IN"
    STOCK_OUT = "STOCK_OUT"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER = "TRANSFER"


class AssetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    MAINTENANCE = "MAINTENANCE"
    DAMAGED = "DAMAGED"
    LOST = "LOST"
    DISPOSED = "DISPOSED"


class KycStatus(StrEnum):
    NOT_SUBMITTED = "NOT_SUBMITTED"
    SUBMITTED = "SUBMITTED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class KycIdType(StrEnum):
    AADHAAR = "AADHAAR"
    PAN = "PAN"
    PASSPORT = "PASSPORT"
    DRIVING_LICENCE = "DRIVING_LICENCE"
    VOTER_ID = "VOTER_ID"
    OTHER = "OTHER"


class NotificationType(StrEnum):
    RENT_DUE = "RENT_DUE"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    PAYMENT_VERIFIED = "PAYMENT_VERIFIED"
    COMPLAINT_UPDATED = "COMPLAINT_UPDATED"
    VISITOR_REQUEST = "VISITOR_REQUEST"
    GATE_PASS = "GATE_PASS"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    SUBSCRIPTION = "SUBSCRIPTION"
    SYSTEM = "SYSTEM"


class AnnouncementAudience(StrEnum):
    ALL = "ALL"
    RESIDENTS = "RESIDENTS"
    STAFF = "STAFF"
    BRANCH = "BRANCH"


class PublishStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    # Recorded on every rejected sign-in. Separate from LOGIN so a security
    # review can filter for failures without parsing description text.
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ASSIGN = "ASSIGN"
    TRANSFER = "TRANSFER"
    CHECKIN = "CHECKIN"
    CHECKOUT = "CHECKOUT"
    SUSPEND = "SUSPEND"
    ACTIVATE = "ACTIVATE"
    EXTEND = "EXTEND"


def check_values(enum_cls: type[StrEnum]) -> list[str]:
    return [m.value for m in enum_cls]


# ------------------------------------------------------------ staff (HR) --
class StaffStatus(StrEnum):
    """The workforce list. Separate from login accounts: a cook has no login."""
    ACTIVE = "ACTIVE"
    ON_LEAVE = "ON_LEAVE"
    LEFT = "LEFT"


# ------------------------------------------------------- checkout notice --
class CheckoutNoticeStatus(StrEnum):
    SUBMITTED = "SUBMITTED"          # given, the office has not looked yet
    ACKNOWLEDGED = "ACKNOWLEDGED"    # the office has accepted the leaving date
    WITHDRAWN = "WITHDRAWN"          # the resident changed their mind
    CANCELLED = "CANCELLED"          # the office cancelled it
    COMPLETED = "COMPLETED"          # they checked out

    @classmethod
    def open(cls) -> set[str]:
        return {cls.SUBMITTED, cls.ACKNOWLEDGED}


# ------------------------------------------------------- online payments --
class PaymentSource(StrEnum):
    """Who put a payment into the system."""
    DESK = "desk"            # staff recorded it at the front desk
    RESIDENT = "resident"    # the resident paid by UPI/bank and typed the UTR
    RAZORPAY = "razorpay"    # confirmed by Razorpay's signature


class GatewayOrderStatus(StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    FAILED = "FAILED"
