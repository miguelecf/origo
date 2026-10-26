from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Mentor"
    DATABASE_URL: str = "sqlite:///./mentor.db"
    TIMEZONE: str = "America/Argentina/Buenos_Aires"
    # Cómo te ven los invitados: "Miguel confirmó tu pago".
    OWNER_NAME: str = "Miguel"

    # Login web. Vacío = sin login (solo para uso local).
    APP_PASSWORD: str = ""
    SECRET_KEY: str = "dev-secret-change-me"

    # MCP remoto (Claude.ai, ChatGPT, apps). Sin estas tres, solo hay MCP local por stdio.
    BASE_URL: str = "http://localhost:8000"
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_ALLOWED_LOGIN: str = ""

    @property
    def remote_mcp_enabled(self) -> bool:
        return bool(self.GITHUB_CLIENT_ID and self.GITHUB_CLIENT_SECRET and self.GITHUB_ALLOWED_LOGIN)


settings = Settings()
