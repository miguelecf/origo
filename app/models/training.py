import datetime as dt
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.database import Base


class Exercise(Base):
    """Catálogo propio: se llena solo con lo que se escribe en la rutina."""

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(80), unique=True)  # nombre normalizado
    created_at: Mapped[dt.datetime] = mapped_column(default=now)


class RoutineDay(Base):
    __tablename__ = "routine_days"

    weekday: Mapped[int] = mapped_column(primary_key=True)  # 0 = lunes
    title: Mapped[str] = mapped_column(String(80), default="")


class RoutineItem(Base):
    __tablename__ = "routine_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    weekday: Mapped[int] = mapped_column(index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"))
    sets: Mapped[int]
    reps: Mapped[int]
    kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    position: Mapped[int] = mapped_column(default=0)

    exercise: Mapped[Exercise] = relationship(lazy="joined")


class WorkoutLog(Base):
    """Lo que se hizo: un ejercicio marcado como hecho en una fecha."""

    __tablename__ = "workout_logs"
    __table_args__ = (UniqueConstraint("date", "routine_item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    routine_item_id: Mapped[int | None] = mapped_column(ForeignKey("routine_items.id", ondelete="SET NULL"))
    sets: Mapped[int]
    reps: Mapped[int]
    kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    created_at: Mapped[dt.datetime] = mapped_column(default=now)

    exercise: Mapped[Exercise] = relationship(lazy="joined")
