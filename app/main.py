from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.mcp_server import mcp
from app.routers import auth, body, checkin, debts, finance, guests, home, lists
from app.web.auth import require_owner


def create_app() -> FastAPI:
    init_db()
    # El MCP remoto solo se monta con OAuth configurado; sin eso, se usa local por stdio.
    mcp_app = mcp.http_app(path="/mcp") if settings.remote_mcp_enabled else None

    app = FastAPI(title=settings.APP_NAME, lifespan=mcp_app.lifespan if mcp_app else None)
    app.add_middleware(
        SessionMiddleware, secret_key=settings.SECRET_KEY, max_age=60 * 60 * 24 * 90,
        https_only=settings.BASE_URL.startswith("https"),
    )
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    app.include_router(auth.router)
    # Deudas y Súper chequean permisos por ruta: también entran invitados con link mágico.
    app.include_router(debts.router)
    app.include_router(lists.router)
    for module in (home, finance, body, checkin, guests):
        app.include_router(module.router, dependencies=[Depends(require_owner)])

    if mcp_app:
        app.mount("/", mcp_app)  # va al final: /mcp y las rutas de OAuth (/authorize, /token, ...)
    return app


app = create_app()
