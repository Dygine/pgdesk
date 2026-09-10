"""
Request contracts for the operational modules.

Responses are shaped by the routers rather than declared here: they nest heavily
(an invoice carries its items and payments, a resident carries its placement)
and a parallel set of read models would be one more thing to keep in step for no
gain. The write side is where validation earns its keep, so that is what is
modelled.
"""
import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, EmailStr, Field, field_validator


# --------------------------------------------------------------- residents
class ResidentCreate(BaseModel):
    branch_id: uuid.UUID
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str = Field(min_length=6, max_length=20)
    alternate_phone: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    occupation: str | None = None

    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relation: str | None = None

    joining_date: date | None = None
    expected_checkout_date: date | None = None
    monthly_rent: float = Field(default=0, ge=0)
    security_deposit: float = Field(default=0, ge=0)
    rent_due_day: int = Field(default=5, ge=1, le=28)
    status: str | None = None
    notes: str | None = None

    bed_id: uuid.UUID | None = None
    create_portal_login: bool = Field(
        default=False, description="Issue a temporary password for the resident portal.")

    @field_validator("full_name")
    @classmethod
    def _need_a_name(cls, v, info):
        if v:
            return v.strip()
        return v


class ResidentUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    #: Editable, because it becomes the sign-in ID when portal access is given
    #: later. Sending null removes it - refused while a login depends on it.
    email: EmailStr | None = None
    phone: str | None = None
    alternate_phone: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    occupation: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relation: str | None = None
    joining_date: date | None = None
    expected_checkout_date: date | None = None
    monthly_rent: float | None = Field(default=None, ge=0)
    security_deposit: float | None = Field(default=None, ge=0)
    rent_due_day: int | None = Field(default=None, ge=1, le=28)
    status: str | None = None
    notes: str | None = None


class PortalAccessRequest(BaseModel):
    """Optional email, saved on the resident first when they have none yet."""
    email: EmailStr | None = None


class BedAssignment(BaseModel):
    bed_id: uuid.UUID


class CheckInRequest(BaseModel):
    """
    Everything agreed at the desk when someone moves in.

    Rent is required rather than optional-with-a-fallback: a resident checked in
    at zero rent bills nothing every month afterwards, and that is a mistake
    nobody notices until the month closes.
    """
    bed_id: uuid.UUID
    joining_date: date | None = None
    monthly_rent: float = Field(gt=0, le=10_000_000)
    security_deposit: float | None = Field(default=None, ge=0, le=10_000_000)
    meal_plan: str | None = Field(default=None, max_length=40)
    billing_cycle: str | None = Field(default=None, max_length=20)
    rent_due_day: int | None = Field(default=None, ge=1, le=28)
    raise_invoice: bool = True
    food_charge: float | None = Field(default=None, ge=0, le=1_000_000)
    notes: str | None = Field(default=None, max_length=2000)


class TransferRequest(BaseModel):
    bed_id: uuid.UUID
    reason: str | None = None


class CheckoutRequest(BaseModel):
    checkout_date: date | None = None
    notes: str | None = None


class KycCreate(BaseModel):
    id_type: str = Field(description="AADHAAR | PAN | PASSPORT | DRIVING_LICENCE | VOTER_ID | OTHER")
    id_number: str = Field(min_length=4, max_length=80)
    document_reference: str | None = None
    notes: str | None = None


class KycDecision(BaseModel):
    approved: bool
    notes: str | None = None


# ----------------------------------------------------------------- billing
class InvoiceLine(BaseModel):
    kind: str = "OTHER"
    description: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, gt=0)
    unit_price: float = Field(default=0, ge=0)
    amount: float | None = Field(default=None, ge=0)


class InvoiceCreate(BaseModel):
    resident_id: uuid.UUID
    invoice_date: date | None = None
    due_date: date | None = None
    period: date | None = None
    tax: float = Field(default=0, ge=0)
    late_fee: float = Field(default=0, ge=0)
    notes: str | None = None
    items: list[InvoiceLine] = Field(min_length=1)


