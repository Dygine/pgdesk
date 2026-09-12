"""Simple accounts: profit and loss for a date range."""
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.dependencies import CurrentScope, DbSession, require, require_tenant
from app.core.responses import ok
from app.services.accounts_service import AccountsService

router = APIRouter(tags=["accounts"])
Tenant = Annotated[CurrentScope, Depends(require_tenant)]


@router.get("/accounts/pnl", summary="Profit and loss")
def profit_and_loss(db: DbSession, scope: Tenant, _: None = Depends(require("reports.view")),
                    from_date: date | None = None, to_date: date | None = None,
                    branch_id: uuid.UUID | None = None) -> dict:
    """Cash basis. Deposits, tax and capital purchases are reported but kept out of profit."""
    return ok(AccountsService(db, scope).pnl(
        from_date=from_date, to_date=to_date, branch_id=branch_id))


@router.get("/accounts/pnl/export", summary="Profit and loss as CSV")
def export_profit_and_loss(db: DbSession, scope: Tenant,
                           _: None = Depends(require("reports.export")),
                           from_date: date | None = None, to_date: date | None = None,
                           branch_id: uuid.UUID | None = None):
    service = AccountsService(db, scope)
    report = service.pnl(from_date=from_date, to_date=to_date, branch_id=branch_id)
    return Response(
        content=service.to_csv(report), media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="pgguru-pnl-{report["from_date"]}-{report["to_date"]}.csv"'})
