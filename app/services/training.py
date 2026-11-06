"""Entreno: rutina semanal, lo que toca hoy e historial de lo hecho."""
import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import today
from app.models import Exercise, RoutineDay, RoutineItem, WorkoutLog
from app.services.lists import normalize

WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MAX_ITEMS_PER_DAY = 40


# --- Catálogo ---

def exercise_for(db: Session, name: str) -> Exercise:
    """El ejercicio con ese nombre (sin importar mayúsculas ni espacios), o uno nuevo."""
    name = " ".join(name.split())[:80]
    if not name:
        raise ValueError("Escribí el nombre del ejercicio")
    key = normalize(name)
    exercise = db.scalar(select(Exercise).where(Exercise.key == key))
    if exercise is None:
        exercise = Exercise(name=name, key=key)
        db.add(exercise)
        db.flush()
    return exercise


def exercise_names(db: Session) -> list[str]:
    return list(db.scalars(select(Exercise.name).order_by(Exercise.name)))


# --- Rutina ---

def _weekday(value: int) -> int:
    if not isinstance(value, int) or not 0 <= value <= 6:
        raise ValueError("El día va de 0 (lunes) a 6 (domingo)")
    return value


def parse_reps(text: str | None) -> tuple[int | None, int | None]:
    """'10' → (10, None); '8-12', '8–12' u '8 a 12' → (8, 12). Lo que no se entiende, (None, None)."""
    raw = (text or "").strip().lower().replace("–", "-").replace("—", "-").replace(" a ", "-")
    parts = [p.strip() for p in raw.split("-")]
    if not 1 <= len(parts) <= 2 or not all(p.isdigit() for p in parts):
        return None, None
    low = int(parts[0])
    high = int(parts[1]) if len(parts) == 2 else None
    return low, (None if high == low else high)


def format_reps(reps: int, reps_max: int | None) -> str:
    return f"{reps}–{reps_max}" if reps_max else str(reps)


def _validate_dose(sets: int | None, reps: int | None, reps_max: int | None, kg: Decimal | None) -> None:
    if not sets or not 1 <= sets <= 50:
        raise ValueError("Poné cuántas series (de 1 a 50)")
    if not reps or not 1 <= reps <= 500:
        raise ValueError("Poné cuántas repeticiones (de 1 a 500)")
    if reps_max is not None and not reps < reps_max <= 500:
        raise ValueError("El rango de repeticiones va de menos a más, ej. 8–12")
    if kg is not None and (not Decimal(kg).is_finite() or not 0 <= kg <= 1000):
        raise ValueError("Los kilos van de 0 a 1000")


def add_item(
    db: Session, weekday: int, name: str, sets: int | None, reps: int | None, kg: Decimal | None = None,
    reps_max: int | None = None, allow_duplicate: bool = False,
) -> RoutineItem:
    weekday = _weekday(weekday)
    _validate_dose(sets, reps, reps_max, kg)
    exercise = exercise_for(db, name)
    items = _items(db, weekday)
    if not allow_duplicate and any(i.exercise_id == exercise.id for i in items):
        db.rollback()
        raise ValueError(f"{exercise.name} ya está el {WEEKDAYS[weekday].lower()}")
    if len(items) >= MAX_ITEMS_PER_DAY:
        db.rollback()
        raise ValueError(f"Un día admite hasta {MAX_ITEMS_PER_DAY} ejercicios")
    item = RoutineItem(weekday=weekday, exercise=exercise, sets=sets, reps=reps, reps_max=reps_max, kg=kg,
                       position=len(items))
    db.add(item)
    db.commit()
    return item


_KEEP = object()


def update_item(db: Session, item_id: int, sets=_KEEP, reps=_KEEP, reps_max=_KEEP, kg=_KEEP) -> RoutineItem:
    """Cambia la dosis de un ejercicio de la rutina; lo que no se pasa queda igual.
    reps_max=None o kg=None los borran. El historial ya registrado no cambia."""
    item = db.get(RoutineItem, item_id)
    if item is None:
        raise ValueError("Ese ejercicio ya no está en la rutina")
    new = {
        "sets": item.sets if sets is _KEEP else sets,
        "reps": item.reps if reps is _KEEP else reps,
        "reps_max": item.reps_max if reps_max is _KEEP else reps_max,
        "kg": item.kg if kg is _KEEP else kg,
    }
    _validate_dose(**new)
    for key, value in new.items():
        setattr(item, key, value)
    db.commit()
    return item


def _items(db: Session, weekday: int) -> list[RoutineItem]:
    return list(db.scalars(
        select(RoutineItem).where(RoutineItem.weekday == weekday).order_by(RoutineItem.position, RoutineItem.id)
    ))


