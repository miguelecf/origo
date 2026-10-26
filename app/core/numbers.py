import re
from decimal import Decimal, InvalidOperation


def parse_amount(text, *, thousands: bool = True) -> Decimal | None:
    """Números como se escriben acá: '12.500' y '12.500,50' son miles; '12500.5' y '0,5' decimales.
    Con thousands=False (cantidades), '0.500' es medio."""
    if text is None or text == "":
        return None
    text = re.sub(r"[^\d.,-]", "", str(text))
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif thousands and (text.count(".") > 1 or re.fullmatch(r"-?[1-9]\d{0,2}\.\d{3}", text)):
        text = text.replace(".", "")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None
