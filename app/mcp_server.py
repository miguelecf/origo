"""MCP de Mentor: el agente lee lo mismo que ves en la app (misma capa de servicios).

Local (Claude Code, Claude Desktop): `uv run python -m app.mcp_server` por stdio, sin auth.
Remoto (Claude.ai, ChatGPT): se monta en /mcp dentro de la app web, con OAuth de GitHub
y restringido a GITHUB_ALLOWED_LOGIN.
"""

import datetime as dt
from contextlib import contextmanager
from decimal import Decimal

from fastmcp import FastMCP

from app.core.clock import month_bounds, today
from app.core.database import SessionLocal, init_db
from app.services import body, brands, checkins, debts, finance, guests, lists, overview, subscriptions

INSTRUCTIONS = """\
Registro personal de la vida de una persona: plata, deudas, peso, comidas, sueño, ánimo,
movimiento y compras. Montos en la moneda local, fechas en formato ISO (YYYY-MM-DD).
Los rangos son [from_date, to_date): incluye el inicio y excluye el final.
Para analizar, empezá por get_overview y después bajá al detalle que necesites.
Las tools de escritura guardan de verdad: confirmá montos y fechas antes de llamarlas, y para
borrar algo pedí siempre confirmación explícita.
"""


mcp = FastMCP("Mentor", instructions=INSTRUCTIONS, mask_error_details=True)


def remote_http_app():
    from app.services.mcp_auth import remote_auth

    remote = FastMCP("Mentor", instructions=INSTRUCTIONS, auth=remote_auth(), mask_error_details=True)
    remote.mount(mcp)
    return remote.http_app(path="/mcp")


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


