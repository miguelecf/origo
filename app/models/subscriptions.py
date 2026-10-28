import datetime as dt
from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="ARS")  # ARS | USD
    period: Mapped[str] = mapped_column(String(10), default="monthly")  # monthly | yearly
    category: Mapped[str] = mapped_column(String(40), default="Otros")
    next_charge: Mapped[dt.date] = mapped_column(index=True)
    # Con qué se paga: marca del catálogo (static/brands/<paid_with>.png) o nada.
    paid_with: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=now)
