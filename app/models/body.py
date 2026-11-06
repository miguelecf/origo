import datetime as dt
from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.database import Base


class Weight(Base):
    __tablename__ = "weights"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(unique=True)
    kg: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Lo que da una balanza de bioimpedancia. Todo opcional: son lecturas, no diagnósticos.
    fat_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    muscle_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    lean_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    water_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    visceral_fat: Mapped[int | None] = mapped_column(default=None)


class FoodEntry(Base):
    __tablename__ = "food_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(default=now, index=True)
    text: Mapped[str] = mapped_column(String(300))


class WeightMilestone(Base):
    """Hitos intermedios hacia la meta final. No reemplazan la meta (que vive en Setting)."""

    __tablename__ = "weight_milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    kg: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    note: Mapped[str] = mapped_column(String(120), default="")
    reached_on: Mapped[dt.date | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=now)


class Setting(Base):
    """Valores sueltos (por ahora, el peso objetivo)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
