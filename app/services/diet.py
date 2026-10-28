"""Plan de comidas: qué toca en cada momento del día, para ver y recordar. Sin gramos ni calorías."""
import datetime as dt
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import MealPlan

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


def save(db: Session, slot: str, text: str) -> None:
    if slot not in SLOT_KEYS:
        raise ValueError("Ese momento del día no existe")
    row = db.get(MealPlan, slot) or MealPlan(slot=slot)
    row.text = text.strip()[:MAX_TEXT]
    db.add(row)
    db.commit()


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
