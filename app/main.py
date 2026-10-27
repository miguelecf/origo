from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.core.logging import configure_logging
from app.mcp_server import remote_http_app
from app.routers import auth, body, checkin, debts, finance, guests, home, lists
from app.web.auth import require_owner
from app.web.security import SecurityMiddleware


def create_app() -> FastAPI:
    settings.validate_security()
    configure_logging()
    init_db()
    mcp_app = remote_http_app() if settings.remote_mcp_enabled else None

    app = FastAPI(title=settings.APP_NAME, lifespan=mcp_app.lifespan if mcp_app else None,
                  docs_url=None, redoc_url=None, openapi_url=None, debug=False)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlsplit(settings.BASE_URL).hostname, "localhost", "127.0.0.1", "::1"], www_redirect=False)
    app.add_middleware(SecurityMiddleware)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    app.include_router(auth.router)
    # Deudas y Súper chequean permisos por ruta: también entran invitados con link mágico.
    app.include_router(debts.router)
    app.include_router(lists.router)
    for module in (home, finance, body, checkin, guests):
        app.include_router(module.router, dependencies=[Depends(require_owner)])

    if mcp_app:
        app.mount("/", mcp_app)  # Al final: MCP y OAuth, nunca acceso anónimo.
    else:
        @app.api_route("/mcp", methods=["GET", "POST", "DELETE"])
        @app.api_route("/mcp/{path:path}", methods=["GET", "POST", "DELETE"])
        def mcp_disabled(path: str = ""):
            return JSONResponse({"detail": "MCP remoto no habilitado"}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
    return app


app = create_app()
