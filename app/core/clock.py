import datetime as dt
from zoneinfo import ZoneInfo

from app.core.config import settings


def now() -> dt.datetime:
    """Hora local sin tzinfo; así se guarda en SQLite."""
    return dt.datetime.now(ZoneInfo(settings.TIMEZONE)).replace(tzinfo=None, microsecond=0)


def today() -> dt.date:
    return now().date()


def month_bounds(day: dt.date) -> tuple[dt.date, dt.date]:
    """Primer día del mes y primer día del mes siguiente (exclusivo)."""
    first = day.replace(day=1)
    return first, add_months(first, 1)


def add_months(day: dt.date, months: int) -> dt.date:
    """Suma meses recortando al último día cuando no existe (31 ene + 1 = 28/29 feb)."""
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    last_day = (dt.date(year + month // 12, month % 12 + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(year, month, min(day.day, last_day))


def week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())
