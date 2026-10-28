from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Origo"
    DATABASE_URL: str = "sqlite:///./mentor.db"
    TIMEZONE: str = "America/Argentina/Buenos_Aires"
    OWNER_NAME: str = "Miguel"
    SECRET_KEY: str = "dev-secret-change-me"
    MENTOR_DEV_OPEN: bool = False
    SESSION_IDLE_SECONDS: int = 1800
    SESSION_ABSOLUTE_SECONDS: int = 86400
    BASE_URL: str = "http://localhost:8000"
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_ALLOWED_LOGIN: str = ""
    MCP_TOKEN: str = ""
    MCP_LOCAL_ONLY: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = ""

    @model_validator(mode="after")
    def validate_security(self):
        url = urlsplit(self.BASE_URL)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
            raise ValueError("BASE_URL debe ser un origen HTTP o HTTPS sin ruta")
        self.BASE_URL = self.BASE_URL.rstrip("/")
        if url.scheme == "https":
            if len(self.SECRET_KEY.encode()) < 32 or len(set(self.SECRET_KEY)) < 12 or any(word in self.SECRET_KEY.lower() for word in ("change-me", "example", "changeme")):
                raise ValueError("SECRET_KEY debe ser aleatoria y tener al menos 32 bytes en HTTPS")
            if self.MENTOR_DEV_OPEN:
                raise ValueError("MENTOR_DEV_OPEN no está permitido en HTTPS")
        if self.MENTOR_DEV_OPEN and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("MENTOR_DEV_OPEN solo está permitido en localhost")
        if self.MCP_TOKEN and (len(self.MCP_TOKEN.encode()) < 32 or len(set(self.MCP_TOKEN)) < 12):
            raise ValueError("MCP_TOKEN debe ser aleatorio y tener al menos 32 bytes")
        if min(self.SESSION_IDLE_SECONDS, self.SESSION_ABSOLUTE_SECONDS) <= 0:
            raise ValueError("Los plazos de sesión deben ser positivos")
        return self

    @property
    def oauth_enabled(self) -> bool:
        return bool(self.GITHUB_CLIENT_ID and self.GITHUB_CLIENT_SECRET and self.GITHUB_ALLOWED_LOGIN)

    @property
    def remote_mcp_enabled(self) -> bool:
        return self.oauth_enabled or bool(self.MCP_TOKEN)


settings = Settings()
