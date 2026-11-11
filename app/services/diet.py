"""Plan de comidas: qué toca comer en cada momento de cada día de la semana, y los objetivos del plan.

Formato estricto: para cada día (0 = lunes ... 6 = domingo) y cada momento hay UNA comida, en un
renglón corto. Si el plan da opciones, va la que se elige para ese día. El plan es fijo por día de
la semana y no rota solo.

Los objetivos (kcal, macros, reglas, suplementos) los escribe quien arma el plan, por ejemplo el
agente. Origo los guarda y los muestra: no los calcula ni los ajusta, y no son comidas consumidas."""
import datetime as dt
import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.models import DietTargets, MealPlan, MealPlanDay
from app.services.training import WEEKDAYS

# (clave, nombre, emoji, desde qué hora toca)
SLOTS = [
    ("desayuno", "Desayuno", "🥣", dt.time(5, 0)),
    ("media_manana", "Media mañana", "🍎", dt.time(10, 0)),
    ("almuerzo", "Almuerzo", "🍽️", dt.time(12, 0)),
    ("merienda", "Merienda", "🧉", dt.time(16, 0)),
    ("cena", "Cena", "🌙", dt.time(20, 0)),
]
SLOT_KEYS = [key for key, *_ in SLOTS]
MAX_MEAL = 200
MAX_TEXT = 2000  # reglas y suplementos de los objetivos

FORMAT = (
    "Una comida por momento y por día de la semana (weekday 0 = lunes ... 6 = domingo; "
    f"slot: {', '.join(SLOT_KEYS)}). Cada comida es un solo renglón de hasta {MAX_MEAL} caracteres, "
    "con cantidades si el plan las tiene (ej. '200 g de pollo con arroz y ensalada'). Sin listas de "
    "opciones: si el plan da opciones, cargá la elegida para ese día. Un momento sin comida queda vacío. "
    "El plan es fijo por día de la semana y no rota solo. Es el plan, no lo comido."
)


def _check_day(weekday) -> int:
    if not isinstance(weekday, int) or isinstance(weekday, bool) or not 0 <= weekday <= 6:
        raise ValueError("El día va de 0 (lunes) a 6 (domingo)")
    return weekday


def _check_slot(slot: str) -> str:
    if slot not in SLOT_KEYS:
        raise ValueError(f"Ese momento del día no existe. Opciones: {', '.join(SLOT_KEYS)}")
    return slot


def _migrate_legacy(db: Session) -> None:
    """Una sola vez: el plan viejo (igual todos los días) se copia a los siete días.
    Las opciones que eran varios renglones quedan unidas con ' / ' para no perder nada.
    Las celdas vacías se guardan como filas con text="", así esto no vuelve a correr."""
    if db.scalar(select(func.count()).select_from(MealPlanDay)):
        return
    legacy = {row.slot: row.text for row in db.scalars(select(MealPlan)) if (row.text or "").strip()}
    if not legacy:
        return
    for weekday in range(7):
        for slot in SLOT_KEYS:
            lines = [line.strip() for line in legacy.get(slot, "").splitlines() if line.strip()]
            db.add(MealPlanDay(weekday=weekday, slot=slot, text=" / ".join(lines)))
    db.commit()


def _cells(db: Session) -> dict[tuple[int, str], str]:
    _migrate_legacy(db)
    return {(row.weekday, row.slot): row.text for row in db.scalars(select(MealPlanDay))}


def _day(cells: dict, weekday: int) -> list[dict]:
    meals = []
    for key, name, emoji, start in SLOTS:
        text = cells.get((weekday, key), "")
        meals.append({"key": key, "name": name, "emoji": emoji, "from": start, "text": text,
                      "lines": [text] if text else []})
    return meals


def plan(db: Session, weekday: int | None = None) -> list[dict]:
    """Los momentos de un día en orden (por defecto, hoy), con su comida."""
    return _day(_cells(db), today().weekday() if weekday is None else _check_day(weekday))


def week(db: Session) -> list[dict]:
    cells = _cells(db)
    return [{"weekday": d, "name": WEEKDAYS[d], "meals": _day(cells, d)} for d in range(7)]


