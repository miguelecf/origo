import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
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

STATIC_DIR = Path(__file__).parent / "static"


def _service_worker() -> str:
    assets = []
    version_parts = []
    for path in sorted(STATIC_DIR.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(STATIC_DIR).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        version_parts.append(f"{relative}:{digest}")
        assets.append(f"/static/{relative}?v={digest[:16]}")
    version = hashlib.sha256("\n".join(version_parts).encode()).hexdigest()[:16]
    precache = json.dumps(assets, separators=(",", ":"))
    return f'''"use strict";
const CACHE = "mentor-static-{version}";
const ASSETS = {precache};
const OFFLINE_HTML = `<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#f2f2f7"><title>Sin conexión | Mentor</title><style>*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:#f2f2f7;color:#1c1c1e;font:17px/1.5 -apple-system,BlinkMacSystemFont,system-ui,sans-serif}}main{{max-width:420px;padding:28px;border-radius:24px;background:#fff;box-shadow:0 12px 40px #1c1c1e18}}h1{{font-size:34px;line-height:1.2;margin:0 0 12px}}p{{margin:0;color:#636366}}a{{display:inline-flex;min-height:44px;align-items:center;margin-top:20px;color:#007aff;font-weight:600;text-decoration:none}}</style><main><h1>Estás sin conexión</h1><p>Mentor necesita señal para mostrar tus datos privados. Lo que ya anotaste en la compra sigue guardado en este teléfono.</p><a href="/">Volver a intentar</a></main></html>`;
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting())));
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("mentor-") && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener("fetch", event => {{
  const request = event.request;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname === "/logout" && request.method !== "GET") {{
    event.respondWith(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("mentor-")).map(key => caches.delete(key)))).then(() => fetch(request)));
    return;
  }}
  if (request.method !== "GET" || url.pathname === "/login" || url.pathname === "/logout" || url.pathname.startsWith("/g/") || url.pathname === "/mcp" || url.pathname.startsWith("/mcp/") || url.pathname.startsWith("/.well-known/")) return;
  if (url.pathname.startsWith("/static/")) {{
    event.respondWith(caches.open(CACHE).then(async cache => {{
      const cached = await cache.match(request, {{ignoreSearch:true}});
      if (cached) return cached;
      const response = await fetch(request);
      if (response.ok && response.type === "basic") await cache.put(request, response.clone());
      return response;
    }}));
    return;
  }}
  if (request.mode === "navigate") {{
    event.respondWith(fetch(request).catch(() => url.pathname === "/offline"
      ? new Response(OFFLINE_HTML, {{headers: {{"Content-Type":"text/html; charset=utf-8", "Cache-Control":"no-store"}}}})
      : Response.redirect(new URL("/offline", self.location.origin), 302)));
  }}
}});
'''


def create_app() -> FastAPI:
    settings.validate_security()
    configure_logging()
    init_db()
    mcp_app = remote_http_app() if settings.remote_mcp_enabled else None

    app = FastAPI(title=settings.APP_NAME, lifespan=mcp_app.lifespan if mcp_app else None,
                  docs_url=None, redoc_url=None, openapi_url=None, debug=False)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlsplit(settings.BASE_URL).hostname, "localhost", "127.0.0.1", "::1"], www_redirect=False)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(SecurityMiddleware)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.include_router(auth.router)
    # Deudas y Súper chequean permisos por ruta: también entran invitados con link mágico.
    app.include_router(debts.router)
    app.include_router(lists.router)
    for module in (home, finance, body, checkin, guests):
        app.include_router(module.router, dependencies=[Depends(require_owner)])

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return Response(_service_worker(), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/offline", include_in_schema=False)
    def offline():
        return HTMLResponse(
            '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#f2f2f7"><title>Sin conexión | Mentor</title><link rel="stylesheet" href="/static/app.css?v=apple-3"><main class="offline"><h1>Estás sin conexión</h1><p>Mentor necesita señal para mostrar tus datos privados. Lo que ya anotaste en la compra sigue guardado en este teléfono.</p><a class="btn" href="/">Volver a intentar</a></main></html>',
            headers={"Cache-Control": "no-store"},
        )

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
