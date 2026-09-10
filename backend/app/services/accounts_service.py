"""
A simple profit and loss for a PG owner.

Cash basis, because that is how a PG owner thinks about the month: money that
actually came in (verified payments) against money that actually went out
(expenses, salaries included). What was billed is shown next to it for
comparison, but profit is never computed from bills nobody has paid.

Three things are deliberately kept OUT of profit:

  * **Security deposits.** They are refundable, so they are a liability, not
    income. Counting them would make every move-in month look like a windfall
    and every move-out month like a loss.
  * **Tax collected** on invoices, which is owed onward.
  * **Assets and stock bought.** A new geyser is capital; stock added to the
    store room is valued at purchase price. Both are shown for information. If
    the supplier bill should count against profit, record it under Expenses.

A payment is not itemised, so it is shared across the lines of its invoice in
proportion to their amounts. A Rs 15,000 payment against a Rs 10,000 rent +
Rs 20,000 deposit invoice is counted as Rs 5,000 rent and Rs 10,000 deposit.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import CurrentScope
from app.core.exceptions import ConflictError, PermissionDeniedError
from app.models import (
    Asset, Expense, InventoryItem, InventoryTransaction, Invoice, Payment,
)
from app.models.enums import InvoiceItemKind, InvoiceStatus, PaymentStatus

LABELS = {
    "RENT": "Rent", "FOOD": "Food", "LAUNDRY": "Laundry", "ELECTRICITY": "Electricity",
    "MAINTENANCE": "Maintenance charges", "LATE_FEE": "Late fees",
    "OTHER": "Other charges", "ADVANCE": "Payments not tied to an invoice",
}


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def _split(payment: Payment) -> dict[str, float]:
    """Share one verified payment across its invoice's lines."""
    amount = float(payment.amount)
    invoice = payment.invoice
    if invoice is None:
        return {"ADVANCE": amount}
    weights: list[tuple[str, float]] = [
        (str(i.kind), float(i.amount)) for i in invoice.items
        if i.kind != InvoiceItemKind.DISCOUNT and float(i.amount) > 0]
    if float(invoice.late_fee or 0) > 0:
        weights.append(("LATE_FEE", float(invoice.late_fee)))
    if float(invoice.tax or 0) > 0:
        weights.append(("TAX", float(invoice.tax)))
    gross = sum(w for _, w in weights)
    if gross <= 0:
        return {"OTHER": amount}
    out: dict[str, float] = defaultdict(float)
    for kind, w in weights:
        out[kind] += amount * w / gross
    return out