def move_item(db: Session, item_id: int, step: int) -> None:
    """Sube (-1) o baja (+1) un ejercicio dentro de su día."""
    item = db.get(RoutineItem, item_id)
    if item is None:
        raise ValueError("Ese ejercicio ya no está en la rutina")
    items = _items(db, item.weekday)
    i = items.index(item)
    j = max(0, min(len(items) - 1, i + step))
    items.insert(j, items.pop(i))
    for position, each in enumerate(items):
        each.position = position
    db.commit()


def delete_item(db: Session, item_id: int) -> bool:
    """Saca el ejercicio de la rutina. Lo que ya se hizo queda en el historial.
    Reacomoda las posiciones del día. Devuelve si había algo para sacar."""
    item = db.get(RoutineItem, item_id)
    if item is None:
        return False
    weekday = item.weekday
    db.execute(update(WorkoutLog).where(WorkoutLog.routine_item_id == item_id).values(routine_item_id=None))
    db.delete(item)
    db.flush()
    for position, each in enumerate(_items(db, weekday)):
        each.position = position
    db.commit()
    return True


def set_title(db: Session, weekday: int, title: str) -> None:
    day = db.get(RoutineDay, _weekday(weekday)) or RoutineDay(weekday=weekday)
    day.title = " ".join(title.split())[:80]
    db.add(day)
    db.commit()


def day_plan(db: Session, weekday: int) -> dict:
    day = db.get(RoutineDay, weekday)
    return {"weekday": weekday, "name": WEEKDAYS[weekday], "title": day.title if day else "", "items": _items(db, weekday)}


def week(db: Session) -> list[dict]:
    return [day_plan(db, weekday) for weekday in range(7)]


def next_training_day(db: Session, after: dt.date) -> tuple[dt.date, dict] | None:
    """El próximo día con ejercicios después de `after`."""
    for offset in range(1, 8):
        day = after + dt.timedelta(days=offset)
        plan = day_plan(db, day.weekday())
        if plan["items"]:
            return day, plan
    return None


# --- Hoy e historial ---

def done_ids(db: Session, day: dt.date) -> set[int]:
    return set(db.scalars(select(WorkoutLog.routine_item_id).where(WorkoutLog.date == day, WorkoutLog.routine_item_id.is_not(None))))


def toggle_done(db: Session, item_id: int, on: dt.date | None = None) -> bool:
    """Marca o desmarca un ejercicio de la rutina como hecho ese día. Devuelve si quedó hecho."""
    item = db.get(RoutineItem, item_id)
    if item is None:
        raise ValueError("Ese ejercicio ya no está en la rutina")
    day = on or today()
    log = db.scalar(select(WorkoutLog).where(WorkoutLog.date == day, WorkoutLog.routine_item_id == item_id))
    if log:
        db.delete(log)
    else:
        db.add(WorkoutLog(date=day, exercise_id=item.exercise_id, routine_item_id=item.id,
                          sets=item.sets, reps=item.reps, reps_max=item.reps_max, kg=item.kg))
    db.commit()
    return log is None


def last_done(db: Session, exercise_ids: list[int], before: dt.date) -> dict[int, WorkoutLog]:
    """La última vez que se hizo cada ejercicio antes de `before`."""
    last = {}
    for log in db.scalars(
        select(WorkoutLog).where(WorkoutLog.exercise_id.in_(exercise_ids), WorkoutLog.date < before)
        .order_by(WorkoutLog.date.desc(), WorkoutLog.id.desc())
    ):
        last.setdefault(log.exercise_id, log)
    return last


def history(db: Session, days: int = 30, until: dt.date | None = None) -> list[tuple[dt.date, list[WorkoutLog]]]:
    """Sesiones de los últimos `days` días, de la más nueva a la más vieja."""
    end = until or today()
    logs = db.scalars(
        select(WorkoutLog).where(WorkoutLog.date > end - dt.timedelta(days=days), WorkoutLog.date <= end)
        .order_by(WorkoutLog.date.desc(), WorkoutLog.id)
    )
    sessions: dict[dt.date, list[WorkoutLog]] = {}
    for log in logs:
        sessions.setdefault(log.date, []).append(log)
    return list(sessions.items())


def today_summary(db: Session, day: dt.date | None = None) -> dict:
    day = day or today()
    plan = day_plan(db, day.weekday())
    done = done_ids(db, day)
    return {**plan, "done": len([i for i in plan["items"] if i.id in done]), "total": len(plan["items"])}
