"""Residents, KYC and the bed lifecycle."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import CurrentScope, DbSession, require, require_tenant
from app.core.responses import ok, paginated
from app.models import Bed, Branch, Building, Customer, Floor, Room
from app.schemas.operations import (
    DocumentUpload, NoticeCreate, NoticeDecision,
    BedAssignment, CheckInRequest, CheckoutRequest, KycCreate, KycDecision,
    PortalAccessRequest, ResidentCreate, ResidentUpdate, TransferRequest,
)
from app.services.notice_service import CheckoutNoticeService, notice_payload
from app.services.resident_service import ResidentDocumentService, ResidentService

router = APIRouter(tags=["residents"])
Tenant = Annotated[CurrentScope, Depends(require_tenant)]


def _svc(db, scope) -> ResidentService:
    return ResidentService(db, scope)


def _resident(db, r: Customer, *, detail: bool = False) -> dict:
    payload = {
        "id": str(r.id), "full_name": r.full_name,
        "first_name": r.first_name, "last_name": r.last_name,
        "email": r.email, "phone": r.phone, "alternate_phone": r.alternate_phone,
        "gender": r.gender, "status": r.status, "is_active": r.is_active,
        "branch_id": str(r.branch_id) if r.branch_id else None,
        "building_id": str(r.building_id) if r.building_id else None,
        "floor_id": str(r.floor_id) if r.floor_id else None,
        "room_id": str(r.room_id) if r.room_id else None,
        "bed_id": str(r.bed_id) if r.bed_id else None,
        "monthly_rent": float(r.monthly_rent),
        "security_deposit": float(r.security_deposit),
        "rent_due_day": r.rent_due_day,
        "joining_date": r.joining_date.isoformat() if r.joining_date else None,
        "expected_checkout_date": (r.expected_checkout_date.isoformat()
                                   if r.expected_checkout_date else None),
        "actual_checkout_date": (r.actual_checkout_date.isoformat()
                                 if r.actual_checkout_date else None),
        "has_portal_login": bool(r.password_hash),
        # Still on the owner-issued temporary password. The profile screen uses
        # it to decide between "show a new sign-in QR" and "reset password".
        "must_change_password": bool(r.password_hash) and bool(r.must_change_password),
        "last_login_at": r.last_login_at.isoformat() if r.last_login_at else None,
        "created_at": r.created_at.isoformat(),
    }

    # The placement is resolved into names, because every screen showing a
    # resident wants "Room 204, Bed B" rather than four opaque ids.
    room = db.get(Room, r.room_id) if r.room_id else None
    bed = db.get(Bed, r.bed_id) if r.bed_id else None
    branch = db.get(Branch, r.branch_id) if r.branch_id else None
    payload["placement"] = {
        "branch": branch.name if branch else None,
        "branch_code": branch.code if branch else None,
        "building": (db.get(Building, r.building_id).name if r.building_id else None),
        "floor": (db.get(Floor, r.floor_id).name if r.floor_id else None),
        "room": room.room_number if room else None,
        "room_type": room.room_type if room else None,
        "bed": (bed.bed_code or bed.bed_number) if bed else None,
        "bed_number": bed.bed_number if bed else None,
    }

    if detail:
        payload.update({
            "date_of_birth": r.date_of_birth.isoformat() if r.date_of_birth else None,
            "address": r.address, "city": r.city, "state": r.state,
            "pincode": r.pincode, "occupation": r.occupation,
            "emergency_contact_name": r.emergency_contact_name,
            "emergency_contact_phone": r.emergency_contact_phone,
            "emergency_contact_relation": r.emergency_contact_relation,
            "notes": r.notes,
            # The token itself is never sent to a staff screen - only whether
            # one exists. The resident sees their own in the portal.
            "has_qr": bool(r.qr_token),
        })
    return payload


# ----------------------------------------------------------------- listing
@router.get("/residents", summary="List residents")
def list_residents(db: DbSession, scope: Tenant,
                   _: None = Depends(require("customers.view")),
                   search: str | None = None,
                   status_filter: str | None = Query(default=None, alias="status"),
                   branch_id: uuid.UUID | None = None,
                   room_id: uuid.UUID | None = None,
                   page: int = Query(default=1, ge=1),
                   page_size: int = Query(default=25, ge=1, le=200)) -> dict:
    rows, total = _svc(db, scope).list(
        search=search, status=status_filter, branch_id=branch_id,
        room_id=room_id, page=page, page_size=page_size)
    return paginated([_resident(db, r) for r in rows], page, page_size, total)


@router.get("/residents/available-beds", summary="Beds a resident could be placed in")
def available_beds(db: DbSession, scope: Tenant,
                   _: None = Depends(require("customers.view", "beds.view")),
                   branch_id: uuid.UUID | None = None,
                   for_resident: uuid.UUID | None = None) -> dict:
    """
    `for_resident` also returns the bed reserved for that person, which is
    otherwise excluded for not being AVAILABLE.
    """
    return ok(_svc(db, scope).available_beds(branch_id, for_resident=for_resident))


@router.get("/residents/{resident_id}", summary="Resident detail")
def get_resident(resident_id: uuid.UUID, db: DbSession, scope: Tenant,
                 _: None = Depends(require("customers.view"))) -> dict:
    return ok(_resident(db, _svc(db, scope).get(resident_id), detail=True))


# ---------------------------------------------------------------- mutating
@router.post("/residents", status_code=status.HTTP_201_CREATED, summary="Create a resident")
def create_resident(body: ResidentCreate, db: DbSession, scope: Tenant,
                    _: None = Depends(require("customers.create"))) -> dict:
    """Counts against the plan's resident limit. A bed may be assigned inline."""
    resident, credentials = _svc(db, scope).create(body.model_dump())
    db.commit()
    db.refresh(resident)
    payload = _resident(db, resident, detail=True)
    if credentials:
        payload["credentials"] = credentials
    return ok(payload, message=f"{resident.full_name} added.")


