import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.clock import today, week_start
from app.core.database import get_db
from app.services import checkins
from app.web.forms import parse_amount, parse_date, parse_int
from app.web.templates import render

router = APIRouter(prefix="/dia")


@router.get("")
def checkin_page(request: Request, fecha: str | None = None, db: Session = Depends(get_db)):
    day = parse_date(fecha) or today()
    last_week = checkins.list_checkins(db, day - dt.timedelta(days=13), day + dt.timedelta(days=1))
    return render(
        request, "pages/checkin.html",
        day=day, checkin=checkins.get_checkin(db, day), recent=last_week[::-1],
        review=checkins.get_review(db, day), week=week_start(day),
        averages=checkins.averages(db, day - dt.timedelta(days=6), day + dt.timedelta(days=1)),
        saved=request.query_params.get("ok"), today=today(),
    )


@router.post("")
def save(
    date: str = Form(""), sleep_hours: str = Form(""), mood: str = Form(""),
    movement_min: str = Form(""), note: str = Form(""), db: Session = Depends(get_db),
):
    day = parse_date(date) or today()
    mood_value = parse_int(mood)
    checkins.save_checkin(
        db, day, sleep_hours=parse_amount(sleep_hours),
        mood=mood_value if mood_value and 1 <= mood_value <= 5 else None,
        movement_min=parse_int(movement_min), note=note,
    )
    return RedirectResponse(f"/dia?fecha={day}&ok=1", status_code=303)


@router.post("/semana")
def save_review(date: str = Form(""), went_well: str = Form(""), change: str = Form(""), db: Session = Depends(get_db)):
    day = parse_date(date) or today()
    checkins.save_review(db, day, went_well, change)
    return RedirectResponse(f"/dia?fecha={day}&ok=1", status_code=303)
