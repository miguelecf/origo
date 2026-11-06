from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MealPlan(Base):
    """El plan de comidas: un texto libre por momento del día, igual todos los días."""

    __tablename__ = "meal_plan"

    slot: Mapped[str] = mapped_column(String(20), primary_key=True)  # desayuno | media_manana | ...
    text: Mapped[str] = mapped_column(Text, default="")


class DietTargets(Base):
    """Objetivos diarios, reglas y suplementos del plan. Una sola fila (id=1).
    Son lo que dice el plan, no lo que se comió: las comidas van en FoodEntry."""

    __tablename__ = "diet_targets"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    kcal: Mapped[int | None] = mapped_column(default=None)
    protein_g: Mapped[int | None] = mapped_column(default=None)
    carbs_g: Mapped[int | None] = mapped_column(default=None)
    fat_g: Mapped[int | None] = mapped_column(default=None)
    rules: Mapped[str] = mapped_column(Text, default="")
    supplements: Mapped[str] = mapped_column(Text, default="")
