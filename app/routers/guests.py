import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import Debt, Guest
from app.services import guests, lists
from app.web.templates import render

router = APIRouter(prefix="/invitados")


def _link(token: str) -> str:
    return f"{settings.BASE_URL.rstrip('/')}/g/{token}"


def _page(request: Request, db: Session, **extra):
    return render(
        request, "pages/guests.html", guests=guests.list_guests(db),
        people=sorted(set(db.scalars(select(Debt.person)))), **extra,
    )


@router.get("")
def guests_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db)


@router.post("")
def create(
    request: Request, name: str = Form(""), person: str = Form(""),
    can_lists: bool = Form(False), can_debts: bool = Form(False),
    expires_at: dt.datetime | None = Form(None), db: Session = Depends(get_db),
):
    try:
        guest, token = guests.create_guest(db, name=name, person=person, can_lists=can_lists, can_debts=can_debts, expires_at=expires_at)
    except ValueError as exc:
        return _page(request, db, error=str(exc))
    return _new_link(request, db, guest.name, token)


@router.post("/{guest_id}/link")
def rotate(request: Request, guest_id: int, db: Session = Depends(get_db)):
    token = guests.rotate_token(db, guest_id)
    return _new_link(request, db, db.get(Guest, guest_id).name, token)


@router.post("/{guest_id}/quitar")
def revoke(guest_id: int, db: Session = Depends(get_db)):
    guests.revoke(db, guest_id)
    return RedirectResponse("/invitados", status_code=303)


def _new_link(request: Request, db: Session, name: str, token: str):
    link = _link(token)
    text = f"Te paso el link a mi Origo: {link}"
    return _page(request, db, new_link={"name": name, "url": link, "whatsapp": lists.whatsapp_url(text)})
