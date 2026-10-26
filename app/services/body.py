import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.models import FoodEntry, Setting, Weight

GOAL_KEY = "weight_goal"


def log_weight(db: Session, kg: Decimal, on: dt.date | None = None) -> Weight:
    """Un registro por día: si ya había uno, lo reemplaza."""
    on = on or today()
    weight = db.scalar(select(Weight).where(Weight.date == on)) or Weight(date=on)
    weight.kg = Decimal(kg)
    db.add(weight)
    db.commit()
    return weight


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


def weight_summary(db: Session) -> dict:
    """Punto de partida, hoy, hace 30 días y meta."""
    series = weight_series(db)
    month_ago = today() - dt.timedelta(days=30)
    previous = [w for w in series if w.date <= month_ago]
    return {
        "start": series[0] if series else None,
        "current": series[-1] if series else None,
        "month_ago": previous[-1] if previous else None,
        "goal": get_goal(db),
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
