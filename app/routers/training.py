from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.database import get_db
from app.models import RoutineItem
from app.services import training
from app.web.forms import parse_amount, parse_int
from app.web.templates import render

router = APIRouter(prefix="/entreno")


def _to_routine(weekday: int, error: str | None = None) -> RedirectResponse:
    url = f"/entreno/rutina?dia={weekday}" + (f"&error={quote(error)}" if error else "")
    return RedirectResponse(url, status_code=303)


@router.get("")
def today_page(request: Request, db: Session = Depends(get_db)):
    day = today()
    plan = training.day_plan(db, day.weekday())
    return render(
        request, "pages/training.html",
        day=day, plan=plan, done=training.done_ids(db, day),
        last=training.last_done(db, [i.exercise_id for i in plan["items"]], day),
        upcoming=training.next_training_day(db, day), week=training.week(db),
        history=training.history(db, days=60)[:6], today=day, error=request.query_params.get("error"),
    )


@router.post("/hecho/{item_id}")
def toggle(item_id: int, db: Session = Depends(get_db)):
    try:
        training.toggle_done(db, item_id)
    except ValueError as exc:
        return RedirectResponse(f"/entreno?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"/entreno#ej-{item_id}", status_code=303)


@router.get("/rutina")
def routine_page(request: Request, dia: int | None = None, db: Session = Depends(get_db)):
    weekday = dia if dia is not None and 0 <= dia <= 6 else today().weekday()
    return render(
        request, "pages/routine.html",
        plan=training.day_plan(db, weekday), week=training.week(db), weekdays=training.WEEKDAYS,
        exercise_names=training.exercise_names(db), today=today(), error=request.query_params.get("error"),
    )


@router.post("/rutina/{weekday}")
def add_item(
    weekday: int, name: str = Form(""), sets: str = Form(""), reps: str = Form(""), kg: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        training.add_item(db, weekday, name, parse_int(sets), parse_int(reps), parse_amount(kg))
    except ValueError as exc:
        return _to_routine(weekday, str(exc))
    return _to_routine(weekday)


@router.post("/rutina/{weekday}/titulo")
def set_title(weekday: int, title: str = Form(""), db: Session = Depends(get_db)):
    try:
        training.set_title(db, weekday, title)
    except ValueError as exc:
        return _to_routine(0, str(exc))
    return _to_routine(weekday)


@router.post("/rutina/item/{item_id}/{action}")
def change_item(item_id: int, action: str, db: Session = Depends(get_db)):
    item = db.get(RoutineItem, item_id)
    if item is None:
        return RedirectResponse("/entreno/rutina", status_code=303)
    weekday = item.weekday
    if action in ("subir", "bajar"):
        training.move_item(db, item_id, -1 if action == "subir" else 1)
    elif action == "borrar":
        training.delete_item(db, item_id)
    return _to_routine(weekday)
