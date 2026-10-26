from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.database import get_db
from app.services import debts
from app.web.forms import parse_amount, parse_date, parse_int
from app.web.templates import render

router = APIRouter(prefix="/deudas")


@router.get("")
def debts_page(request: Request, todas: bool = False, db: Session = Depends(get_db)):
    all_debts = debts.list_debts(db, include_settled=todas)
    return render(
        request, "pages/debts.html",
        owed_to_me=[d for d in all_debts if d.direction == "owed_to_me"],
        i_owe=[d for d in all_debts if d.direction == "i_owe"],
        balances=debts.balances(db), alerts=debts.card_alerts(db, today()),
        remaining=debts.remaining, show_all=todas, today=today(),
        error=request.query_params.get("error"),
    )


@router.post("")
def add(
    kind: str = Form(...), person: str = Form(...), total: str = Form(...),
    installments: str = Form("1"), first_due: str = Form(""), card: str = Form(""),
    description: str = Form(""), db: Session = Depends(get_db),
):
    amount, parts, due = parse_amount(total), parse_int(installments) or 1, parse_date(first_due)
    try:
        if amount is None:
            raise ValueError("Monto inválido")
        if kind == "card":
            if not card.strip() or due is None:
                raise ValueError("Para una tarjeta prestada poné la tarjeta y el primer vencimiento")
            debts.create_card_loan(
                db, person=person, card=card, total=amount, installments=parts,
                first_due=due, description=description,
            )
        else:
            debts.create_debt(
                db, person=person, direction=kind, total=amount, installments=parts,
                first_due=due, description=description,
            )
    except ValueError as exc:
        return RedirectResponse(f"/deudas?error={exc}", status_code=303)
    return RedirectResponse("/deudas", status_code=303)


@router.post("/cuotas/{installment_id}")
def toggle_installment(installment_id: int, paid: bool = Form(...), db: Session = Depends(get_db)):
    debts.set_installment_paid(db, installment_id, paid)
    return RedirectResponse("/deudas", status_code=303)


@router.post("/{debt_id}/borrar")
def delete(debt_id: int, db: Session = Depends(get_db)):
    debts.delete_debt(db, debt_id)
    return RedirectResponse("/deudas", status_code=303)
