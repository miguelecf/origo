import datetime as dt
from decimal import Decimal

from sqlalchemy import Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(unique=True)
    sleep_hours: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    mood: Mapped[int | None]  # 1 a 5
    movement_min: Mapped[int | None]
    note: Mapped[str] = mapped_column(String(300), default="")


class WeeklyReview(Base):
    __tablename__ = "weekly_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_start: Mapped[dt.date] = mapped_column(unique=True)
    went_well: Mapped[str] = mapped_column(Text, default="")
    change: Mapped[str] = mapped_column(Text, default="")
