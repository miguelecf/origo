import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import month_bounds, today
from app.models import FoodEntry, HomeItem
from app.services import body, checkins, debts, finance, lists


def overview(db: Session, start: dt.date | None = None, end: dt.date | None = None) -> dict:
    """Todo junto: lo usa la pantalla de inicio y el MCP. Por defecto, el mes en curso."""
    day = today()
    if start is None or end is None:
        start, end = month_bounds(day)
    week_ahead = day + dt.timedelta(days=7)
    return {
        "period": (start, end),
        "finance": finance.summary(db, start, end),
        "debts": {
            **debts.balances(db),
            "due_soon": debts.due_until(db, week_ahead),
            "card_alerts": debts.card_alerts(db, week_ahead),
        },
        "weight": body.weight_summary(db),
        "last_7_days": checkins.averages(db, day - dt.timedelta(days=6), day + dt.timedelta(days=1)),
        "today": {
            "checkin": checkins.get_checkin(db, day),
            "meals": db.scalar(
                select(func.count(FoodEntry.id)).where(FoodEntry.at >= dt.datetime.combine(day, dt.time()))
            ),
        },
        "home_pending": db.scalar(select(func.count(HomeItem.id)).where(HomeItem.done.is_(False))),
        "open_trip": lists.open_trip(db),
    }