def clean_meal(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) > MAX_MEAL:
        raise ValueError(f"Una comida admite hasta {MAX_MEAL} caracteres, en un solo renglón")
    return text


def set_meal(db: Session, slot: str, text: str, weekdays: list[int]) -> dict[int, str]:
    """Pone la misma comida en ese momento de los días pedidos. Texto vacío = vaciar.
    Devuelve lo que había en cada día, para poder deshacer."""
    _check_slot(slot)
    if isinstance(text, str) and "\n" in text.strip():
        raise ValueError("Una comida va en un solo renglón: sin listas ni opciones")
    text = clean_meal(text)
    days = sorted({_check_day(d) for d in weekdays or []})
    if not days:
        raise ValueError("Elegí al menos un día")
    cells = _cells(db)
    previous = {}
    for weekday in days:
        previous[weekday] = cells.get((weekday, slot), "")
        row = db.get(MealPlanDay, (weekday, slot)) or MealPlanDay(weekday=weekday, slot=slot)
        row.text = text
        db.add(row)
    db.commit()
    return previous


def clear_meal(db: Session, slot: str, weekdays: list[int]) -> dict[int, str]:
    return set_meal(db, slot, "", weekdays)


def copy_day(db: Session, source: int, targets: list[int]) -> None:
    """Copia el día entero (todos los momentos) a otros días."""
    meals = plan(db, source)
    days = sorted({_check_day(d) for d in targets or []} - {source})
    if not days:
        raise ValueError("Elegí al menos otro día")
    for meal in meals:
        for weekday in days:
            row = db.get(MealPlanDay, (weekday, meal["key"])) or MealPlanDay(weekday=weekday, slot=meal["key"])
            row.text = meal["text"]
            db.add(row)
    db.commit()


# --- Objetivos del plan ---

TARGET_NUMBERS = {"kcal": 10000, "protein_g": 1000, "carbs_g": 2000, "fat_g": 1000}
TARGET_TEXTS = ("rules", "supplements")
_KEEP = object()


def targets(db: Session) -> DietTargets:
    return db.get(DietTargets, 1) or DietTargets(id=1, rules="", supplements="")


def set_targets(db: Session, **values) -> DietTargets:
    """Cambia solo lo que se pasa. None borra un número; "" borra un texto."""
    unknown = set(values) - set(TARGET_NUMBERS) - set(TARGET_TEXTS)
    if unknown:
        raise ValueError(f"Campo desconocido: {', '.join(sorted(unknown))}")
    row = targets(db)
    for field, value in values.items():
        if field in TARGET_NUMBERS:
            if value is not None and (not isinstance(value, int) or not 0 <= value <= TARGET_NUMBERS[field]):
                raise ValueError(f"{field} va de 0 a {TARGET_NUMBERS[field]}")
        else:
            value = (value or "").strip()
            if len(value) > MAX_TEXT:
                raise ValueError(f"{field} admite hasta {MAX_TEXT} caracteres")
        setattr(row, field, value)
    db.add(row)
    db.commit()
    return row


def targets_lines(row: DietTargets) -> dict:
    split = lambda text: [line.strip() for line in (text or "").splitlines() if line.strip()]
    return {"rules": split(row.rules), "supplements": split(row.supplements)}


def current_slot(at: dt.datetime | None = None) -> str:
    """El momento que toca a esa hora; de madrugada sigue la cena."""
    moment = (at or now()).time()
    current = "cena"
    for key, _, _, start in SLOTS:
        if moment >= start:
            current = key
    return current


def fold(text: str) -> str:
    """Minúsculas y sin acentos, para buscar 'platano' y encontrar 'Plátano'."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def search(db: Session, query: str) -> list[dict]:
    """Las comidas de la semana que contienen todas las palabras buscadas, por día."""
    words = fold(query).split()
    if not words:
        return []
    found = []
    for day in week(db):
        meals = [m for m in day["meals"] if m["text"] and all(w in fold(m["text"]) for w in words)]
        if meals:
            found.append({**day, "meals": meals})
    return found
