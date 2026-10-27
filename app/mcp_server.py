"""MCP de Mentor: el agente lee lo mismo que ves en la app (misma capa de servicios).

Local (Claude Code, Claude Desktop): `uv run python -m app.mcp_server` por stdio, sin auth.
Remoto (Claude.ai, ChatGPT): se monta en /mcp dentro de la app web, con OAuth de GitHub
y restringido a GITHUB_ALLOWED_LOGIN.
"""

import datetime as dt
from contextlib import contextmanager
from decimal import Decimal

from fastmcp import FastMCP
from fastmcp.server.middleware import AuthMiddleware

from app.core.clock import month_bounds, today
from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.services import body, checkins, debts, finance, guests, lists, overview

INSTRUCTIONS = """\
Registro personal de la vida de una persona: plata, deudas, peso, comidas, sueño, ánimo,
movimiento y compras. Montos en la moneda local, fechas en formato ISO (YYYY-MM-DD).
Los rangos son [from_date, to_date): incluye el inicio y excluye el final.
Para analizar, empezá por get_overview y después bajá al detalle que necesites.
"""


def _auth():
    if not settings.remote_mcp_enabled:
        return None, []
    from fastmcp.server.auth.providers.github import GitHubProvider

    allowed = settings.GITHUB_ALLOWED_LOGIN.lower()
    provider = GitHubProvider(
        client_id=settings.GITHUB_CLIENT_ID,
        client_secret=settings.GITHUB_CLIENT_SECRET,
        base_url=settings.BASE_URL,
        jwt_signing_key=settings.SECRET_KEY,
    )
    # Cualquiera con GitHub puede completar el OAuth; solo tu usuario ve y usa las tools.
    only_me = AuthMiddleware(
        auth=lambda ctx: ctx.token is not None and str(ctx.token.claims.get("login", "")).lower() == allowed
    )
    return provider, [only_me]


_provider, _middleware = _auth()
mcp = FastMCP("Mentor", instructions=INSTRUCTIONS, auth=_provider, middleware=_middleware)


@contextmanager
def _db():
    with SessionLocal() as db:
        yield db


def _range(from_date: str | None, to_date: str | None, default_days: int | None = None) -> tuple[dt.date, dt.date]:
    """Sin fechas: el mes en curso (o los últimos `default_days` días)."""
    if from_date and to_date:
        return dt.date.fromisoformat(from_date), dt.date.fromisoformat(to_date)
    if default_days:
        end = today() + dt.timedelta(days=1)
        return end - dt.timedelta(days=default_days), end
    return month_bounds(today())


def _num(value) -> float | None:
    return float(value) if value is not None else None


def _installment(inst) -> dict:
    return {
        "id": inst.id, "number": inst.number, "of": len(inst.debt.installments),
        "amount": _num(inst.amount), "due_date": inst.due_date and inst.due_date.isoformat(),
        "paid_on": inst.paid_on and inst.paid_on.isoformat(),
    }


def _debt(debt) -> dict:
    return {
        "id": debt.id, "person": debt.person, "direction": debt.direction,
        "kind": debt.kind, "brand": debt.brand,
        "description": debt.description, "total": _num(debt.total), "remaining": _num(debts.remaining(debt)),
        "card_loan_group": debt.group_id,
        "installments": [_installment(i) for i in debt.installments],
    }


def _weight(w) -> dict | None:
    return {"date": w.date.isoformat(), "kg": _num(w.kg)} if w else None


# --- Lectura ---

