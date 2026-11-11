"""MCP de Origo: el agente lee lo mismo que ves en la app (misma capa de servicios).

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
from app.services import body, brands, checkins, debts, diet, finance, guests, lists, overview, subscriptions, training

INSTRUCTIONS = """\
Registro personal de la vida de una persona: plata, deudas, peso, comidas, sueño, ánimo,
movimiento y compras. Montos en la moneda local, fechas en formato ISO (YYYY-MM-DD).
Los rangos son [from_date, to_date): incluye el inicio y excluye el final.
Para analizar, empezá por get_overview y después bajá al detalle que necesites.
Las tools de escritura guardan de verdad: confirmá montos y fechas antes de llamarlas, y para
borrar algo pedí siempre confirmación explícita.
El plan (dieta y rutina) no es lo hecho: los objetivos del plan no son comidas consumidas, y la
rutina no marca entrenamientos como realizados. La rutina y la dieta son fijas por día de la
semana (0 = lunes ... 6 = domingo): no rotan solas.
Dieta: una comida por momento y por día, en un solo renglón. Leé `format` en get_diet_plan.
"""


mcp = FastMCP("Origo", instructions=INSTRUCTIONS, mask_error_details=True)


def remote_http_app():
    from app.services.mcp_auth import remote_auth

    remote = FastMCP("Origo", instructions=INSTRUCTIONS, auth=remote_auth(), mask_error_details=True)
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
    if not w:
        return None
    data = {"id": w.id, "date": w.date.isoformat(), "kg": _num(w.kg)}
    for field in body.COMPOSITION:
        value = getattr(w, field)
        if value is not None:
            data[field] = value if field == "visceral_fat" else _num(value)
    return data


def _milestone(m) -> dict:
    return {"id": m.id, "kg": _num(m.kg), "note": m.note}


def _routine_item(i) -> dict:
    return {"id": i.id, "weekday": i.weekday, "exercise": i.exercise.name, "sets": i.sets, "reps": i.reps,
            "reps_max": i.reps_max, "reps_text": training.format_reps(i.reps, i.reps_max), "kg": _num(i.kg),
            "position": i.position}


def _day(plan: dict) -> dict:
    return {"weekday": plan["weekday"], "name": plan["name"], "title": plan["title"],
            "items": [_routine_item(i) for i in plan["items"]]}


def _targets(t) -> dict:
    return {"kcal": t.kcal, "protein_g": t.protein_g, "carbs_g": t.carbs_g, "fat_g": t.fat_g,
            "rules": t.rules or "", "supplements": t.supplements or ""}


def _clear(fields: list[str] | None, allowed) -> set[str]:
    fields = set(fields or [])
    if unknown := fields - set(allowed):
        raise ValueError(f"No se puede limpiar: {', '.join(sorted(unknown))}")
    return fields


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
                "next_milestone": _milestone(w["next_milestone"]) if w["next_milestone"] else None,
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
    """Pesos registrados (kg), con la composición de la balanza si se cargó ese día
    (fat_pct, muscle_pct, lean_kg, water_pct, visceral_fat). Sin fechas, todo el historial."""
    start = dt.date.fromisoformat(from_date) if from_date else None
    end = dt.date.fromisoformat(to_date) if to_date else None
    with _db() as db:
        return [_weight(w) for w in body.weight_series(db, start, end)]


@mcp.tool
def get_food_log(from_date: str | None = None, to_date: str | None = None) -> list[dict]:
    """Comidas en texto libre con fecha y hora. Sin fechas, los últimos 7 días."""
    start, end = _range(from_date, to_date, default_days=7)
    with _db() as db:
        return [{"id": e.id, "at": e.at.isoformat(timespec="minutes"), "text": e.text}
                for e in body.food_log(db, start, end)]


@mcp.tool
def delete_food_entry(entry_id: int) -> dict:
    """Borra una comida registrada (el id sale de get_food_log). Pedí confirmación antes."""
    with _db() as db:
        if not body.delete_food(db, entry_id):
            raise ValueError("No existe esa comida")
        return {"deleted": entry_id}


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
             "split_with": t.split_with, "my_total": _num(t.my_total) if t.split_with else None,
             "items": [{"name": i.name or None, "price": _num(i.price), "qty": _num(i.qty),
                        **({"my_pct": 100 if i.my_pct is None else i.my_pct} if t.split_with else {})}
                       for i in t.items]}
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
def log_weight(
    kg: float, date: str | None = None, fat_pct: float | None = None, muscle_pct: float | None = None,
    lean_kg: float | None = None, water_pct: float | None = None, visceral_fat: int | None = None,
) -> dict:
    """Registra el peso del día y, si los hay, los valores de la balanza de bioimpedancia:
    fat_pct (% grasa), muscle_pct (% músculo), lean_kg (masa magra), water_pct (% agua) y
    visceral_fat (índice de grasa visceral). Si ya había un registro ese día, reemplaza el peso y
    solo los valores que mandes: lo que no mandes queda como estaba. Mandá solo lo que dio la
    balanza o dijo el usuario; no estimes valores."""
    def dec(value):
        return Decimal(str(value)) if value is not None else None
    with _db() as db:
        w = body.log_weight(
            db, Decimal(str(kg)), _date(date), fat_pct=dec(fat_pct), muscle_pct=dec(muscle_pct),
            lean_kg=dec(lean_kg), water_pct=dec(water_pct), visceral_fat=visceral_fat,
        )
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
    """Fija la meta FINAL de peso en kg. Sin valor, la quita. Para un escalón intermedio
    ("mi próximo objetivo es 105") usá add_weight_milestone: esta tool pisa la meta final."""
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


# --- Peso: meta e hitos ---

@mcp.tool
def get_weight_goals() -> dict:
    """La meta final de peso y los hitos intermedios (de mayor a menor), con el próximo a alcanzar."""
    with _db() as db:
        current = body.weight_series(db)[-1:] or [None]
        nxt = body.next_milestone(db, current[0].kg if current[0] else None)
        return {"goal_kg": _num(body.get_goal(db)), "current": _weight(current[0]),
                "milestones": [_milestone(m) for m in body.milestones(db)],
                "next_milestone": _milestone(nxt) if nxt else None}


@mcp.tool
def add_weight_milestone(kg: float, note: str = "") -> dict:
    """Suma un hito intermedio de peso (ej. 105 kg camino a la meta final). No cambia la meta final."""
    with _db() as db:
        return _milestone(body.add_milestone(db, Decimal(str(kg)), note))


@mcp.tool
def delete_weight_milestone(milestone_id: int) -> dict:
    """Borra un hito (id de get_weight_goals). Solo con confirmación explícita del dueño."""
    with _db() as db:
        return {"deleted": milestone_id if body.delete_milestone(db, milestone_id) else None}


# --- Dieta (Cuerpo → Dieta) ---

def _week_days(weekdays: list[int] | None) -> list[int]:
    if not weekdays:
        raise ValueError("Mandá weekdays: lista de días, 0 = lunes ... 6 = domingo")
    return weekdays


@mcp.tool(description=(
    "Plan de alimentación tal como se ve en Cuerpo → Dieta, y los objetivos del plan (kcal, macros, "
    "reglas, suplementos). Sin weekday trae la semana entera; con weekday (0 = lunes ... 6 = domingo), "
    "ese día. Leé `format` antes de escribir: " + diet.FORMAT + " Lo comido sale de get_food_log."
))
def get_diet_plan(weekday: int | None = None) -> dict:
    with _db() as db:
        meals = lambda day: [{"slot": m["key"], "name": m["name"], "from": m["from"].strftime("%H:%M"),
                              "meal": m["text"] or None} for m in day]
        days = [d for d in diet.week(db) if weekday is None or d["weekday"] == weekday]
        if weekday is not None and not days:
            raise ValueError("El día va de 0 (lunes) a 6 (domingo)")
        return {
            "format": diet.FORMAT,
            "days": [{"weekday": d["weekday"], "name": d["name"], "meals": meals(d["meals"])} for d in days],
            "today_weekday": today().weekday(),
            "current_slot": diet.current_slot(),
            "targets": _targets(diet.targets(db)),
        }


@mcp.tool(description=(
    "Pone UNA comida en un momento del plan, para uno o varios días. " + diet.FORMAT + " "
    "weekdays: lista de días (ej. [0] el lunes, [0,1,2,3,4,5,6] todos). Pisa lo que había en esos días "
    "y devuelve lo anterior (previous, por día) para poder deshacer. Para vaciar, clear_meal."
))
def set_meal(slot: str, text: str, weekdays: list[int]) -> dict:
    if not text.strip():
        raise ValueError("Para vaciar un momento usá clear_meal")
    with _db() as db:
        previous = diet.set_meal(db, slot, text, _week_days(weekdays))
        return {"slot": slot, "meal": diet.clean_meal(text), "previous": {str(d): t or None for d, t in previous.items()}}


@mcp.tool
def clear_meal(slot: str, weekdays: list[int]) -> dict:
    """Vacía un momento del plan en los días pedidos (0 = lunes ... 6 = domingo). Borra: pedí
    confirmación antes. Devuelve lo que había (previous, por día) para poder deshacer."""
    with _db() as db:
        previous = diet.clear_meal(db, slot, _week_days(weekdays))
        return {"slot": slot, "previous": {str(d): t or None for d, t in previous.items()}}


@mcp.tool
def copy_diet_day(from_weekday: int, to_weekdays: list[int]) -> dict:
    """Copia el día entero del plan (todos los momentos) a otros días (0 = lunes ... 6 = domingo).
    Pisa lo que tenían: pedí confirmación antes."""
    with _db() as db:
        diet.copy_day(db, from_weekday, _week_days(to_weekdays))
        return {"copied_from": from_weekday, "to": sorted(set(to_weekdays) - {from_weekday})}


@mcp.tool
def set_diet_targets(
    kcal: int | None = None, protein_g: int | None = None, carbs_g: int | None = None, fat_g: int | None = None,
    rules: str | None = None, supplements: str | None = None, clear: list[str] | None = None,
) -> dict:
    """Objetivos diarios del plan: kcal, proteína, carbohidratos y grasas en gramos, más reglas y
    suplementos en texto (uno por renglón; rules/supplements reemplazan el texto entero). Solo
    cambia lo que mandes; para borrar un campo, ponelo en `clear` (ej. ["kcal"]). No son comidas
    consumidas ni una recomendación médica: guardá lo que dice el plan del usuario."""
    with _db() as db:
        values = {k: v for k, v in {"kcal": kcal, "protein_g": protein_g, "carbs_g": carbs_g, "fat_g": fat_g,
                                     "rules": rules, "supplements": supplements}.items() if v is not None}
        for field in _clear(clear, [*diet.TARGET_NUMBERS, *diet.TARGET_TEXTS]):
            values[field] = None if field in diet.TARGET_NUMBERS else ""
        previous = _targets(diet.targets(db))
        return {"previous": previous, "targets": _targets(diet.set_targets(db, **values))}


# --- Rutina (Entreno → Rutina) ---

@mcp.tool
def get_routine(weekday: int | None = None) -> dict:
    """Rutina semanal tal como se ve en Entreno → Rutina. weekday 0 = lunes ... 6 = domingo; sin
    weekday, la semana entera. Un día sin ejercicios es descanso. Es fija por día de semana: no
    rota sola. reps_max no nulo significa rango (reps_text '8–12')."""
    with _db() as db:
        if weekday is not None:
            return _day(training.day_plan(db, training._weekday(weekday)))
        return {"today_weekday": today().weekday(), "days": [_day(d) for d in training.week(db)]}


@mcp.tool
def add_routine_item(
    weekday: int, exercise: str, sets: int, reps: int, reps_max: int | None = None, kg: float | None = None,
    allow_duplicate: bool = False,
) -> dict:
    """Agrega un ejercicio al final de un día de la rutina (0 = lunes). Para un rango de
    repeticiones, reps es el mínimo y reps_max el máximo (8 y 12). Si el ejercicio ya está ese día
    falla, salvo allow_duplicate=true. No lo marca como hecho."""
    with _db() as db:
        item = training.add_item(db, weekday, exercise, sets, reps, Decimal(str(kg)) if kg is not None else None,
                                 reps_max=reps_max, allow_duplicate=allow_duplicate)
        return _routine_item(item)


@mcp.tool
def update_routine_item(
    item_id: int, sets: int | None = None, reps: int | None = None, reps_max: int | None = None,
    kg: float | None = None, clear: list[str] | None = None,
) -> dict:
    """Cambia series, repeticiones o kilos de un ejercicio de la rutina (id de get_routine). Solo
    cambia lo que mandes; para pasar de rango a fijo o quitar los kilos usá clear=["reps_max"] o
    ["kg"]. El historial de lo ya hecho no cambia."""
    changes = {k: v for k, v in {"sets": sets, "reps": reps, "reps_max": reps_max}.items() if v is not None}
    if kg is not None:
        changes["kg"] = Decimal(str(kg))
    for field in _clear(clear, ["reps_max", "kg"]):
        changes[field] = None
    with _db() as db:
        return _routine_item(training.update_item(db, item_id, **changes))


@mcp.tool
def move_routine_item(item_id: int, direction: str) -> dict:
    """Sube (direction 'up') o baja ('down') un ejercicio dentro de su día. Devuelve el día."""
    if direction not in ("up", "down"):
        raise ValueError("direction es 'up' o 'down'")
    with _db() as db:
        training.move_item(db, item_id, -1 if direction == "up" else 1)
        item = db.get(training.RoutineItem, item_id)
        return _day(training.day_plan(db, item.weekday))


@mcp.tool
def delete_routine_item(item_id: int) -> dict:
    """Saca un ejercicio de la rutina (id de get_routine). Lo ya hecho queda en el historial.
    Solo con confirmación explícita del dueño, después de mostrarle qué vas a sacar."""
    with _db() as db:
        return {"deleted": item_id if training.delete_item(db, item_id) else None}


@mcp.tool
def set_routine_day_title(weekday: int, title: str) -> dict:
    """Nombre de un día de la rutina (0 = lunes), ej. 'Rutina A' o 'Pecho y tríceps'. Vacío lo quita."""
    with _db() as db:
        training.set_title(db, weekday, title)
        return _day(training.day_plan(db, weekday))


@mcp.tool
def get_workout_history(days: int = 30) -> list[dict]:
    """Lo que se marcó como hecho en Entreno en los últimos `days` días (máx. 366), por sesión.
    Solo lectura: marcar hecho es del usuario en la app."""
    with _db() as db:
        return [
            {"date": day.isoformat(), "exercises": [
                {"exercise": log.exercise.name, "sets": log.sets, "reps": log.reps, "reps_max": log.reps_max,
                 "kg": _num(log.kg)} for log in logs]}
            for day, logs in training.history(db, days=max(1, min(days, 366)))
        ]


@mcp.prompt
def weekly_review() -> str:
    """Revisión semanal: cruza todas las áreas y marca fallas concretas."""
    return f"""Hoy es {today().isoformat()}. Hacé mi revisión semanal con las tools de Origo.

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
