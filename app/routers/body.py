import datetime as dt
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.database import get_db
from app.services import body, diet
from app.web.forms import parse_amount, parse_date, parse_int
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
        meals_by_day=meals_by_day, today=day, meal_plan=diet.plan(db), now_slot=diet.current_slot(),
        milestones=body.milestones(db), error=request.query_params.get("error"),
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
def add_weight(
    kg: str = Form(...), date: str = Form(""), fat_pct: str = Form(""), muscle_pct: str = Form(""),
    lean_kg: str = Form(""), water_pct: str = Form(""), visceral_fat: str = Form(""),
    db: Session = Depends(get_db),
):
    if (value := parse_amount(kg)) and value > 0:
        composition = {"fat_pct": parse_amount(fat_pct), "muscle_pct": parse_amount(muscle_pct),
                       "lean_kg": parse_amount(lean_kg), "water_pct": parse_amount(water_pct),
                       "visceral_fat": parse_int(visceral_fat)}
        try:
            body.log_weight(db, value, parse_date(date), **composition)
        except ValueError as exc:
            return RedirectResponse(f"/cuerpo?error={quote(str(exc))}#peso", status_code=303)
    return RedirectResponse("/cuerpo#peso", status_code=303)


@router.post("/peso/{weight_id}/borrar")
def delete_weight(weight_id: int, db: Session = Depends(get_db)):
    body.delete_weight(db, weight_id)
    return RedirectResponse("/cuerpo", status_code=303)


@router.post("/meta")
def set_goal(kg: str = Form(""), db: Session = Depends(get_db)):
    value = parse_amount(kg)
    body.set_goal(db, value if value and value > 0 else None)
    return RedirectResponse("/cuerpo", status_code=303)


@router.post("/hito")
def add_milestone(kg: str = Form(""), note: str = Form(""), db: Session = Depends(get_db)):
    try:
        body.add_milestone(db, parse_amount(kg) or Decimal(0), note)
    except ValueError as exc:
        return RedirectResponse(f"/cuerpo?error={quote(str(exc))}#peso", status_code=303)
    return RedirectResponse("/cuerpo#peso", status_code=303)


@router.post("/hito/{milestone_id}/borrar")
def delete_milestone(milestone_id: int, db: Session = Depends(get_db)):
    body.delete_milestone(db, milestone_id)
    return RedirectResponse("/cuerpo#peso", status_code=303)


def _day_param(value) -> int:
    return value if isinstance(value, int) and 0 <= value <= 6 else today().weekday()


@router.get("/dieta")
def diet_page(request: Request, q: str = "", dia: int | None = None, db: Session = Depends(get_db)):
    weekday = _day_param(dia)
    return render(
        request, "pages/diet.html",
        week=diet.week(db), weekday=weekday, today_weekday=today().weekday(),
        meal_plan=diet.plan(db, weekday), now_slot=diet.current_slot(), query=q.strip()[:80],
        results=diet.search(db, q[:80]) if q.strip() else None, saved=request.query_params.get("ok"),
        targets=diet.targets(db), target_lines=diet.targets_lines(diet.targets(db)),
        error=request.query_params.get("error"),
    )


@router.post("/dieta/objetivos")
def save_targets(
    kcal: str = Form(""), protein_g: str = Form(""), carbs_g: str = Form(""), fat_g: str = Form(""),
    rules: str = Form(""), supplements: str = Form(""), db: Session = Depends(get_db),
):
    try:
        diet.set_targets(db, kcal=parse_int(kcal), protein_g=parse_int(protein_g), carbs_g=parse_int(carbs_g),
                         fat_g=parse_int(fat_g), rules=rules, supplements=supplements)
    except ValueError as exc:
        return RedirectResponse(f"/cuerpo/dieta?error={quote(str(exc))}#objetivos", status_code=303)
    return RedirectResponse("/cuerpo/dieta?ok=objetivos#objetivos", status_code=303)


@router.post("/dieta/{weekday}/copiar")
def copy_diet_day(weekday: int, to: list[int] = Form([]), db: Session = Depends(get_db)):
    try:
        diet.copy_day(db, weekday, to)
    except ValueError as exc:
        return RedirectResponse(f"/cuerpo/dieta?dia={weekday}&error={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"/cuerpo/dieta?dia={weekday}&ok=copiado", status_code=303)


@router.post("/dieta/{weekday}/{slot}")
def save_meal(
    weekday: int, slot: str, text: str = Form(""), every_day: bool = Form(False), clear: bool = Form(False),
    db: Session = Depends(get_db),
):
    try:
        diet.set_meal(db, slot, "" if clear else text, list(range(7)) if every_day else [weekday])
    except ValueError as exc:
        return RedirectResponse(f"/cuerpo/dieta?dia={weekday}&error={quote(str(exc))}#{slot}", status_code=303)
    return RedirectResponse(f"/cuerpo/dieta?dia={weekday}&ok={slot}#{slot}", status_code=303)