@router.patch("/residents/{resident_id}", summary="Edit a resident")
def update_resident(resident_id: uuid.UUID, body: ResidentUpdate, db: DbSession,
                    scope: Tenant, _: None = Depends(require("customers.edit"))) -> dict:
    resident = _svc(db, scope).update(resident_id, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(resident)
    return ok(_resident(db, resident, detail=True), message="Resident updated.")


# ------------------------------------------------------------ portal access
#
# The temporary password in these responses is shown once and stored only as a
# hash. The login code is a 30-minute, single-use key drawn as a QR on the
# owner's screen - see app/models/login_code.py for why the QR never carries the
# password itself.
@router.post("/residents/{resident_id}/portal-access", summary="Give a portal login")
def grant_portal_access(resident_id: uuid.UUID, db: DbSession, scope: Tenant,
                        body: PortalAccessRequest | None = None,
                        _: None = Depends(require("customers.edit"))) -> dict:
    resident, credentials = _svc(db, scope).grant_portal_access(
        resident_id, email=body.email if body else None)
    db.commit()
    db.refresh(resident)
    payload = _resident(db, resident, detail=True)
    payload["credentials"] = credentials
    return ok(payload, message=f"{resident.full_name} can now sign in.")


@router.post("/residents/{resident_id}/reset-password", summary="Reset their portal password")
def reset_portal_password(resident_id: uuid.UUID, db: DbSession, scope: Tenant,
                          _: None = Depends(require("customers.edit"))) -> dict:
    resident, credentials = _svc(db, scope).reset_portal_password(resident_id)
    db.commit()
    db.refresh(resident)
    payload = _resident(db, resident, detail=True)
    payload["credentials"] = credentials
    return ok(payload, message="New sign-in details issued. Old sessions were signed out.")


@router.post("/residents/{resident_id}/login-code", summary="A fresh 30-minute sign-in QR")
def issue_login_code(resident_id: uuid.UUID, db: DbSession, scope: Tenant,
                     _: None = Depends(require("customers.edit"))) -> dict:
    resident, credentials = _svc(db, scope).issue_login_code(resident_id)
    db.commit()
    return ok({"id": str(resident.id), "credentials": credentials},
              message="New sign-in QR ready. It works for 30 minutes.")


@router.delete("/residents/{resident_id}/portal-access", summary="Turn portal access off")
def revoke_portal_access(resident_id: uuid.UUID, db: DbSession, scope: Tenant,
                         _: None = Depends(require("customers.edit"))) -> dict:
    resident = _svc(db, scope).revoke_portal_access(resident_id)
    db.commit()
    db.refresh(resident)
    return ok(_resident(db, resident, detail=True), message="Portal access turned off.")


@router.post("/residents/{resident_id}/assign-bed", summary="Assign a bed")
def assign_bed(resident_id: uuid.UUID, body: BedAssignment, db: DbSession, scope: Tenant,
               _: None = Depends(require("customers.assign_bed", "beds.assign"))) -> dict:
    """
    Locks the bed before reading its state, so two staff assigning the last free
    bed at the same moment cannot both succeed.
    """
    resident = _svc(db, scope).assign_bed(resident_id, body.bed_id)
    db.commit()
    db.refresh(resident)
    return ok(_resident(db, resident, detail=True), message="Bed assigned.")


@router.post("/residents/{resident_id}/check-in", summary="Check a resident in")
def check_in(resident_id: uuid.UUID, body: CheckInRequest, db: DbSession, scope: Tenant,
             _: None = Depends(require("customers.assign_bed", "beds.assign"))) -> dict:
    """
    Place a resident on a bed, record the agreed terms and raise the first
    invoice - in one transaction.

    The single commit is the point. Assigning the bed and raising the invoice as
    two requests leaves a window where the bed is taken and nothing is billed;
    if the second call fails the desk has no way to tell. Here either both land
    or neither does.
    """
    resident, invoice = _svc(db, scope).check_in(
        resident_id,
        bed_id=body.bed_id,
        joining_date=body.joining_date,
        monthly_rent=body.monthly_rent,
        security_deposit=body.security_deposit,
        meal_plan=body.meal_plan,
        billing_cycle=body.billing_cycle,
        rent_due_day=body.rent_due_day,
        raise_invoice=body.raise_invoice,
        food_charge=body.food_charge,
        notes=body.notes,
    )
    db.commit()
    db.refresh(resident)

    payload = _resident(db, resident, detail=True)
    payload["invoice"] = None
    if invoice is not None:
        db.refresh(invoice)
        payload["invoice"] = {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "total": float(invoice.total),
            "due_date": invoice.due_date.isoformat(),
        }
    return ok(payload, message=f"{resident.full_name} checked in.")


@router.post("/residents/{resident_id}/reserve-bed", summary="Hold a bed")
def reserve_bed(resident_id: uuid.UUID, body: BedAssignment, db: DbSession, scope: Tenant,
                _: None = Depends(require("customers.assign_bed", "beds.assign"))) -> dict:
    resident = _svc(db, scope).reserve_bed(resident_id, body.bed_id)
    db.commit()
    db.refresh(resident)
    return ok(_resident(db, resident, detail=True), message="Bed reserved.")


@router.post("/residents/{resident_id}/transfer", summary="Move to another bed")
def transfer(resident_id: uuid.UUID, body: TransferRequest, db: DbSession, scope: Tenant,
             _: None = Depends(require("customers.transfer"))) -> dict:
    """Old bed released and new bed taken in one transaction, both rows locked."""
    resident = _svc(db, scope).transfer(resident_id, body.bed_id, body.reason)
    db.commit()
    db.refresh(resident)
    return ok(_resident(db, resident, detail=True), message="Resident transferred.")


@router.post("/residents/{resident_id}/checkout", summary="Check a resident out")
def checkout(resident_id: uuid.UUID, body: CheckoutRequest, db: DbSession, scope: Tenant,
             _: None = Depends(require("customers.checkout"))) -> dict:
    """Frees the bed. The placement history stays on the resident record."""
    resident = _svc(db, scope).checkout(
        resident_id, checkout_date=body.checkout_date, notes=body.notes)
    db.commit()
    db.refresh(resident)
    return ok(_resident(db, resident, detail=True), message="Resident checked out.")


@router.post("/residents/{resident_id}/reissue-qr", summary="Issue a new gate QR")
def reissue_qr(resident_id: uuid.UUID, db: DbSession, scope: Tenant,
               _: None = Depends(require("customers.edit"))) -> dict:
    resident = _svc(db, scope).rotate_qr(resident_id)
    db.commit()
    return ok({"id": str(resident.id)}, message="A new QR has been issued.")


# --------------------------------------------------------------------- KYC
@router.get("/residents/{resident_id}/kyc", summary="Identity documents")
def list_kyc(resident_id: uuid.UUID, db: DbSession, scope: Tenant,
             _: None = Depends(require("customers.view"))) -> dict:
    """
    Numbers come back masked unless the caller holds `customers.kyc_view`.

    Masking here rather than in the browser: an unmasked number that reaches the
    client has already left the building, whatever the UI then does with it.
    """
    unmasked = scope.can("customers.kyc_view")
    return ok(_svc(db, scope).list_kyc(resident_id, unmasked=unmasked))


@router.post("/residents/{resident_id}/kyc", status_code=status.HTTP_201_CREATED,
             summary="Record an identity document")
def add_kyc(resident_id: uuid.UUID, body: KycCreate, db: DbSession, scope: Tenant,
            _: None = Depends(require("customers.edit"))) -> dict:
    row = _svc(db, scope).add_kyc(resident_id, body.model_dump())
    db.commit()
    return ok({"id": str(row.id), "id_type": row.id_type,
               "id_number": row.masked_number, "status": row.status},
              message="Document recorded.")


@router.post("/residents/kyc/{kyc_id}/verify", summary="Verify or reject a document")
def verify_kyc(kyc_id: uuid.UUID, body: KycDecision, db: DbSession, scope: Tenant,
               _: None = Depends(require("customers.kyc_verify"))) -> dict:
    """Verification is a human decision - nothing here checks the number itself."""
    row = _svc(db, scope).verify_kyc(kyc_id, approved=body.approved, notes=body.notes)
    db.commit()
    return ok({"id": str(row.id), "status": row.status},
              message=f"Document {row.status.lower()}.")


# ------------------------------------------------------- checkout notices
@router.get("/checkout-notices", summary="Residents who have given notice")
def list_notices(db: DbSession, scope: Tenant,
                 _: None = Depends(require("customers.view")),
                 status_filter: str | None = Query(default="open", alias="status"),
                 branch_id: uuid.UUID | None = None) -> dict:
    rows = CheckoutNoticeService(db).list(scope, status=status_filter, branch_id=branch_id)
    return ok([notice_payload(db, n) for n in rows])


@router.post("/checkout-notices/{notice_id}/acknowledge", summary="Accept a notice")
def acknowledge_notice(notice_id: uuid.UUID, db: DbSession, scope: Tenant,
                       body: NoticeDecision | None = None,
                       _: None = Depends(require("customers.checkout"))) -> dict:
    notice = CheckoutNoticeService(db).acknowledge(
        scope, notice_id, note=body.note if body else None,
        planned_date=body.planned_checkout_date if body else None)
    db.commit()
    return ok(notice_payload(db, notice), message="Notice acknowledged. The resident was told.")


@router.post("/checkout-notices/{notice_id}/cancel", summary="Cancel a notice")
def cancel_notice(notice_id: uuid.UUID, db: DbSession, scope: Tenant,
                  body: NoticeDecision | None = None,
                  _: None = Depends(require("customers.checkout"))) -> dict:
    notice = CheckoutNoticeService(db).cancel(scope, notice_id,
                                              note=body.note if body else None)
    db.commit()
    return ok(notice_payload(db, notice), message="Notice cancelled.")


@router.post("/residents/{resident_id}/checkout-notice", status_code=status.HTTP_201_CREATED,
             summary="Record notice a resident gave in person")
def record_notice(resident_id: uuid.UUID, body: NoticeCreate, db: DbSession, scope: Tenant,
                  _: None = Depends(require("customers.checkout"))) -> dict:
    resident = _svc(db, scope).get(resident_id)
    notice = CheckoutNoticeService(db).give(
        resident, planned_date=body.planned_checkout_date, reason=body.reason, scope=scope)
    db.commit()
    return ok(notice_payload(db, notice), message=f"Notice recorded for {resident.full_name}.")


# ------------------------------------------------------- scanned documents
def _document(d, *, with_image: bool) -> dict:
    import base64
    payload = {
        "id": str(d.id), "doc_type": d.doc_type, "label": d.label,
        "mime_type": d.mime_type, "size_bytes": d.size_bytes,
        "width": d.width, "height": d.height, "source": d.source,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
    if with_image:
        payload["data_url"] = (f"data:{d.mime_type};base64,"
                               f"{base64.b64encode(d.content).decode()}")
    return payload


@router.get("/residents/{resident_id}/documents", summary="Scanned ID documents")
def list_documents(resident_id: uuid.UUID, db: DbSession, scope: Tenant,
                   _: None = Depends(require("customers.view"))) -> dict:
    """
    The images themselves only go to someone holding `customers.kyc_view` - the
    same rule as full ID numbers. Everyone else sees that a document exists.
    """
    from app.models.customer import DOCUMENT_MAX_BYTES, DOCUMENTS_PER_RESIDENT
    can_view = scope.can("customers.kyc_view")
    rows = ResidentDocumentService(db, scope).list(resident_id)
    return ok({"items": [_document(d, with_image=can_view) for d in rows],
               "can_view_images": can_view, "max_bytes": DOCUMENT_MAX_BYTES,
               "max_documents": DOCUMENTS_PER_RESIDENT})


@router.post("/residents/{resident_id}/documents", status_code=status.HTTP_201_CREATED,
             summary="Add a scanned document (max 3, each under 5 KB)")
def add_document(resident_id: uuid.UUID, body: DocumentUpload, db: DbSession, scope: Tenant,
                 _: None = Depends(require("customers.edit", "customers.create"))) -> dict:
    row = ResidentDocumentService(db, scope).add(
        resident_id, doc_type=body.doc_type, image=body.image, label=body.label,
        source=body.source, width=body.width, height=body.height)
    db.commit()
    db.refresh(row)
    return ok(_document(row, with_image=scope.can("customers.kyc_view")),
              message="Document saved.")


@router.delete("/residents/{resident_id}/documents/{document_id}",
               summary="Delete a scanned document")
def delete_document(resident_id: uuid.UUID, document_id: uuid.UUID, db: DbSession,
                    scope: Tenant, _: None = Depends(require("customers.edit"))) -> dict:
    ResidentDocumentService(db, scope).delete(resident_id, document_id)
    db.commit()
    return ok(None, message="Document deleted.")
