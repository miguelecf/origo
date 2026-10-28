from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MealPlan(Base):
    """El plan de comidas: un texto libre por momento del día, igual todos los días."""

    __tablename__ = "meal_plan"

    slot: Mapped[str] = mapped_column(String(20), primary_key=True)  # desayuno | media_manana | ...
    text: Mapped[str] = mapped_column(Text, default="")
