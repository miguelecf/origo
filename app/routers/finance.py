import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.clock import add_months, month_bounds, today
from app.core.database import get_db
from app.services import finance
from app.web.forms import parse_amount, parse_date
from app.web.templates import render

router = APIRouter(prefix="/plata")


def _month(value: str | None) -> dt.date:
    try:
        return dt.date.fromisoformat(f"{value}-01")
    except (TypeError, ValueError):
        return today().replace(day=1)


@router.get("")
def finance_page(request: Request, mes: str | None = None, db: Session = Depends(get_db)):
    start, end = month_bounds(_month(mes))
    return render(
        request, "pages/finance.html",
        month=start, prev_month=add_months(start, -1), next_month=end,
        summary=finance.summary(db, start, end),
        transactions=finance.list_transactions(db, start, end),
        income_categories=finance.INCOME_CATEGORIES, expense_categories=finance.EXPENSE_CATEGORIES,
        today=today(), error=request.query_params.get("error"),
    )


@router.post("")
def add(
    kind: str = Form(...), amount: str = Form(...), category: str = Form("Otros"),
    date: str = Form(""), note: str = Form(""), db: Session = Depends(get_db),
):
    value = parse_amount(amount)
    try:
        if value is None:
            raise ValueError("Monto inválido")
        tx = finance.add_transaction(
            db, kind=kind, amount=value, category=category, date=parse_date(date), note=note,
        )
    except ValueError as exc:
        return RedirectResponse(f"/plata?error={exc}", status_code=303)
    return RedirectResponse(f"/plata?mes={tx.date:%Y-%m}", status_code=303)


@router.post("/{transaction_id}/borrar")
def delete(transaction_id: int, mes: str = Form(""), db: Session = Depends(get_db)):
    finance.delete_transaction(db, transaction_id)
    return RedirectResponse(f"/plata?mes={mes}" if mes else "/plata", status_code=303)