class InvoiceUpdate(BaseModel):
    due_date: date | None = None
    tax: float | None = Field(default=None, ge=0)
    late_fee: float | None = Field(default=None, ge=0)
    notes: str | None = None
    items: list[InvoiceLine] | None = None


class InvoiceCancel(BaseModel):
    reason: str | None = None


class RentRun(BaseModel):
    period: date | None = Field(
        default=None, description="Any date in the target month. Defaults to today.")
    branch_id: uuid.UUID | None = None


class PaymentCreate(BaseModel):
    resident_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    amount: float = Field(gt=0)
    payment_date: date | None = None
    method: str = "CASH"
    reference: str | None = None
    notes: str | None = None
    auto_verify: bool = Field(
        default=False,
        description="Requires payments.verify. Records and confirms in one step.")


class PaymentDecision(BaseModel):
    approved: bool
    note: str | None = None


class RefundRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


# -------------------------------------------------------------- attendance
class AttendanceMark(BaseModel):
    resident_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    on_date: date | None = None
    status: str = "PRESENT"
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    source: str = "manual"
    notes: str | None = None


class ScanRequest(BaseModel):
    token: str = Field(min_length=8, max_length=120)
    direction: str | None = Field(default=None, description="ENTRY | EXIT. Inferred when omitted.")
    gate: str | None = None


class SelfScanRequest(BaseModel):
    """
    A resident scanning the gate's code from their own phone.

    No `direction` field, unlike `ScanRequest`. The guard's screen offers a
    manual override because a guard sometimes has to correct a mis-scan; a
    resident choosing their own direction could simply declare themselves
    present, which is the one thing this endpoint exists to prevent. It is
    always inferred from the last accepted movement.

    No resident id either - it comes from the token.
    """

    token: str = Field(min_length=8, max_length=120)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    #: Metres, as reported by the device. Optional because a browser may not
    #: supply it, but a value worse than the service threshold is refused: an
    #: imprecise reading cannot show anyone was inside a 150 metre circle.
    accuracy_m: float | None = Field(default=None, ge=0, le=100_000)


# ---------------------------------------------------------------- visitors
class VisitorCreate(BaseModel):
    resident_id: uuid.UUID
    name: str = Field(min_length=2, max_length=160)
    phone: str | None = None
    relation: str | None = None
    purpose: str | None = None
    expected_at: datetime | None = None
    id_proof_reference: str | None = None
    notes: str | None = None


class ApprovalDecision(BaseModel):
    approved: bool
    note: str | None = None


class GatePassCreate(BaseModel):
    resident_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=300)
    destination: str | None = None
    from_at: datetime
    to_at: datetime
    is_emergency: bool = False


class StatusChange(BaseModel):
    status: str


# -------------------------------------------------------------------- food
class MenuUpsert(BaseModel):
    branch_id: uuid.UUID
    on_date: date
    meal: str = Field(description="BREAKFAST | LUNCH | SNACK | DINNER")
    items: str = Field(min_length=1)
    calories: int | None = Field(default=None, ge=0)
    serve_from: time | None = None
    serve_to: time | None = None
    notes: str | None = None


class MealMark(BaseModel):
    resident_id: uuid.UUID
    on_date: date | None = None
    meal: str
    status: str = "EXPECTED"


# ----------------------------------------------------------------- laundry
class SlotCreate(BaseModel):
    branch_id: uuid.UUID
    on_date: date
    start_time: time
    end_time: time
    capacity: int = Field(default=10, ge=1, le=200)
    status: str | None = None


class SlotBooking(BaseModel):
    slot_id: uuid.UUID
    resident_id: uuid.UUID | None = None
    item_count: int = Field(default=1, ge=1, le=100)
    notes: str | None = None


# -------------------------------------------------------------- complaints
class ComplaintCreate(BaseModel):
    resident_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    category: str = "Other"
    subject: str = Field(min_length=3, max_length=200)
    description: str | None = None
    priority: str = "MEDIUM"


