from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MealPlan(Base):
    """Plan viejo (hasta 0.2): un texto por momento, igual todos los días. Ya no se escribe:
    se copia una vez a MealPlanDay y queda intacto para poder volver a una versión anterior."""

    __tablename__ = "meal_plan"

    slot: Mapped[str] = mapped_column(String(20), primary_key=True)  # desayuno | media_manana | ...
    text: Mapped[str] = mapped_column(Text, default="")


class MealPlanDay(Base):
    """El plan de comidas: una comida por momento del día, para cada día de la semana.
    Una celda vacía se guarda con text="" (no se borra la fila)."""

    __tablename__ = "meal_plan_days"

    weekday: Mapped[int] = mapped_column(primary_key=True)  # 0 = lunes ... 6 = domingo
    slot: Mapped[str] = mapped_column(String(20), primary_key=True)
    text: Mapped[str] = mapped_column(String(200), default="")


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
