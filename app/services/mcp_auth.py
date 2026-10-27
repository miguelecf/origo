"""Autenticación HTTP separada de las tools y del transporte stdio local."""
import secrets

from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.auth.providers.github import GitHubProvider

from app.core.config import settings


def static_access(token: str) -> AccessToken | None:
    if settings.MCP_TOKEN and secrets.compare_digest(token.encode(), settings.MCP_TOKEN.encode()):
        return AccessToken(token=token, client_id="mentor-static", scopes=[], claims={"mentor_static": True})
    return None


class StaticVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        return static_access(token)


class OwnerGitHubProvider(GitHubProvider):
    async def verify_token(self, token: str) -> AccessToken | None:
        if access := static_access(token):
            return access
        access = await super().verify_token(token)
        if access and str(access.claims.get("login", "")).casefold() == settings.GITHUB_ALLOWED_LOGIN.casefold():
            return access
        return None


def remote_auth():
    if settings.oauth_enabled:
        return OwnerGitHubProvider(
            client_id=settings.GITHUB_CLIENT_ID, client_secret=settings.GITHUB_CLIENT_SECRET,
            base_url=settings.BASE_URL, jwt_signing_key=settings.SECRET_KEY,
            enable_cimd=False,
        )
    if settings.MCP_TOKEN:
        return StaticVerifier(base_url=settings.BASE_URL)
    raise ValueError("MCP remoto requiere OAuth completo o MCP_TOKEN")
