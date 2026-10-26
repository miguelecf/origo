import datetime as dt
from decimal import Decimal
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.core.clock import today
from app.core.config import settings

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

WEEKDAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def money(value) -> str:
    """12345.5 -> '$ 12.345,50'; sin decimales si son cero."""
    if value is None:
        return "—"
    value = Decimal(value)
    sign = "-" if value < 0 else ""
    text = f"{abs(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{sign}$ {text.removesuffix(',00')}"


def number(value, places: int = 1) -> str:
    if value is None:
        return "—"
    return f"{Decimal(value):.{places}f}".replace(".", ",").removesuffix("," + "0" * places)


def short_date(value: dt.date | dt.datetime) -> str:
    day = value.date() if isinstance(value, dt.datetime) else value
    if day == today():
        return "hoy"
    if day == today() - dt.timedelta(days=1):
        return "ayer"
    return f"{WEEKDAYS[day.weekday()]} {day.day}/{day.month}"


def join_y(values) -> str:
    """[2, 3, 4] -> '2, 3 y 4'."""
    values = [str(v) for v in values]
    return " y ".join([", ".join(values[:-1]), values[-1]]) if len(values) > 1 else "".join(values)


templates.env.filters.update(money=money, number=number, short_date=short_date, join_y=join_y)
templates.env.globals.update(app_name=settings.APP_NAME, owner_name=settings.OWNER_NAME, MONTHS=MONTHS)


def render(request: Request, name: str, **context):
    viewer = getattr(request.state, "viewer", None)
    return templates.TemplateResponse(request, name, {"active": request.url.path, "viewer": viewer, **context})