@mcp.tool
def get_overview(from_date: str | None = None, to_date: str | None = None) -> dict:
    """Resumen de todo: plata del período, deudas, peso, promedios de los últimos 7 días y el día de hoy.
    Sin fechas, usa el mes en curso."""
    start, end = _range(from_date, to_date)
    with _db() as db:
        o = overview.overview(db, start, end)
        f, d, w = o["finance"], o["debts"], o["weight"]
        return {
            "today": today().isoformat(),
            "period": {"from": start.isoformat(), "to": end.isoformat()},
            "finance": {
                "income": _num(f["income"]), "expense": _num(f["expense"]), "balance": _num(f["balance"]),
                "expense_by_category": {c: _num(t) for c, t in f["by_category"]},
            },
            "debts": {
                "owed_to_me": _num(d["owed_to_me"]), "i_owe": _num(d["i_owe"]),
                "by_kind": {kind: {direction: _num(amount) for direction, amount in totals.items()}
                            for kind, totals in d["by_kind"].items()},
                "due_next_7_days": [
                    {"person": i.debt.person, "direction": i.debt.direction,
                     "kind": i.debt.kind, "brand": i.debt.brand, **_installment(i)} for i in d["due_soon"]
                ],
                "card_installments_not_yet_repaid": [
                    {"person": a["person"], "card": a["card"],
                     "kind": a["installment"].debt.kind, "brand": a["installment"].debt.brand,
                     **_installment(a["installment"])}
                    for a in d["card_alerts"]
                ],
                "payment_claims_waiting_my_confirmation": [
                    {"guest": c.guest.name, "message": c.message, "amount": _num(guests.claim_total(c)),
                     "installments": [_installment(i) for i in c.installments]}
                    for c in d["pending_claims"]
                ],
            },
            "weight": {
                "start": _weight(w["start"]), "current": _weight(w["current"]),
                "30_days_ago": _weight(w["month_ago"]), "goal_kg": _num(w["goal"]),
            },
            "last_7_days": {k: _num(v) if k != "days" else v for k, v in o["last_7_days"].items()},
            "today_checkin_done": o["today"]["checkin"] is not None,
            "today_meals_logged": o["today"]["meals"],
            "home_list_pending": o["home_pending"],
        }


@mcp.tool
def list_transactions(from_date: str | None = None, to_date: str | None = None, category: str | None = None) -> list[dict]:
    """Ingresos y gastos del período (por defecto, el mes en curso). kind: income | expense."""
    start, end = _range(from_date, to_date)
    with _db() as db:
        return [
            {"id": t.id, "date": t.date.isoformat(), "kind": t.kind, "amount": _num(t.amount),
             "category": t.category, "note": t.note, "source": t.source}
            for t in finance.list_transactions(db, start, end, category)
        ]


@mcp.tool
def get_debts(include_settled: bool = False) -> list[dict]:
    """Deudas con sus cuotas. direction: owed_to_me (me deben) | i_owe (debo).
    kind: person | card | entity; brand: marca del catálogo o null.
    Una tarjeta prestada son dos deudas con el mismo card_loan_group."""
    with _db() as db:
        return [_debt(d) for d in debts.list_debts(db, include_settled)]


@mcp.tool
def get_weight_series(from_date: str | None = None, to_date: str | None = None) -> list[dict]:
    """Pesos registrados (kg). Sin fechas, todo el historial."""
    start = dt.date.fromisoformat(from_date) if from_date else None
    end = dt.date.fromisoformat(to_date) if to_date else None
    with _db() as db:
        return [_weight(w) for w in body.weight_series(db, start, end)]


@mcp.tool
def get_food_log(from_date: str | None = None, to_date: str | None = None) -> list[dict]:
    """Comidas en texto libre con fecha y hora. Sin fechas, los últimos 7 días."""
    start, end = _range(from_date, to_date, default_days=7)
    with _db() as db:
        return [{"at": e.at.isoformat(timespec="minutes"), "text": e.text} for e in body.food_log(db, start, end)]


@mcp.tool
def get_checkins(from_date: str | None = None, to_date: str | None = None) -> dict:
    """Check-ins diarios (horas de sueño, ánimo 1-5, minutos de movimiento, nota) y revisiones semanales.
    Sin fechas, los últimos 30 días."""
    start, end = _range(from_date, to_date, default_days=30)
    with _db() as db:
        return {
            "daily": [
                {"date": c.date.isoformat(), "sleep_hours": _num(c.sleep_hours), "mood": c.mood,
                 "movement_min": c.movement_min, "note": c.note}
                for c in checkins.list_checkins(db, start, end)
            ],
            "weekly_reviews": [
                {"week_start": r.week_start.isoformat(), "went_well": r.went_well, "change": r.change}
                for r in checkins.list_reviews(db, start, end)
            ],
        }


