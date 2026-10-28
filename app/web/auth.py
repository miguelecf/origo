from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import Guest, User
from app.services import security
from app.web.security import COOKIE_NAME


@dataclass
class Viewer:
    """Quién está mirando: yo (guest None) o un invitado con link mágico."""

    guest: Guest | None = None

    @property
    def is_owner(self) -> bool:
        return self.guest is None

    @property
    def guest_id(self) -> int | None:
        return self.guest.id if self.guest else None

    def can(self, scope: str) -> bool:
        return self.is_owner or bool(getattr(self.guest, f"can_{scope}"))

    @property
    def home(self) -> str:
        if self.is_owner:
            return "/"
        return "/super" if self.can("lists") else "/deudas"


def _redirect(location: str) -> HTTPException:
    return HTTPException(status_code=303, headers={"Location": location})


def get_viewer(request: Request, db: Session) -> Viewer | None:
    identity = security.session_identity(db, request.cookies.get(COOKIE_NAME))
    if isinstance(identity, User):
        return Viewer()
    if isinstance(identity, Guest):
        return Viewer(identity)
    if settings.ORIGO_DEV_OPEN and not request.cookies.get(COOKIE_NAME):
        return Viewer()  # Solo desarrollo local explícito; validado al arrancar.
    return None


def require_owner(request: Request, db: Session = Depends(get_db)) -> Viewer:
    viewer = get_viewer(request, db)
    if viewer is None:
        raise _redirect("/login")
    if not viewer.is_owner:
        raise _redirect(viewer.home)
    request.state.viewer = viewer
    return viewer


def require_scope(scope: str):
    """Yo, o un invitado con permiso para `scope` ('lists' o 'debts')."""

    def dependency(request: Request, db: Session = Depends(get_db)) -> Viewer:
        viewer = get_viewer(request, db)
        if viewer is None:
            raise _redirect("/login")
        if not viewer.can(scope):
            raise _redirect(viewer.home)
        request.state.viewer = viewer
        return viewer

    return dependency
