import datetime as dt

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.database import Base


class AgentAction(Base):
    """Registro de lo que intentó escribir el agente por MCP: qué tool, con qué datos y si se hizo."""

    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(default=now, index=True)
    tool: Mapped[str] = mapped_column(String(80))
    args: Mapped[str] = mapped_column(Text, default="")
    ok: Mapped[bool] = mapped_column(default=True)
    error: Mapped[str] = mapped_column(String(300), default="")
