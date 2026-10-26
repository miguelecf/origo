import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.web.templates import render

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return render(request, "pages/login.html", error=None)


@router.post("/login")
def login(request: Request, password: str = Form("")):
    if settings.APP_PASSWORD and secrets.compare_digest(password.encode(), settings.APP_PASSWORD.encode()):
        request.session["auth"] = True
        return RedirectResponse("/", status_code=303)
    return render(request, "pages/login.html", error="Contraseña incorrecta")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