def _date(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def _catalog(kind: str) -> str:
    return ", ".join(f"{slug} ({name})" for slug, name in brands.CATALOGS[kind].items())


def _subscription(s) -> dict:
    return {
        "id": s.id, "name": s.name, "amount": _num(s.amount), "currency": s.currency, "period": s.period,
        "category": s.category, "next_charge": s.next_charge.isoformat(), "paid_with": s.paid_with,
        "note": s.note, "active": s.active,
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
                    {"claim_id": c.id, "guest": c.guest.name, "message": c.message, "amount": _num(guests.claim_total(c)),
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
            "subscriptions": {
                "monthly_cost": {c: _num(v) for c, v in o["subscriptions"]["monthly"].items()},
                "charging_next_7_days": [_subscription(s) for s in o["subscriptions"]["due_soon"]],
            },
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


@mcp.tool
def get_home_list() -> list[dict]:
    """Lista de compras de la casa: pendientes primero, después las tachadas."""
    with _db() as db:
        return [{"id": i.id, "name": i.name, "done": i.done} for i in lists.home_items(db)]


@mcp.tool
def toggle_home_item(item_id: int) -> dict:
    """Tacha un producto de la lista de casa (o lo destacha si ya estaba tachado)."""
    with _db() as db:
        lists.toggle_home_item(db, item_id)
        return {"items": [{"id": i.id, "name": i.name, "done": i.done} for i in lists.home_items(db)]}


@mcp.tool
def get_due_payments(days: int = 7) -> list[dict]:
    """Cuotas sin pagar que vencen en los próximos `days` días, incluidas las atrasadas.
    Sirve para avisos de pago: direction i_owe es lo que pago yo, owed_to_me lo que me tienen que pagar."""
    with _db() as db:
        return [
            {"debt_id": i.debt.id, "person": i.debt.person, "direction": i.debt.direction,
             "kind": i.debt.kind, "brand": i.debt.brand, "overdue": i.due_date < today(), **_installment(i)}
            for i in debts.due_until(db, today() + dt.timedelta(days=max(0, min(days, 366))))
        ]


@mcp.tool(description=(
    "Anota una deuda en cuotas iguales. direction: owed_to_me (me deben) | i_owe (debo). "
    "kind: person | card | entity. Tarjetas y entidades siempre son i_owe. "
    "Una tarjeta necesita brand y first_due. Si person queda vacío, se usa el nombre de la marca. "
    f"Marcas de tarjeta: {_catalog('card')}. Entidades: {_catalog('entity')}. "
    "Para una entidad que no está en la lista, brand vacío y person con el nombre."
))
def add_debt(
    person: str, direction: str, total: float, installments: int = 1, first_due: str | None = None,
    description: str = "", kind: str = "person", brand: str | None = None,
) -> dict:
    with _db() as db:
        debt = debts.create_debt(
            db, person=person, direction=direction, total=Decimal(str(total)), installments=installments,
            first_due=_date(first_due), description=description, kind=kind, brand=brand,
        )
        return _debt(debt)


@mcp.tool(description=(
    "Tarjeta prestada: la persona me debe las cuotas y yo se las debo a la tarjeta. Crea las dos "
    f"deudas enlazadas. card es el nombre de la tarjeta (ej. 'Visa Galicia'); brand: {_catalog('card')}."
))
def lend_card(
    person: str, card: str, total: float, installments: int, first_due: str,
    description: str = "", brand: str | None = None,
) -> list[dict]:
    with _db() as db:
        pair = debts.create_card_loan(
            db, person=person, card=card, total=Decimal(str(total)), installments=installments,
            first_due=dt.date.fromisoformat(first_due), description=description, brand=brand,
        )
        return [_debt(d) for d in pair]


@mcp.tool
def set_installment_paid(installment_id: int, paid: bool = True, date: str | None = None) -> dict:
    """Marca una cuota como pagada (o la desmarca). Al pagarla se registra sola en Plata:
    ingreso si me la pagaron, gasto si la pagué yo. Los id de cuota salen de get_debts o get_due_payments."""
    with _db() as db:
        return _installment(debts.set_installment_paid(db, installment_id, paid, _date(date)))


@mcp.tool
def resolve_payment_claim(claim_id: int, accept: bool, reply: str = "") -> dict:
    """Confirma o rechaza un aviso de pago de un invitado (claim_id sale de get_overview).
    Confirmar marca sus cuotas como cobradas."""
    with _db() as db:
        claim = guests.resolve_claim(db, claim_id, accept, reply)
        return {"claim_id": claim.id, "status": claim.status}


@mcp.tool
def save_checkin(
    date: str | None = None, sleep_hours: float | None = None, mood: int | None = None,
    movement_min: int | None = None, note: str | None = None,
) -> dict:
    """Check-in del día (por defecto hoy): horas de sueño, ánimo 1-5, minutos de movimiento y una nota.
    Lo que no mandes conserva el valor que ya tenía ese día."""
    with _db() as db:
        c = checkins.update_checkin(
            db, _date(date) or today(), sleep_hours=Decimal(str(sleep_hours)) if sleep_hours is not None else None,
            mood=mood, movement_min=movement_min, note=note,
        )
        return {"date": c.date.isoformat(), "sleep_hours": _num(c.sleep_hours), "mood": c.mood,
                "movement_min": c.movement_min, "note": c.note}


@mcp.tool
def set_weight_goal(kg: float | None = None) -> dict:
    """Fija la meta de peso en kg. Sin valor, la quita."""
    with _db() as db:
        body.set_goal(db, Decimal(str(kg)) if kg is not None else None)
        return {"goal_kg": _num(body.get_goal(db))}


@mcp.tool
def delete_transaction(transaction_id: int) -> dict:
    """Borra un ingreso o gasto mal cargado (id de list_transactions). Si era el pago de una cuota,
    la cuota vuelve a quedar pendiente. Solo con confirmación explícita del dueño."""
    with _db() as db:
        finance.delete_transaction(db, transaction_id)
        return {"deleted": transaction_id}


@mcp.tool
def get_subscriptions(include_paused: bool = True) -> dict:
    """Suscripciones (IA, streaming, cursos...) con su próximo cobro, y el costo mensual de las activas
    por moneda (ARS y USD por separado; una anual cuenta un doceavo)."""
    with _db() as db:
        subs = subscriptions.list_subscriptions(db, include_paused)
        return {"monthly_cost": {c: _num(v) for c, v in subscriptions.monthly_totals(subs).items()},
                "subscriptions": [_subscription(s) for s in subs]}


@mcp.tool(description=(
    "Anota una suscripción. currency: ARS | USD. period: monthly | yearly. "
    f"category: {', '.join(subscriptions.CATEGORIES)}. next_charge: fecha del próximo cobro (por defecto hoy). "
    f"paid_with (opcional), con qué se paga: {', '.join(subscriptions.PAYMENT_OPTIONS)}."
))
def add_subscription(
    name: str, amount: float, currency: str = "ARS", period: str = "monthly", category: str = "Otros",
    next_charge: str | None = None, paid_with: str | None = None, note: str = "",
) -> dict:
    with _db() as db:
        return _subscription(subscriptions.create_subscription(
            db, name=name, amount=Decimal(str(amount)), currency=currency, period=period, category=category,
            next_charge=_date(next_charge), paid_with=paid_with, note=note,
        ))


@mcp.tool
def mark_subscription_charged(subscription_id: int, amount_ars: float | None = None, date: str | None = None) -> dict:
    """Registra el cobro de una suscripción como gasto en Plata (categoría Suscripciones) y pasa el
    próximo cobro al período siguiente. Si es en USD, amount_ars (lo que salió en pesos) es obligatorio."""
    with _db() as db:
        tx = subscriptions.mark_charged(
            db, subscription_id, amount_ars=Decimal(str(amount_ars)) if amount_ars is not None else None, on=_date(date),
        )
        sub = db.get(subscriptions.Subscription, subscription_id)
        return {"transaction_id": tx.id, "amount": _num(tx.amount), "next_charge": sub.next_charge.isoformat()}


@mcp.tool
def set_subscription_active(subscription_id: int, active: bool) -> dict:
    """Pausa (active=false) o reactiva una suscripción. Pausada no suma al costo mensual."""
    with _db() as db:
        return _subscription(subscriptions.set_active(db, subscription_id, active))


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
