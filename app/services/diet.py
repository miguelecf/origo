"""Plan de comidas: qué toca en cada momento del día, y los objetivos diarios del plan.

Los objetivos (kcal, macros, reglas, suplementos) los escribe quien arma el plan, por ejemplo el
agente. Origo los guarda y los muestra: no los calcula ni los ajusta, y no son comidas consumidas."""
import datetime as dt
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import DietTargets, MealPlan

# (clave, nombre, emoji, desde qué hora toca)
SLOTS = [
    ("desayuno", "Desayuno", "🥣", dt.time(5, 0)),
    ("media_manana", "Media mañana", "🍎", dt.time(10, 0)),
    ("almuerzo", "Almuerzo", "🍽️", dt.time(12, 0)),
    ("merienda", "Merienda", "🧉", dt.time(16, 0)),
    ("cena", "Cena", "🌙", dt.time(20, 0)),
]
SLOT_KEYS = [key for key, *_ in SLOTS]
MAX_TEXT = 2000


def plan(db: Session) -> list[dict]:
    """Los cinco momentos en orden, con su texto y sus líneas."""
    texts = {row.slot: row.text for row in db.scalars(select(MealPlan))}
    return [
        {"key": key, "name": name, "emoji": emoji, "from": start, "text": texts.get(key, ""),
         "lines": [line.strip() for line in texts.get(key, "").splitlines() if line.strip()]}
        for key, name, emoji, start in SLOTS
    ]


def save(db: Session, slot: str, text: str) -> str:
    """Reemplaza el texto de un momento. Devuelve el texto anterior, para poder deshacer."""
    if slot not in SLOT_KEYS:
        raise ValueError("Ese momento del día no existe")
    text = text.strip()
    if len(text) > MAX_TEXT:
        raise ValueError(f"El texto de un momento admite hasta {MAX_TEXT} caracteres")
    row = db.get(MealPlan, slot) or MealPlan(slot=slot, text="")
    previous = row.text or ""
    row.text = text
    db.add(row)
    db.commit()
    return previous


def append(db: Session, slot: str, lines: str) -> str:
    """Suma renglones al final de un momento sin tocar lo que ya había (los repetidos no se duplican).
    Devuelve el texto anterior."""
    if slot not in SLOT_KEYS:
        raise ValueError("Ese momento del día no existe")
    row = db.get(MealPlan, slot)
    current = (row.text if row else "") or ""
    have = {fold(line.strip()) for line in current.splitlines() if line.strip()}
    new = []
    for line in lines.splitlines():
        line = line.strip()
        if line and fold(line) not in have:
            have.add(fold(line))
            new.append(line)
    return save(db, slot, "\n".join([current.rstrip(), *new]) if current.strip() else "\n".join(new))


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
    """Los momentos con alguna línea que contenga todas las palabras buscadas."""
    words = fold(query).split()
    if not words:
        return []
    found = []
    for slot in plan(db):
        lines = [line for line in slot["lines"] if all(w in fold(line) for w in words)]
        if lines:
            found.append({**slot, "lines": lines})
    return found
