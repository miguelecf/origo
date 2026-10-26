import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services import guests
from app.web.auth import Viewer
from app.web.templates import render

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return render(request, "pages/login.html", error=None)


@router.post("/login")
def login(request: Request, password: str = Form("")):
    if settings.APP_PASSWORD and secrets.compare_digest(password.encode(), settings.APP_PASSWORD.encode()):
        request.session.pop("guest_id", None)
        request.session["auth"] = True
        return RedirectResponse("/", status_code=303)
    return render(request, "pages/login.html", error="Contraseña incorrecta")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/g/{token}")
def magic_link(request: Request, token: str, db: Session = Depends(get_db)):
    """Link mágico de un invitado: lo deja entrar sin contraseña a lo que tenga permitido."""
    if request.session.get("auth"):
        # Soy yo probando el link: no me deslogueo.
        return render(request, "pages/login.html", error=None, owner_with_link=True)
    guest = guests.by_token(db, token)
    if guest is None:
        request.session.pop("guest_id", None)
        return render(request, "pages/login.html", error="Ese link ya no funciona. Pedile uno nuevo a " + settings.OWNER_NAME + ".")
    request.session["guest_id"] = guest.id
    return RedirectResponse(Viewer(guest).home, status_code=303)
