import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.models import FoodEntry, Setting, Weight, WeightMilestone

GOAL_KEY = "weight_goal"


# Campo → (mínimo, máximo) que acepta. Lecturas de balanza, no diagnósticos.
COMPOSITION = {
    "fat_pct": (Decimal(1), Decimal(75)),
    "muscle_pct": (Decimal(5), Decimal(95)),
    "lean_kg": (Decimal(10), Decimal(300)),
    "water_pct": (Decimal(20), Decimal(85)),
    "visceral_fat": (1, 59),
}


def _check_kg(kg: Decimal) -> Decimal:
    kg = Decimal(kg)
    if not kg.is_finite() or not 20 <= kg <= 400:
        raise ValueError("El peso va de 20 a 400 kg")
    return kg


def log_weight(db: Session, kg: Decimal, on: dt.date | None = None, **composition) -> Weight:
    """Un registro por día: si ya había uno, reemplaza el peso. De la composición
    (fat_pct, muscle_pct, lean_kg, water_pct, visceral_fat) solo cambia lo que se pasa:
    lo que no viene conserva el valor que ya tenía ese día."""
    unknown = set(composition) - set(COMPOSITION)
    if unknown:
        raise ValueError(f"Campo desconocido: {', '.join(sorted(unknown))}")
    for field, value in composition.items():
        low, high = COMPOSITION[field]
        if value is not None and not low <= value <= high:
            raise ValueError(f"{field} va de {low} a {high}")
    on = on or today()
    weight = db.scalar(select(Weight).where(Weight.date == on)) or Weight(date=on)
    weight.kg = _check_kg(kg)
    for field, value in composition.items():
        if value is not None:
            setattr(weight, field, value)
    db.add(weight)
    db.commit()
    return weight


def latest_composition(series: list[Weight]) -> Weight | None:
    """El último registro con algún dato de composición."""
    return next((w for w in reversed(series) if any(getattr(w, f) is not None for f in COMPOSITION)), None)


def delete_weight(db: Session, weight_id: int) -> None:
    if weight := db.get(Weight, weight_id):
        db.delete(weight)
        db.commit()


def weight_series(db: Session, start: dt.date | None = None, end: dt.date | None = None) -> list[Weight]:
    q = select(Weight).order_by(Weight.date)
    if start:
        q = q.where(Weight.date >= start)
    if end:
        q = q.where(Weight.date < end)
    return list(db.scalars(q))


def get_goal(db: Session) -> Decimal | None:
    setting = db.get(Setting, GOAL_KEY)
    return Decimal(setting.value) if setting else None


def set_goal(db: Session, kg: Decimal | None) -> None:
    setting = db.get(Setting, GOAL_KEY)
    if kg is None:
        if setting:
            db.delete(setting)
    elif setting:
        setting.value = str(kg)
    else:
        db.add(Setting(key=GOAL_KEY, value=str(kg)))
    db.commit()


# --- Hitos: escalones intermedios. Nunca tocan la meta final. ---

def milestones(db: Session) -> list[WeightMilestone]:
    return list(db.scalars(select(WeightMilestone).order_by(WeightMilestone.kg.desc(), WeightMilestone.id)))


def add_milestone(db: Session, kg: Decimal, note: str = "") -> WeightMilestone:
    kg = _check_kg(kg)
    if db.scalar(select(WeightMilestone).where(WeightMilestone.kg == kg)):
        raise ValueError(f"Ya hay un hito en {kg} kg")
    milestone = WeightMilestone(kg=kg, note=" ".join(note.split())[:120])
    db.add(milestone)
    db.commit()
    return milestone


def delete_milestone(db: Session, milestone_id: int) -> bool:
    milestone = db.get(WeightMilestone, milestone_id)
    if milestone is None:
        return False
    db.delete(milestone)
    db.commit()
    return True


def next_milestone(db: Session, current: Decimal | None) -> WeightMilestone | None:
    """El hito más cercano que todavía no se alcanzó, en el sentido de la meta
    (bajando si la meta está debajo del peso actual, subiendo si está arriba)."""
    if current is None:
        return None
    goal = get_goal(db)
    going_down = goal is None or goal < current
    pending = [m for m in milestones(db) if (m.kg < current if going_down else m.kg > current)]
    if not pending:
        return None
    return max(pending, key=lambda m: m.kg) if going_down else min(pending, key=lambda m: m.kg)


def weight_summary(db: Session) -> dict:
    """Punto de partida, hoy, hace 30 días, meta, próximo hito y última composición."""
    series = weight_series(db)
    month_ago = today() - dt.timedelta(days=30)
    previous = [w for w in series if w.date <= month_ago]
    current = series[-1] if series else None
    return {
        "start": series[0] if series else None,
        "current": current,
        "month_ago": previous[-1] if previous else None,
        "goal": get_goal(db),
        "next_milestone": next_milestone(db, current.kg if current else None),
        "composition": latest_composition(series),
    }


def log_food(db: Session, text: str, at: dt.datetime | None = None) -> FoodEntry:
    text = text.strip()
    if not text:
        raise ValueError("Escribí qué comiste")
    entry = FoodEntry(text=text, at=at or now())
    db.add(entry)
    db.commit()
    return entry


def delete_food(db: Session, entry_id: int) -> None:
    if entry := db.get(FoodEntry, entry_id):
        db.delete(entry)
        db.commit()


def food_log(db: Session, start: dt.date, end: dt.date) -> list[FoodEntry]:
    """Comidas con start <= día < end, en orden cronológico."""
    return list(db.scalars(
        select(FoodEntry)
        .where(FoodEntry.at >= dt.datetime.combine(start, dt.time()), FoodEntry.at < dt.datetime.combine(end, dt.time()))
        .order_by(FoodEntry.at)
    ))
