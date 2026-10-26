import datetime as dt

from app.core.numbers import parse_amount

__all__ = ["parse_amount", "parse_date", "parse_int"]


def parse_int(text: str | None) -> int | None:
    value = parse_amount(text)
    return int(value) if value is not None else None


def parse_date(text: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text) if text else None
    except ValueError:
        return None
