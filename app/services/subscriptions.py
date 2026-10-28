"""Suscripciones: gastos que se repiten (IA, streaming, cursos). Al cobrarse pasan a Plata."""
import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import add_months, today
from app.models import Subscription, Transaction
from app.services import brands
from app.services.finance import new_transaction

CATEGORIES = ["IA", "Streaming", "Cursos", "Software", "Música", "Otros"]
CURRENCIES = ("ARS", "USD")
PERIODS = {"monthly": 1, "yearly": 12}
PERIOD_LABELS = {"monthly": "Mensual", "yearly": "Anual"}
# Para autocompletar el nombre; se puede escribir cualquier otro.
SUGGESTIONS = [
    "ChatGPT", "Claude", "Cursor", "GitHub Copilot", "Gemini", "Perplexity", "Midjourney",
    "Netflix", "Disney+", "Max", "Prime Video", "Paramount+", "YouTube Premium", "Crunchyroll",
    "Spotify", "Apple Music", "iCloud+", "Google One", "Platzi", "Udemy", "Coursera", "Domestika",
]
PAYMENT_OPTIONS = {**brands.ENTITIES, **brands.CARDS}


def _amount(value) -> Decimal:
    value = Decimal(value)
    if not value.is_finite() or value <= 0:
        raise ValueError("El monto tiene que ser mayor a cero")
    return value


def _validate(sub: Subscription) -> None:
    sub.name = sub.name.strip()[:80]
    if not sub.name:
        raise ValueError("Poné el nombre de la suscripción")
    if sub.currency not in CURRENCIES:
        raise ValueError("La moneda es ARS o USD")
    if sub.period not in PERIODS:
        raise ValueError("La frecuencia es monthly o yearly")
    if sub.category not in CATEGORIES:
        raise ValueError(f"Categoría inválida: usá {', '.join(CATEGORIES)}")
    if sub.paid_with and sub.paid_with not in PAYMENT_OPTIONS:
        raise ValueError("Ese medio de pago no está en el catálogo")


def create_subscription(
    db: Session, *, name: str, amount: Decimal, currency: str = "ARS", period: str = "monthly",
    category: str = "Otros", next_charge: dt.date | None = None, paid_with: str | None = None, note: str = "",
) -> Subscription:
    sub = Subscription(
        name=name, amount=_amount(amount), currency=currency, period=period, category=category,
        next_charge=next_charge or today(), paid_with=paid_with or None, note=note.strip()[:200],
    )
    _validate(sub)
    db.add(sub)
    db.commit()
    return sub


def list_subscriptions(db: Session, include_paused: bool = True) -> list[Subscription]:
    query = select(Subscription).order_by(Subscription.active.desc(), Subscription.next_charge, Subscription.name)
    if not include_paused:
        query = query.where(Subscription.active.is_(True))
    return list(db.scalars(query))


def monthly_totals(subs: list[Subscription]) -> dict[str, Decimal]:
    """Cuánto cuestan por mes las activas, por moneda (una anual cuenta un doceavo)."""
    totals = {currency: Decimal(0) for currency in CURRENCIES}
    for sub in subs:
        if sub.active:
            totals[sub.currency] += sub.amount / PERIODS[sub.period]
    return {currency: total.quantize(Decimal("0.01")) for currency, total in totals.items()}


def due_until(db: Session, until: dt.date) -> list[Subscription]:
    """Activas que se cobran hasta `until`, incluidas las que ya pasaron sin marcar."""
    return list(db.scalars(
        select(Subscription).where(Subscription.active.is_(True), Subscription.next_charge <= until)
        .order_by(Subscription.next_charge)
    ))


def mark_charged(
    db: Session, subscription_id: int, *, amount_ars: Decimal | None = None, on: dt.date | None = None,
) -> Transaction:
    """Registra el cobro como gasto en Plata y corre el próximo cobro un período."""
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise ValueError("No existe esa suscripción")
    if amount_ars is None:
        if sub.currency != "ARS":
            raise ValueError("Poné cuánto se cobró en pesos")
        amount_ars = sub.amount
    note = sub.name if sub.currency == "ARS" else f"{sub.name} (US$ {sub.amount:.2f})"
    tx = new_transaction(
        kind="expense", amount=_amount(amount_ars), category="Suscripciones",
        date=on or today(), note=note, source="subscription",
    )
    db.add(tx)
    sub.next_charge = add_months(sub.next_charge, PERIODS[sub.period])
    db.commit()
    return tx


def set_active(db: Session, subscription_id: int, active: bool) -> Subscription:
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise ValueError("No existe esa suscripción")
    sub.active = active
    db.commit()
    return sub


def delete_subscription(db: Session, subscription_id: int) -> None:
    """Borra la suscripción. Los cobros ya registrados quedan en Plata."""
    if sub := db.get(Subscription, subscription_id):
        db.delete(sub)
        db.commit()
