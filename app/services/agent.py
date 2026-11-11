"""Reglas para el agente conectado por MCP: qué tools ve, cuánto puede escribir y qué queda registrado.

Las aplica Origo, del lado del servidor, aunque el cliente del agente esté mal configurado.
La configuración vive en el .env (MCP_ACCESS, MCP_DENY, MCP_MAX_*)."""
import datetime as dt
import fnmatch
import json
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.core.config import settings
from app.models import AgentAction

READ_PREFIXES = ("get_", "list_")
READ_TOOLS = {"weekly_review"}
DATE_ARGS = {"date"}
AMOUNT_ARGS = {"amount", "total", "amount_ars"}
MAX_ARGS_LOG = 1000


def is_read(tool: str) -> bool:
    return tool.startswith(READ_PREFIXES) or tool in READ_TOOLS


def denied_patterns() -> list[str]:
    return [p.strip() for p in settings.MCP_DENY.split(",") if p.strip()]


def allowed(tool: str) -> bool:
    """Si el agente puede ver y usar esta tool, según MCP_ACCESS y MCP_DENY."""
    if settings.MCP_ACCESS == "read" and not is_read(tool):
        return False
    return not any(fnmatch.fnmatchcase(tool, pattern) for pattern in denied_patterns())


def check_args(args: dict) -> None:
    """Fechas dentro de la ventana permitida y montos bajo el tope. Lanza ValueError."""
    for name, value in (args or {}).items():
        if name in DATE_ARGS and value:
            try:
                day = dt.date.fromisoformat(str(value))
            except ValueError:
                raise ValueError(f"{name}: fecha inválida, usá YYYY-MM-DD") from None
            if day > today():
                raise ValueError(f"{name}: el agente no puede cargar fechas a futuro")
            if (today() - day).days > settings.MCP_MAX_BACKDATE_DAYS:
                raise ValueError(f"{name}: el agente puede fechar hasta {settings.MCP_MAX_BACKDATE_DAYS} días para atrás")
        if name in AMOUNT_ARGS and value is not None and settings.MCP_MAX_AMOUNT:
            try:
                amount = Decimal(str(value))
            except InvalidOperation:
                continue  # lo rechaza la validación de la tool
            if amount > Decimal(str(settings.MCP_MAX_AMOUNT)):
                raise ValueError(f"{name}: supera el tope de {settings.MCP_MAX_AMOUNT:g} para el agente. Cargalo desde la web")


MAX_WEIGHT_JUMP = Decimal("0.08")


def check_plausible(db: Session, tool: str, args: dict) -> None:
    """Datos que no pueden ser ciertos de un día para otro: un peso que se aleja más de un 8 %
    del último registro. Si es correcto, se carga desde la web."""
    if tool == "log_weight" and args.get("kg") is not None:
        from app.services import body

        series = body.weight_series(db)
        if series:
            last = series[-1].kg
            try:
                kg = Decimal(str(args["kg"]))
            except InvalidOperation:
                return
            if last and abs(kg - last) / last > MAX_WEIGHT_JUMP:
                raise ValueError(
                    f"{kg:g} kg se aleja mucho del último registro ({last:g} kg). "
                    "Confirmá el número con el usuario; si es correcto, que lo cargue desde la web"
                )


def writes_last_hour(db: Session) -> int:
    since = now() - dt.timedelta(hours=1)
    return db.scalar(select(func.count(AgentAction.id)).where(AgentAction.at >= since, AgentAction.ok.is_(True))) or 0


def check_rate(db: Session) -> None:
    limit = settings.MCP_MAX_WRITES_PER_HOUR
    if limit and writes_last_hour(db) >= limit:
        raise ValueError(f"El agente llegó al tope de {limit} escrituras por hora. Probá más tarde")


def record(db: Session, tool: str, args: dict, ok: bool, error: str = "") -> AgentAction:
    text = json.dumps(args or {}, ensure_ascii=False, default=str)
    action = AgentAction(tool=tool[:80], args=text[:MAX_ARGS_LOG], ok=ok, error=error[:300])
    db.add(action)
    db.commit()
    return action


def recent(db: Session, limit: int = 50) -> list[AgentAction]:
    return list(db.scalars(select(AgentAction).order_by(AgentAction.id.desc()).limit(limit)))


def policy() -> dict:
    return {
        "access": settings.MCP_ACCESS,
        "deny": denied_patterns(),
        "max_writes_per_hour": settings.MCP_MAX_WRITES_PER_HOUR,
        "max_backdate_days": settings.MCP_MAX_BACKDATE_DAYS,
        "max_amount": settings.MCP_MAX_AMOUNT or None,
    }
