import datetime as dt
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.database import Base


class HomeItem(Base):
    """Lista de compras de la casa (lo que falta)."""

    __tablename__ = "home_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    done: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=now)


class MarketTrip(Base):
    """Una ida al súper. Abierta mientras closed_at es None."""

    __tablename__ = "market_trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=now)
    closed_at: Mapped[dt.datetime | None]
    budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # None = la hice yo. Si la hizo un invitado, no se carga sola como gasto mío.
    guest_id: Mapped[int | None] = mapped_column(ForeignKey("guests.id"), index=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"))
    # Compra dividida: con quién y qué % de lo compartido pongo yo por defecto. Su parte queda
    # como deuda (me debe) al cerrar. Solo en compras mías.
    split_with: Mapped[str | None] = mapped_column(String(80))
    split_pct: Mapped[int | None]
    debt_id: Mapped[int | None] = mapped_column(ForeignKey("debts.id", ondelete="SET NULL"))

    items: Mapped[list["MarketItem"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="MarketItem.position"
    )
    guest: Mapped["Guest | None"] = relationship()  # noqa: F821

    @property
    def total(self) -> Decimal:
        return sum((item.subtotal for item in self.items), Decimal(0))

    @property
    def my_total(self) -> Decimal:
        """Mi parte. Sin dividir, es todo."""
        if not self.split_with:
            return self.total
        return sum((item.my_part for item in self.items), Decimal(0))

    @property
    def their_total(self) -> Decimal:
        return self.total - self.my_total


class MarketItem(Base):
    __tablename__ = "market_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("market_trips.id"), index=True)
    name: Mapped[str] = mapped_column(String(80), default="")  # vacío = solo precio
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    qty: Mapped[Decimal] = mapped_column(Numeric(8, 3), default=1)
    position: Mapped[int] = mapped_column(default=0)
    # Qué % pongo yo (0 a 100). None = todo mío. Solo cuenta si la compra está dividida.
    my_pct: Mapped[int | None]

    trip: Mapped[MarketTrip] = relationship(back_populates="items")

    @property
    def subtotal(self) -> Decimal:
        return (self.price * self.qty).quantize(Decimal("0.01"))

    @property
    def my_part(self) -> Decimal:
        pct = 100 if self.my_pct is None else self.my_pct
        return (self.subtotal * pct / 100).quantize(Decimal("0.01"))


class PriceRecord(Base):
    """Precio pagado por un producto en una compra. Sirve para autocompletar y ver cuánto sube."""

    __tablename__ = "price_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    product: Mapped[str] = mapped_column(String(80), index=True)  # nombre normalizado
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    date: Mapped[dt.date]