class AccountsService:
    def __init__(self, db: Session, scope: CurrentScope):
        self.db = db
        self.scope = scope

    @property
    def org_id(self) -> uuid.UUID:
        return self.scope.organization_id

    def _branches(self, branch_id: uuid.UUID | None) -> list[uuid.UUID]:
        if branch_id:
            if not self.scope.owns_branch(branch_id):
                raise PermissionDeniedError(
                    "Branch access denied. You are not assigned to this branch.")
            return [branch_id]
        return list(self.scope.branch_ids) or [uuid.UUID(int=0)]

    def _verified(self, branches, start: date, end: date) -> list[Payment]:
        return list(self.db.scalars(
            select(Payment)
            .options(selectinload(Payment.invoice).selectinload(Invoice.items))
            .where(Payment.organization_id == self.org_id,
                   Payment.branch_id.in_(branches),
                   Payment.status == PaymentStatus.VERIFIED,
                   Payment.payment_date >= start, Payment.payment_date <= end)).all())

    def pnl(self, *, from_date: date | None = None, to_date: date | None = None,
            branch_id: uuid.UUID | None = None) -> dict:
        today = date.today()
        start = from_date or _month_start(today)
        end = to_date or today
        if end < start:
            raise ConflictError("The end date is before the start date.")
        if (end - start).days > 731:
            raise ConflictError("Pick a range of two years or less.")
        branches = self._branches(branch_id)

        # ------------------------------------------------ money that came in
        collected: dict[str, float] = defaultdict(float)
        for p in self._verified(branches, start, end):
            for kind, value in _split(p).items():
                collected[kind] += value
        deposits_in = collected.pop("DEPOSIT", 0.0)
        tax_in = collected.pop("TAX", 0.0)

        # -------------------------------------------------------- what billed
        billed: dict[str, float] = defaultdict(float)
        deposits_billed = discounts = 0.0
        invoices = self.db.scalars(
            select(Invoice).options(selectinload(Invoice.items))
            .where(Invoice.organization_id == self.org_id,
                   Invoice.branch_id.in_(branches),
                   Invoice.status != InvoiceStatus.CANCELLED,
                   Invoice.invoice_date >= start, Invoice.invoice_date <= end)).all()
        for inv in invoices:
            for item in inv.items:
                if item.kind == InvoiceItemKind.DISCOUNT:
                    discounts += float(item.amount)
                elif item.kind == InvoiceItemKind.DEPOSIT:
                    deposits_billed += float(item.amount)
                else:
                    billed[str(item.kind)] += float(item.amount)
            if float(inv.late_fee or 0) > 0:
                billed["LATE_FEE"] += float(inv.late_fee)

        kinds = sorted(set(collected) | set(billed),
                       key=lambda k: (-collected.get(k, 0), LABELS.get(k, k)))
        income_lines = [
            {"kind": k, "label": LABELS.get(k, k.replace("_", " ").title()),
             "collected": round(collected.get(k, 0), 2), "billed": round(billed.get(k, 0), 2)}
            for k in kinds]
        income_total = round(sum(collected.values()), 2)

        # ------------------------------------------------ money that went out
        expense_rows = self.db.execute(
            select(Expense.category, func.sum(Expense.amount), func.count(Expense.id))
            .where(Expense.organization_id == self.org_id,
                   Expense.branch_id.in_(branches),
                   Expense.spent_on >= start, Expense.spent_on <= end)
            .group_by(Expense.category)).all()
        expense_lines = sorted(
            [{"category": c, "amount": round(float(a or 0), 2), "count": n}
             for c, a, n in expense_rows], key=lambda r: -r["amount"])
        expense_total = round(sum(r["amount"] for r in expense_lines), 2)

        # ----------------------------------------------- outside the profit
        assets_bought = float(self.db.scalar(
            select(func.sum(Asset.purchase_price)).where(
                Asset.organization_id == self.org_id, Asset.branch_id.in_(branches),
                Asset.purchase_date >= start, Asset.purchase_date <= end)) or 0)
        window = (datetime.combine(start, time.min, tzinfo=timezone.utc),
                  datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc))
        stock_added = float(self.db.scalar(
            select(func.sum(InventoryTransaction.quantity_delta * InventoryItem.purchase_price))
            .join(InventoryItem, InventoryItem.id == InventoryTransaction.item_id)
            .where(InventoryTransaction.organization_id == self.org_id,
                   InventoryTransaction.branch_id.in_(branches),
                   InventoryTransaction.txn_type == "STOCK_IN",
                   InventoryTransaction.created_at >= window[0],
                   InventoryTransaction.created_at < window[1])) or 0)
        receivable = float(self.db.scalar(
            select(func.sum(Invoice.balance)).where(
                Invoice.organization_id == self.org_id, Invoice.branch_id.in_(branches),
                Invoice.status != InvoiceStatus.CANCELLED, Invoice.balance > 0)) or 0)

        net = round(income_total - expense_total, 2)
        return {
            "from_date": start.isoformat(), "to_date": end.isoformat(),
            "income": {"lines": income_lines, "total": income_total,
                       "billed_total": round(sum(billed.values()), 2),
                       "discounts": round(discounts, 2)},
            "expenses": {"lines": expense_lines, "total": expense_total},
            "net_profit": net,
            "margin_pct": round(net / income_total * 100, 1) if income_total else 0.0,
            "not_in_profit": {
                "deposits_collected": round(deposits_in, 2),
                "deposits_billed": round(deposits_billed, 2),
                "tax_collected": round(tax_in, 2),
                "assets_bought": round(assets_bought, 2),
                "stock_added": round(stock_added, 2),
            },
            "receivable_now": round(receivable, 2),
            "trend": self._trend(branches, end),
        }

    def _trend(self, branches, end: date, months: int = 6) -> list[dict]:
        first = _add_months(_month_start(end), -(months - 1))
        last = _add_months(_month_start(end), 1) - timedelta(days=1)
        income: dict[date, float] = defaultdict(float)
        for p in self._verified(branches, first, last):
            share = _split(p)
            income[_month_start(p.payment_date)] += sum(
                v for k, v in share.items() if k not in ("DEPOSIT", "TAX"))
        spent: dict[date, float] = defaultdict(float)
        for spent_on, amount in self.db.execute(
                select(Expense.spent_on, Expense.amount).where(
                    Expense.organization_id == self.org_id, Expense.branch_id.in_(branches),
                    Expense.spent_on >= first, Expense.spent_on <= last)).all():
            spent[_month_start(spent_on)] += float(amount)
        out = []
        for i in range(months):
            m = _add_months(first, i)
            inc, exp = round(income.get(m, 0), 2), round(spent.get(m, 0), 2)
            out.append({"month": m.isoformat(), "label": m.strftime("%b %Y"),
                        "income": inc, "expenses": exp, "profit": round(inc - exp, 2)})
        return out

    @staticmethod
    def to_csv(report: dict) -> str:
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Profit and loss", report["from_date"], "to", report["to_date"]])
        w.writerow([])
        w.writerow(["Income", "Collected", "Billed"])
        for line in report["income"]["lines"]:
            w.writerow([line["label"], line["collected"], line["billed"]])
        w.writerow(["Total income", report["income"]["total"], report["income"]["billed_total"]])
        w.writerow([])
        w.writerow(["Expenses", "Amount", "Entries"])
        for line in report["expenses"]["lines"]:
            w.writerow([line["category"], line["amount"], line["count"]])
        w.writerow(["Total expenses", report["expenses"]["total"]])
        w.writerow([])
        w.writerow(["Net profit", report["net_profit"]])
        w.writerow([])
        w.writerow(["Not counted in profit", "Amount"])
        for key, value in report["not_in_profit"].items():
            w.writerow([key.replace("_", " ").capitalize(), value])
        return buf.getvalue()
