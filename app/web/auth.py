from fastapi import HTTPException, Request

from app.core.config import settings


def require_login(request: Request) -> None:
    if settings.APP_PASSWORD and not request.session.get("auth"):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
