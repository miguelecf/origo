import ipaddress
import time
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse

from app.core.config import settings
from app.core.logging import event, redact_path

COOKIE_NAME = "mentor_session"
OAUTH_PATHS = {"/authorize", "/token", "/register", "/revoke", "/auth/callback", "/consent"}


def bearer_path(path: str) -> bool:
    return path in OAUTH_PATHS or path == "/mcp" or path.startswith("/mcp/") or path.startswith("/.well-known/")


def client_ip(scope) -> str:
    peer = (scope.get("client") or ("unknown", 0))[0]
    if peer == "127.0.0.1":
        headers = Headers(scope=scope)
        candidate = headers.get("cf-connecting-ip") or headers.get("x-forwarded-for", "").split(",")[-1].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    # Con --proxy-headers uvicorn ya validó el peer antes de reescribir scope.client.
    return peer


def origin(value: str):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        start = time.monotonic()
        headers = Headers(scope=scope)
        ip = client_ip(scope)
        scope.setdefault("state", {})["client_ip"] = ip
        status = 500
        started = False

        async def secure_send(message):
            nonlocal status, started
            if message["type"] == "http.response.start":
                started = True
                status = message["status"]
                out = MutableHeaders(scope=message)
                # Mantener la CSP más estricta del proveedor OAuth en sus propias páginas.
                if "content-security-policy" not in out:
                    out["Content-Security-Policy"] = (
                        "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline' 'unsafe-eval'; "
                        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                        "font-src 'self'; "
                        "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
                    )
                out["X-Frame-Options"] = "DENY"
                out["X-Content-Type-Options"] = "nosniff"
                out["Referrer-Policy"] = "same-origin"
                out["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
                if settings.BASE_URL.startswith("https://"):
                    out["Strict-Transport-Security"] = "max-age=31536000"
                if "text/html" in out.get("content-type", "") or scope["path"].startswith(("/g/", "/login", "/logout")):
                    out["Cache-Control"] = "no-store"
                if scope["path"].startswith("/g/"):
                    out["Referrer-Policy"] = "no-referrer"
            await send(message)

        try:
            if scope["method"] not in {"GET", "HEAD", "OPTIONS"} and not bearer_path(scope["path"]):
                supplied = headers.get("origin") if "origin" in headers else headers.get("referer", "")
                if headers.get("sec-fetch-site", "").lower() == "cross-site" or origin(supplied) != origin(settings.BASE_URL):
                    event("csrf_rejected", ip=ip, method=scope["method"], path=redact_path(scope["path"]))
                    return await PlainTextResponse("Origen no permitido", status_code=403)(scope, receive, secure_send)
            await self.app(scope, receive, secure_send)
        except Exception:
            event("request_error", ip=ip, path=redact_path(scope["path"]))
            if not started:
                await PlainTextResponse("Error interno del servidor", status_code=500)(scope, receive, secure_send)
        finally:
            event("access", ip=ip, method=scope["method"], path=redact_path(scope["path"]), status=status,
                  duration_ms=round((time.monotonic() - start) * 1000, 2))


def set_session_cookie(response, token: str):
    response.set_cookie(COOKIE_NAME, token, max_age=settings.SESSION_ABSOLUTE_SECONDS,
                        httponly=True, secure=settings.BASE_URL.startswith("https://"), samesite="lax", path="/")
