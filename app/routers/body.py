import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.database import get_db
from app.services import body
from app.web.forms import parse_amount, parse_date
from app.web.templates import render

router = APIRouter(prefix="/cuerpo")


@router.get("")
def body_page(request: Request, db: Session = Depends(get_db)):
    day = today()
    series = body.weight_series(db)
    meals = body.food_log(db, day - dt.timedelta(days=6), day + dt.timedelta(days=1))
    meals_by_day: dict[dt.date, list] = {}
    for entry in reversed(meals):
        meals_by_day.setdefault(entry.at.date(), []).append(entry)
    return render(
        request, "pages/body.html",
        summary=body.weight_summary(db), series=series[-30:][::-1],
        chart={"labels": [w.date.isoformat() for w in series], "values": [float(w.kg) for w in series]},
        meals_by_day=meals_by_day, today=day,
    )


@router.post("/comida")
def add_food(text: str = Form(""), db: Session = Depends(get_db)):
    if text.strip():
        body.log_food(db, text)
    return RedirectResponse("/cuerpo", status_code=303)


@router.post("/comida/{entry_id}/borrar")
def delete_food(entry_id: int, db: Session = Depends(get_db)):
    body.delete_food(db, entry_id)
    return RedirectResponse("/cuerpo", status_code=303)


@router.post("/peso")
def add_weight(kg: str = Form(...), date: str = Form(""), db: Session = Depends(get_db)):
    if (value := parse_amount(kg)) and value > 0:
        body.log_weight(db, value, parse_date(date))
    return RedirectResponse("/cuerpo", status_code=303)


@router.post("/peso/{weight_id}/borrar")
def delete_weight(weight_id: int, db: Session = Depends(get_db)):
    body.delete_weight(db, weight_id)
    return RedirectResponse("/cuerpo", status_code=303)


@router.post("/meta")
def set_goal(kg: str = Form(""), db: Session = Depends(get_db)):
    value = parse_amount(kg)
    body.set_goal(db, value if value and value > 0 else None)
    return RedirectResponse("/cuerpo", status_code=303)
