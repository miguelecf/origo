import datetime as dt
import re
from decimal import Decimal, InvalidOperation


def parse_amount(text: str | None) -> Decimal | None:
    """Acepta '12500', '12.500', '12.500,50', '12500.5', '$ 1.200'."""
    if not text:
        return None
    text = re.sub(r"[^\d.,-]", "", text)
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1 or re.fullmatch(r"-?\d{1,3}\.\d{3}", text):
        text = text.replace(".", "")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def parse_int(text: str | None) -> int | None:
    value = parse_amount(text)
    return int(value) if value is not None else None


def parse_date(text: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text) if text else None
    except ValueError:
        return None
