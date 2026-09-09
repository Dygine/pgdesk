"""
Model registry.

Alembic autogenerate only sees a table if its module has been imported, so every
model is re-exported here and `alembic/env.py` imports this package.
"""
from app.models.audit import AuditLog
from app.models.base import BranchMixin, TenantMixin, Timestamps, UUIDPrimaryKey
from app.models.branch import Branch
from app.models.billing import Invoice, InvoiceItem, Payment
from app.models.customer import Customer, ResidentKyc
from app.models.enums import (
    AuditAction, BedStatus, BillingCycle, BranchStatus, BuildingStatus, CustomerStatus,
    FloorStatus, GenderPolicy, OrganizationStatus, PlanStatus, PrincipalKind, RoomStatus,
    SubscriptionStatus, UserStatus,
)
from app.models.organization import Organization
from app.models.platform import SINGLETON_ID, LoginAttempt, PlatformSettings
from app.models.operations import (
    Attendance, FoodMenu, GateLog, GatePass, LaundryRequest, LaundrySlot,
    MealAttendance, Visitor,
)
from app.models.property import Bed, Building, Floor, Room
from app.models.support import (
    Announcement, Asset, Complaint, ComplaintUpdate, Expense, InventoryItem,
    InventoryTransaction, Notification, OrganizationSettings, QueryMessage, SupportQuery,
)
from app.models.role import Permission, Role, role_permissions, user_branches, user_roles
from app.models.subscription import Subscription, SubscriptionPlan
from app.models.token import PasswordResetToken, RefreshToken
from app.models.user import User

__all__ = [
    "Announcement", "Asset", "Attendance", "AuditAction", "AuditLog", "Bed", "BedStatus",
    "BillingCycle", "Branch", "BranchMixin", "Complaint", "ComplaintUpdate", "Expense",
    "FoodMenu", "GateLog", "GatePass", "InventoryItem", "InventoryTransaction",
    "Invoice", "InvoiceItem", "LaundryRequest", "LaundrySlot", "MealAttendance",
    "Notification", "OrganizationSettings", "Payment", "QueryMessage", "ResidentKyc",
    "SupportQuery", "Visitor",
    "BranchStatus", "Building", "BuildingStatus", "Floor", "FloorStatus", "GenderPolicy",
    "Room", "RoomStatus",
    "Customer", "CustomerStatus", "Organization", "OrganizationStatus",
    "LoginAttempt", "PasswordResetToken", "Permission", "PlanStatus",
    "PlatformSettings",
    "PrincipalKind", "RefreshToken", "SINGLETON_ID",
    "Role", "Subscription", "SubscriptionPlan", "SubscriptionStatus", "TenantMixin",
    "Timestamps", "UUIDPrimaryKey", "User", "UserStatus",
    "role_permissions", "user_branches", "user_roles",
]
