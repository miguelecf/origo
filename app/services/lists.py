import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import now, today
from app.models import HomeItem, MarketItem, MarketTrip, PriceRecord
from app.services.finance import new_transaction


def normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


# --- Lista de casa ---

def home_items(db: Session) -> list[HomeItem]:
    return list(db.scalars(select(HomeItem).order_by(HomeItem.done, HomeItem.created_at)))


def add_home_items(db: Session, text: str) -> list[HomeItem]:
    """Acepta varios de una: 'leche, pan' o uno por renglón. No duplica pendientes."""
    pending = {normalize(i.name) for i in db.scalars(select(HomeItem).where(HomeItem.done.is_(False)))}
    added = []
    for name in re.split(r"[,\n]", text):
        name = re.sub(r"\s+", " ", name).strip()
        if name and normalize(name) not in pending:
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


def open_trip(db: Session) -> MarketTrip | None:
    return db.scalar(
        select(MarketTrip).options(selectinload(MarketTrip.items))
        .where(MarketTrip.closed_at.is_(None)).order_by(MarketTrip.id.desc())
    )


def start_trip(db: Session) -> MarketTrip:
    """Abre una compra (o devuelve la abierta) y trae lo pendiente de la lista de casa, sin precio."""
    if trip := open_trip(db):
        return trip
    trip = MarketTrip()
    pending = db.scalars(select(HomeItem).where(HomeItem.done.is_(False)).order_by(HomeItem.created_at))
    for position, item in enumerate(pending):
        trip.items.append(MarketItem(name=item.name, price=Decimal(0), qty=Decimal(1), position=position))
    db.add(trip)
    db.commit()
    return trip


def _decimal(value, default: Decimal) -> Decimal:
    try:
        number = Decimal(str(value).replace(",", ".")) if value not in (None, "") else default
    except InvalidOperation:
        return default
    return number if number.is_finite() and number >= 0 else default


def save_trip(db: Session, trip_id: int, items: list[dict], budget=None) -> MarketTrip:
    """Reemplaza los productos de una compra abierta con lo que manda el navegador."""
    trip = db.get(MarketTrip, trip_id)
    if trip is None or trip.closed_at is not None:
        raise ValueError("Esa compra no está abierta")
    trip.items.clear()
    for position, raw in enumerate(items):
        name = re.sub(r"\s+", " ", str(raw.get("name", ""))).strip()[:80]
        if name:
            trip.items.append(MarketItem(
                name=name, price=_decimal(raw.get("price"), Decimal(0)),
                qty=_decimal(raw.get("qty"), Decimal(1)), position=position,
            ))
    budget = _decimal(budget, Decimal(0))
    trip.budget = budget or None
    db.commit()
    return trip


def close_trip(db: Session, trip_id: int) -> MarketTrip:
    """Cierra la compra: la carga como gasto en Súper, guarda precios y tacha la lista de casa."""
    trip = db.get(MarketTrip, trip_id)
    if trip is None or trip.closed_at is not None:
        raise ValueError("Esa compra no está abierta")
    bought = [i for i in trip.items if i.price > 0]
    if not bought:
        raise ValueError("No hay productos con precio")
    tx = new_transaction(
        kind="expense", amount=trip.total, category="Súper",
        note=f"Mercado ({len(bought)} productos)", source="market",
    )
    db.add(tx)
    db.flush()
    trip.transaction_id, trip.closed_at = tx.id, now()
    for item in bought:
        db.add(PriceRecord(product=normalize(item.name), price=item.price, date=today()))
    names = {normalize(i.name) for i in bought}
    for home in db.scalars(select(HomeItem).where(HomeItem.done.is_(False))):
        if normalize(home.name) in names:
            home.done = True
    db.commit()
    return trip


def discard_trip(db: Session, trip_id: int) -> None:
    trip = db.get(MarketTrip, trip_id)
    if trip is not None and trip.closed_at is None:
        db.delete(trip)
        db.commit()


def recent_trips(db: Session, limit: int = 10) -> list[MarketTrip]:
    return list(db.scalars(
        select(MarketTrip).options(selectinload(MarketTrip.items))
        .where(MarketTrip.closed_at.is_not(None)).order_by(MarketTrip.closed_at.desc()).limit(limit)
    ))
