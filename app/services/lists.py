import re
from decimal import Decimal
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import now, today
from app.core.numbers import parse_amount
from app.models import HomeItem, MarketItem, MarketTrip, PriceRecord
from app.services.finance import new_transaction


def normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


# --- Lista de casa ---

def home_items(db: Session) -> list[HomeItem]:
    return list(db.scalars(select(HomeItem).order_by(HomeItem.done, HomeItem.created_at)))


MAX_HOME_ITEMS = 300
MAX_TRIP_ITEMS = 400


def add_home_items(db: Session, text: str) -> list[HomeItem]:
    """Acepta varios de una: 'leche, pan' o uno por renglón. No duplica pendientes."""
    pending = {normalize(i.name) for i in db.scalars(select(HomeItem).where(HomeItem.done.is_(False)))}
    room = MAX_HOME_ITEMS - (db.scalar(select(func.count(HomeItem.id))) or 0)
    added = []
    for name in re.split(r"[,\n]", text[:5000]):
        name = re.sub(r"\s+", " ", name).strip()[:80]
        if name and normalize(name) not in pending and len(added) < room:
            pending.add(normalize(name))
            added.append(HomeItem(name=name))
    db.add_all(added)
    db.commit()
    return added


def toggle_home_item(db: Session, item_id: int) -> None:
    if item := db.get(HomeItem, item_id):
        item.done = not item.done
        db.commit()


def delete_home_item(db: Session, item_id: int) -> None:
    if item := db.get(HomeItem, item_id):
        db.delete(item)
        db.commit()


def clear_done(db: Session) -> None:
    for item in db.scalars(select(HomeItem).where(HomeItem.done.is_(True))):
        db.delete(item)
    db.commit()


def whatsapp_text(items: list[HomeItem]) -> str:
    lines = [f"- {i.name}" for i in items if not i.done]
    return "\n".join(["🛒 Lista de compras", *lines])


def whatsapp_url(text: str) -> str:
    return "https://wa.me/?text=" + quote(text)


# --- Mercado ---

def last_prices(db: Session) -> dict[str, Decimal]:
    """Último precio pagado por cada producto (por nombre normalizado)."""
    latest = (
        select(PriceRecord.product, func.max(PriceRecord.id).label("id"))
        .group_by(PriceRecord.product).subquery()
    )
    rows = db.execute(select(PriceRecord.product, PriceRecord.price).join(latest, PriceRecord.id == latest.c.id))
    return {product: price for product, price in rows}


def price_history(db: Session, product: str) -> list[PriceRecord]:
    return list(db.scalars(
        select(PriceRecord).where(PriceRecord.product == normalize(product)).order_by(PriceRecord.date, PriceRecord.id)
    ))


def open_trip(db: Session, guest_id: int | None = None) -> MarketTrip | None:
    """La compra abierta de cada uno: la mía (guest_id None) o la de un invitado."""
    return db.scalar(
        select(MarketTrip).options(selectinload(MarketTrip.items))
        .where(
            MarketTrip.closed_at.is_(None),
            MarketTrip.guest_id.is_(None) if guest_id is None else MarketTrip.guest_id == guest_id,
        )
        .order_by(MarketTrip.id.desc())
    )


def start_trip(db: Session, guest_id: int | None = None) -> MarketTrip:
    """Abre una compra (o devuelve la abierta) y trae lo pendiente de la lista de casa, sin precio."""
    if trip := open_trip(db, guest_id):
        return trip
    trip = MarketTrip(guest_id=guest_id)
    pending = db.scalars(select(HomeItem).where(HomeItem.done.is_(False)).order_by(HomeItem.created_at))
    for position, item in enumerate(pending):
        trip.items.append(MarketItem(name=item.name, price=Decimal(0), qty=Decimal(1), position=position))
    db.add(trip)
    db.commit()
    return trip


def _decimal(value, default: Decimal, *, thousands: bool = True) -> Decimal:
    number = parse_amount(value, thousands=thousands)
    return number if number is not None and number >= 0 else default


def save_trip(db: Session, trip_id: int, items: list[dict], budget=None) -> MarketTrip:
    """Reemplaza los productos de una compra abierta con lo que manda el navegador."""
    trip = db.get(MarketTrip, trip_id)
    if trip is None or trip.closed_at is not None:
        raise ValueError("Esa compra no está abierta")
    if not isinstance(items, list) or len(items) > MAX_TRIP_ITEMS or not all(isinstance(i, dict) for i in items):
        raise ValueError(f"Una compra puede tener hasta {MAX_TRIP_ITEMS} productos")
    trip.items.clear()
    for position, raw in enumerate(items):
        name = re.sub(r"\s+", " ", str(raw.get("name", ""))).strip()[:80]
        price = _decimal(raw.get("price"), Decimal(0))
        if name or price:  # un precio sin nombre vale: modo "solo precios"
            trip.items.append(MarketItem(
                name=name, price=price, qty=_decimal(raw.get("qty"), Decimal(1), thousands=False) or Decimal(1), position=position,
            ))
    budget = _decimal(budget, Decimal(0))
    trip.budget = budget or None
    db.commit()
    return trip


def _expense_for(trip: MarketTrip, db: Session) -> None:
    bought = [i for i in trip.items if i.price > 0]
    who = f" de {trip.guest.name}" if trip.guest else ""
    tx = new_transaction(
        kind="expense", amount=trip.total, category="Súper",
        note=f"Compra{who} ({len(bought)} producto{'s' if len(bought) != 1 else ''})", source="market",
    )
    db.add(tx)
    db.flush()
    trip.transaction_id = tx.id


def close_trip(db: Session, trip_id: int) -> MarketTrip:
    """Cierra la compra: guarda precios, tacha la lista de casa y, si la hice yo, la carga como gasto."""
    trip = db.get(MarketTrip, trip_id)
    if trip is None or trip.closed_at is not None:
        raise ValueError("Esa compra no está abierta")
    bought = [i for i in trip.items if i.price > 0]
    if not bought:
        raise ValueError("Anotá al menos un precio")
    if trip.guest_id is None:
        _expense_for(trip, db)
    trip.closed_at = now()
    for item in bought:
        if item.name:
            db.add(PriceRecord(product=normalize(item.name), price=item.price, date=today()))
    names = {normalize(i.name) for i in bought if i.name}
    for home in db.scalars(select(HomeItem).where(HomeItem.done.is_(False))):
        if normalize(home.name) in names:
            home.done = True
    db.commit()
    return trip


def charge_to_me(db: Session, trip_id: int) -> MarketTrip:
    """Una compra que hizo un invitado y pagué yo: la cargo como gasto mío."""
    trip = db.get(MarketTrip, trip_id)
    if trip is None or trip.closed_at is None or trip.transaction_id is not None:
        raise ValueError("Esa compra no se puede cargar")
    _expense_for(trip, db)
    db.commit()
    return trip


def discard_trip(db: Session, trip_id: int) -> None:
    trip = db.get(MarketTrip, trip_id)
    if trip is not None and trip.closed_at is None:
        db.delete(trip)
        db.commit()


def recent_trips(db: Session, limit: int = 10, guest_id: int | None = None) -> list[MarketTrip]:
    """Últimas compras cerradas. Con guest_id, solo las de ese invitado."""
    q = select(MarketTrip).options(selectinload(MarketTrip.items)).where(MarketTrip.closed_at.is_not(None))
    if guest_id is not None:
        q = q.where(MarketTrip.guest_id == guest_id)
    return list(db.scalars(q.order_by(MarketTrip.closed_at.desc()).limit(limit)))