@mcp.tool
def get_market_trips(limit: int = 10) -> list[dict]:
    """Últimas compras de súper con productos, precios y total."""
    with _db() as db:
        return [
            {"date": t.closed_at.date().isoformat(), "total": _num(t.total), "budget": _num(t.budget),
             "done_by": t.guest.name if t.guest else "me", "counted_as_my_expense": t.transaction_id is not None,
             "items": [{"name": i.name or None, "price": _num(i.price), "qty": _num(i.qty)} for i in t.items]}
            for t in lists.recent_trips(db, limit)
        ]


@mcp.tool
def get_price_history(product: str) -> list[dict]:
    """Precios pagados por un producto a lo largo del tiempo (para ver cuánto subió)."""
    with _db() as db:
        return [{"date": r.date.isoformat(), "price": _num(r.price)} for r in lists.price_history(db, product)]


# --- Escritura ---

@mcp.tool(description=(
    "Registra un ingreso (kind='income') o gasto (kind='expense'). "
    f"Categorías de gasto: {', '.join(finance.EXPENSE_CATEGORIES)}. "
    f"Categorías de ingreso: {', '.join(finance.INCOME_CATEGORIES)}."
))
def add_transaction(kind: str, amount: float, category: str, note: str = "", date: str | None = None) -> dict:
    with _db() as db:
        tx = finance.add_transaction(
            db, kind=kind, amount=Decimal(str(amount)), category=category, note=note,
            date=dt.date.fromisoformat(date) if date else None,
        )
        return {"id": tx.id, "date": tx.date.isoformat()}


@mcp.tool
def log_food(text: str) -> dict:
    """Registra una comida en texto libre, con la hora actual."""
    with _db() as db:
        entry = body.log_food(db, text)
        return {"id": entry.id, "at": entry.at.isoformat(timespec="minutes")}


@mcp.tool
def log_weight(kg: float, date: str | None = None) -> dict:
    """Registra el peso del día (si ya había uno ese día, lo reemplaza)."""
    with _db() as db:
        w = body.log_weight(db, Decimal(str(kg)), dt.date.fromisoformat(date) if date else None)
        return _weight(w)


@mcp.tool
def add_to_home_list(items: str) -> list[str]:
    """Agrega cosas a la lista de compras de la casa. Varias separadas por coma."""
    with _db() as db:
        return [i.name for i in lists.add_home_items(db, items)]


@mcp.prompt
def weekly_review() -> str:
    """Revisión semanal: cruza todas las áreas y marca fallas concretas."""
    return f"""Hoy es {today().isoformat()}. Hacé mi revisión semanal con las tools de Mentor.

1. Llamá a get_overview, get_checkins (últimos 14 días), get_food_log (últimos 7),
   list_transactions (mes en curso), get_debts y get_weight_series (últimos 90 días).
2. Buscá cruces entre áreas, no solo dentro de cada una. Por ejemplo:
   - ¿Los días que dormí poco gasté más en comida afuera o tuve peor ánimo?
   - ¿El peso se mueve con lo que como o con el movimiento?
   - ¿Hay cuotas de tarjeta prestada que vencen y la otra persona no me pagó?
   - ¿Qué categoría de gasto creció contra lo habitual?
3. Decime como máximo 3 fallas concretas, con el dato que las respalda, y una acción chica
   para cada una que pueda hacer esta semana.
4. Si faltan datos para concluir algo (días sin check-in, sin peso, etc.), decilo también.

Sé directo y breve. Nada de consejos genéricos."""


if __name__ == "__main__":
    init_db()
    mcp.run()
