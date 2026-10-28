import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.clock import add_months, month_bounds, today
from app.core.database import get_db
from app.services import brands, finance, subscriptions
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


# --- Suscripciones ---

SUBS = "/plata/suscripciones"


@router.get("/suscripciones")
def subscriptions_page(request: Request, db: Session = Depends(get_db)):
    subs = subscriptions.list_subscriptions(db)
    return render(
        request, "pages/subscriptions.html",
        active_subs=[s for s in subs if s.active], paused_subs=[s for s in subs if not s.active],
        totals=subscriptions.monthly_totals(subs), categories=subscriptions.CATEGORIES,
        periods=subscriptions.PERIOD_LABELS, payment_options=subscriptions.PAYMENT_OPTIONS,
        suggestions=subscriptions.SUGGESTIONS, brand_label=brands.label, today=today(),
        error=request.query_params.get("error"),
    )


@router.post("/suscripciones")
def add_subscription(
    name: str = Form(...), amount: str = Form(...), currency: str = Form("ARS"), period: str = Form("monthly"),
    category: str = Form("Otros"), next_charge: str = Form(""), paid_with: str = Form(""), note: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        value = parse_amount(amount)
        if value is None:
            raise ValueError("Monto inválido")
        subscriptions.create_subscription(
            db, name=name, amount=value, currency=currency, period=period, category=category,
            next_charge=parse_date(next_charge), paid_with=paid_with, note=note,
        )
    except ValueError as exc:
        return RedirectResponse(f"{SUBS}?error={exc}", status_code=303)
    return RedirectResponse(SUBS, status_code=303)


@router.post("/suscripciones/{subscription_id}/cobrada")
def charged(subscription_id: int, amount_ars: str = Form(""), db: Session = Depends(get_db)):
    try:
        subscriptions.mark_charged(db, subscription_id, amount_ars=parse_amount(amount_ars))
    except ValueError as exc:
        return RedirectResponse(f"{SUBS}?error={exc}", status_code=303)
    return RedirectResponse(SUBS, status_code=303)


@router.post("/suscripciones/{subscription_id}/activa")
def toggle_active(subscription_id: int, active: bool = Form(...), db: Session = Depends(get_db)):
    try:
        subscriptions.set_active(db, subscription_id, active)
    except ValueError as exc:
        return RedirectResponse(f"{SUBS}?error={exc}", status_code=303)
    return RedirectResponse(SUBS, status_code=303)


@router.post("/suscripciones/{subscription_id}/borrar")
def delete_subscription(subscription_id: int, db: Session = Depends(get_db)):
    subscriptions.delete_subscription(db, subscription_id)
    return RedirectResponse(SUBS, status_code=303)