class ComplaintUpdateIn(BaseModel):
    status: str | None = None
    priority: str | None = None
    category: str | None = None
    subject: str | None = None
    assigned_to_id: uuid.UUID | None = None
    resolution: str | None = None
    message: str | None = None
    is_internal: bool = False


# ----------------------------------------------------------------- queries
class QueryCreate(BaseModel):
    resident_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    category: str = "General"
    subject: str = Field(min_length=3, max_length=200)
    message: str | None = None


class QueryReply(BaseModel):
    message: str = Field(min_length=1)
    close: bool = False


# ---------------------------------------------------------------- expenses
class ExpenseCreate(BaseModel):
    branch_id: uuid.UUID
    category: str = "Other"
    amount: float = Field(gt=0)
    spent_on: date | None = None
    vendor: str | None = None
    payment_method: str | None = None
    reference: str | None = None
    description: str | None = None
    attachment_reference: str | None = None


class ExpenseUpdate(BaseModel):
    category: str | None = None
    amount: float | None = Field(default=None, gt=0)
    spent_on: date | None = None
    vendor: str | None = None
    payment_method: str | None = None
    reference: str | None = None
    description: str | None = None


# --------------------------------------------------------------- inventory
class InventoryCreate(BaseModel):
    branch_id: uuid.UUID
    sku: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    category: str = "Other"
    unit: str = "pcs"
    quantity: float = Field(default=0, ge=0)
    minimum_stock: float = Field(default=0, ge=0)
    location: str | None = None
    supplier: str | None = None
    purchase_price: float = Field(default=0, ge=0)


class StockAdjustment(BaseModel):
    txn_type: str = Field(description="STOCK_IN | STOCK_OUT | ADJUSTMENT | TRANSFER")
    quantity: float = Field(gt=0)
    reference: str | None = None
    notes: str | None = None


# ------------------------------------------------------------------ assets
class AssetCreate(BaseModel):
    branch_id: uuid.UUID
    asset_code: str | None = None
    name: str = Field(min_length=1, max_length=160)
    category: str = "Other"
    purchase_date: date | None = None
    purchase_price: float = Field(default=0, ge=0)
    warranty_until: date | None = None
    location: str | None = None
    room_id: uuid.UUID | None = None
    assigned_to_id: uuid.UUID | None = None
    status: str | None = None
    notes: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    purchase_date: date | None = None
    purchase_price: float | None = Field(default=None, ge=0)
    warranty_until: date | None = None
    location: str | None = None
    room_id: uuid.UUID | None = None
    assigned_to_id: uuid.UUID | None = None
    status: str | None = None
    notes: str | None = None


# ----------------------------------------------------------- announcements
class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=1)
    audience: str = "ALL"
    priority: str = "MEDIUM"
    status: str = "PUBLISHED"
    branch_id: uuid.UUID | None = None
    starts_on: date | None = None
    ends_on: date | None = None


class AnnouncementUpdate(BaseModel):
    title: str | None = None
    message: str | None = None
    audience: str | None = None
    priority: str | None = None
    status: str | None = None
    branch_id: uuid.UUID | None = None
    starts_on: date | None = None
    ends_on: date | None = None


# ---------------------------------------------------------------- settings
class SettingsUpdate(BaseModel):
    currency: str | None = None
    timezone: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    rent_due_day: int | None = Field(default=None, ge=1, le=28)
    late_fee_amount: float | None = Field(default=None, ge=0)
    late_fee_after_days: int | None = Field(default=None, ge=0, le=90)
    invoice_prefix: str | None = Field(default=None, max_length=10)
    gate_duplicate_window_seconds: int | None = Field(default=None, ge=0, le=3600)
    visitor_approval_required: bool | None = None
    gate_pass_approval_required: bool | None = None
    food_enabled: bool | None = None
    laundry_enabled: bool | None = None
    meal_optout_cutoff_hours: int | None = Field(default=None, ge=0, le=48)
    extra: dict | None = None
