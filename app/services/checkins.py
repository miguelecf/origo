import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import week_start
from app.models import Checkin, WeeklyReview


def get_checkin(db: Session, day: dt.date) -> Checkin | None:
    return db.scalar(select(Checkin).where(Checkin.date == day))


def save_checkin(
    db: Session, day: dt.date, *, sleep_hours: Decimal | None = None, mood: int | None = None,
    movement_min: int | None = None, note: str = "",
) -> Checkin:
    if mood is not None and not 1 <= mood <= 5:
        raise ValueError("El ánimo va de 1 a 5")
    checkin = get_checkin(db, day) or Checkin(date=day)
    checkin.sleep_hours, checkin.mood, checkin.movement_min = sleep_hours, mood, movement_min
    checkin.note = note.strip()
    db.add(checkin)
    db.commit()
    return checkin


def list_checkins(db: Session, start: dt.date, end: dt.date) -> list[Checkin]:
    return list(db.scalars(
        select(Checkin).where(Checkin.date >= start, Checkin.date < end).order_by(Checkin.date)
    ))


def _avg(values: list) -> Decimal | None:
    values = [Decimal(v) for v in values if v is not None]
    return (sum(values) / len(values)).quantize(Decimal("0.1")) if values else None


def averages(db: Session, start: dt.date, end: dt.date) -> dict:
    checkins = list_checkins(db, start, end)
    return {
        "days": len(checkins),
        "sleep_hours": _avg([c.sleep_hours for c in checkins]),
        "mood": _avg([c.mood for c in checkins]),
        "movement_min": _avg([c.movement_min for c in checkins]),
    }


def get_review(db: Session, day: dt.date) -> WeeklyReview | None:
    return db.scalar(select(WeeklyReview).where(WeeklyReview.week_start == week_start(day)))


def save_review(db: Session, day: dt.date, went_well: str, change: str) -> WeeklyReview:
    review = get_review(db, day) or WeeklyReview(week_start=week_start(day))
    review.went_well, review.change = went_well.strip(), change.strip()
    db.add(review)
    db.commit()
    return review


def list_reviews(db: Session, start: dt.date, end: dt.date) -> list[WeeklyReview]:
    return list(db.scalars(
        select(WeeklyReview)
        .where(WeeklyReview.week_start >= week_start(start), WeeklyReview.week_start < end)
        .order_by(WeeklyReview.week_start)
    ))
