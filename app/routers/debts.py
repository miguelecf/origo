from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.database import get_db
from app.services import brands, debts, guests
from app.web.auth import Viewer, require_owner, require_scope
from app.web.forms import parse_amount, parse_date, parse_int
from app.web.templates import render

router = APIRouter(prefix="/deudas")
owner_only = [Depends(require_owner)]


@router.get("")
def debts_page(
    request: Request, todas: bool = False,
    viewer: Viewer = Depends(require_scope("debts")), db: Session = Depends(get_db),
):
    if not viewer.is_owner:
        mine = guests.guest_debts(db, viewer.guest)
        return render(
            request, "pages/guest_debts.html",
            owes_me=[d for d in mine if d.direction == "owed_to_me"],
            i_owe=[d for d in mine if d.direction == "i_owe"],
            claimed=guests.claimed_installment_ids(db), claims=guests.guest_claims(db, viewer.guest),
            remaining=debts.remaining, claim_total=guests.claim_total, today=today(),
            sent=request.query_params.get("ok"), error=request.query_params.get("error"),
        )
    all_debts = debts.list_debts(db, include_settled=todas)
    return render(
        request, "pages/debts.html",
        groups=debts.debt_groups(db, settled=todas), next_due=debts.next_due,
        cards=brands.CARDS, entities=brands.ENTITIES,
        balances=debts.balances(db), alerts=debts.card_alerts(db, today()),
        claims=guests.pending_claims(db), claimed=guests.claimed_installment_ids(db),
        claim_total=guests.claim_total, remaining=debts.remaining, show_all=todas, today=today(),
        people=sorted({d.person for d in all_debts}), error=request.query_params.get("error"),
    )


@router.post("/avisar")
def claim(
    installment_ids: list[int] = Form(default=[]), message: str = Form(""),
    viewer: Viewer = Depends(require_scope("debts")), db: Session = Depends(get_db),
):
    if viewer.is_owner:
        return RedirectResponse("/deudas", status_code=303)
    try:
        guests.create_claim(db, viewer.guest, installment_ids, message)
    except ValueError as exc:
        return RedirectResponse(f"/deudas?error={exc}", status_code=303)
    return RedirectResponse("/deudas?ok=1", status_code=303)


@router.post("/avisos/{claim_id}", dependencies=owner_only)
def resolve(claim_id: int, accept: bool = Form(...), reply: str = Form(""), back: str = Form("/deudas"), db: Session = Depends(get_db)):
    try:
        guests.resolve_claim(db, claim_id, accept, reply)
    except ValueError:
        pass
    return RedirectResponse(back if back in ("/", "/deudas") else "/deudas", status_code=303)


@router.post("", dependencies=owner_only)
def add(
    kind: str = Form(...), person: str = Form(""), total: str = Form(...),
    installments: str = Form("1"), first_due: str = Form(""), card: str = Form(""),
    direction: str | None = Form(None), brand: str | None = Form(None),
    description: str = Form(""), db: Session = Depends(get_db),
):
    amount, parts, due = parse_amount(total), parse_int(installments), parse_date(first_due)
    try:
        if amount is None:
            raise ValueError("El monto no es un número")
        debts.create_from_form(
            db, kind=kind, direction=direction, person=person, card=card, brand=brand,
            total=amount, installments=parts if parts is not None else 1,
            first_due=due, description=description,
        )
    except ValueError as exc:
        return RedirectResponse(f"/deudas?error={exc}", status_code=303)
    return RedirectResponse("/deudas", status_code=303)


@router.post("/cuotas/{installment_id}", dependencies=owner_only)
def toggle_installment(installment_id: int, paid: bool = Form(...), db: Session = Depends(get_db)):
    debts.set_installment_paid(db, installment_id, paid)
    return RedirectResponse("/deudas", status_code=303)


@router.post("/{debt_id}/borrar", dependencies=owner_only)
def delete(debt_id: int, db: Session = Depends(get_db)):
    debts.delete_debt(db, debt_id)
    return RedirectResponse("/deudas", status_code=303)
