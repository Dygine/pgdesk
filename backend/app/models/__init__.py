"""
Model registry.

Alembic autogenerate only sees a table if its module has been imported, so every
model is re-exported here and `alembic/env.py` imports this package.
"""
from app.models.audit import AuditLog
from app.models.base import BranchMixin, TenantMixin, Timestamps, UUIDPrimaryKey
from app.models.branch import Branch, BranchPhoto
from app.models.billing import (
    GatewayOrder, Invoice, InvoiceItem, Payment, PaymentSettings,
)
from app.models.customer import Customer, ResidentDocument, ResidentKyc
from app.models.enums import (
    AuditAction, BedStatus, BillingCycle, BranchStatus, BuildingStatus, CustomerStatus,
    FloorStatus, GenderPolicy, OrganizationStatus, PlanStatus, PrincipalKind, RoomStatus,
    SubscriptionStatus, UserStatus,
)
from app.models.enquiry import EnquiryStatus, PgEnquiry
from app.models.login_code import LoginCode
from app.models.otp import OtpCode, OtpPurpose
from app.models.organization import Organization
from app.models.platform import SINGLETON_ID, LoginAttempt, PlatformSettings
from app.models.operations import (
    Attendance, FoodMenu, FoodWeekMenu, GateLog, GatePass, LaundryRequest, LaundrySlot,
    MealAttendance, Visitor,
)
from app.models.notice import CheckoutNotice
from app.models.staff import StaffMember
from app.models.property import Bed, Building, Floor, Room
from app.models.support import (
    Announcement, Asset, Complaint, ComplaintUpdate, Expense, InventoryItem,
    InventoryTransaction, Notification, OrganizationSettings, QueryMessage, SupportQuery,
)
from app.models.role import Permission, Role, role_permissions, user_branches, user_roles
from app.models.site import SiteBlock, SiteImage
from app.models.seeker import PgSeeker, SeekerSession
from app.models.subscription import Subscription, SubscriptionPlan
from app.models.token import PasswordResetToken, RefreshToken
from app.models.user import User

__all__ = [
    "Announcement", "Asset", "Attendance", "AuditAction", "AuditLog", "Bed", "BedStatus",
    "BillingCycle", "Branch", "BranchPhoto", "SiteBlock", "SiteImage", "BranchMixin", "Complaint", "ComplaintUpdate", "Expense",
    "FoodMenu", "GateLog", "GatePass", "InventoryItem", "InventoryTransaction",
    "Invoice", "InvoiceItem", "LaundryRequest", "LaundrySlot", "MealAttendance",
    "Notification", "OrganizationSettings", "Payment", "QueryMessage", "ResidentKyc",
    "SupportQuery", "Visitor",
    "CheckoutNotice", "FoodWeekMenu", "ResidentDocument", "GatewayOrder", "PaymentSettings", "StaffMember",
    "BranchStatus", "Building", "BuildingStatus", "Floor", "FloorStatus", "GenderPolicy",
    "Room", "RoomStatus",
    "Customer", "CustomerStatus", "Organization",
    "OtpCode",
    "PgEnquiry", "LoginCode", "PgSeeker", "SeekerSession",
    "EnquiryStatus",
    "OtpPurpose", "OrganizationStatus",
    "LoginAttempt", "PasswordResetToken", "Permission", "PlanStatus",
    "PlatformSettings",
    "PrincipalKind", "RefreshToken", "SINGLETON_ID",
    "Role", "Subscription", "SubscriptionPlan", "SubscriptionStatus", "TenantMixin",
    "Timestamps", "UUIDPrimaryKey", "User", "UserStatus",
    "role_permissions", "user_branches", "user_roles",
]
