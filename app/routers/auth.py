from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import event
from app.services import guests, security
from app.web.auth import Viewer, get_viewer
from app.web.security import COOKIE_NAME, set_session_cookie
from app.web.templates import render

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return render(request, "pages/login.html", error=None)


@router.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form(""),
          code: str = Form(""), db: Session = Depends(get_db)):
    ip = request.state.client_ip
    user, blocked = security.authenticate(db, username, password, code, ip)
    if user:
        token = security.new_session(db, previous=request.cookies.get(COOKIE_NAME), user=user)
        response = RedirectResponse("/", status_code=303)
        set_session_cookie(response, token)
        event("login_ok", ip=ip, user_id=user.id)
        return response
    event("login_blocked" if blocked else "login_failed", ip=ip)
    response = render(request, "pages/login.html", error="No pudimos iniciar sesión. Revisá los datos o esperá unos minutos.")
    response.status_code = 429 if blocked else 401
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    security.revoke_session(db, request.cookies.get(COOKIE_NAME))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME, secure=settings.BASE_URL.startswith("https://"), httponly=True, samesite="lax")
    event("logout", ip=request.state.client_ip)
    return response


@router.get("/g/{token}")
def magic_link(request: Request, token: str, db: Session = Depends(get_db)):
    if not security.consume_attempt(db, security.attempt_keys(request.state.client_ip, guest=True), limit=20):
        response = render(request, "pages/login.html", error="Esperá unos minutos antes de volver a intentar.")
        response.status_code = 429
        return response
    viewer = get_viewer(request, db)
    if viewer and viewer.is_owner:
        return render(request, "pages/login.html", error=None, owner_with_link=True)
    guest = guests.by_token(db, token)
    if guest is None:
        security.revoke_session(db, request.cookies.get(COOKIE_NAME))
        response = render(request, "pages/login.html", error="Ese link ya no funciona. Pedile uno nuevo a " + settings.OWNER_NAME + ".")
        response.delete_cookie(COOKIE_NAME)
        return response
    session_token = security.new_session(db, previous=request.cookies.get(COOKIE_NAME), guest=guest)
    response = RedirectResponse(Viewer(guest).home, status_code=303)
    set_session_cookie(response, session_token)
    event("guest_login", ip=request.state.client_ip, guest_id=guest.id)
    return response
