from decimal import Decimal

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import lists
from app.web.templates import render

router = APIRouter()


def _plain(value: Decimal) -> str:
    """Decimal('1.000') -> '1', Decimal('1500.00') -> '1500' (sin puntos que parezcan miles)."""
    return f"{value.normalize():f}"


@router.get("/listas")
def lists_page(request: Request, db: Session = Depends(get_db)):
    items = lists.home_items(db)
    text = lists.whatsapp_text(items)
    return render(
        request, "pages/lists.html",
        items=items, whatsapp_text=text, whatsapp_url=lists.whatsapp_url(text),
        open_trip=lists.open_trip(db), trips=lists.recent_trips(db, 5),
    )


@router.post("/listas/casa")
def add_items(text: str = Form(""), db: Session = Depends(get_db)):
    lists.add_home_items(db, text)
    return RedirectResponse("/listas", status_code=303)


@router.post("/listas/casa/{item_id}/marcar")
def toggle(item_id: int, db: Session = Depends(get_db)):
    lists.toggle_home_item(db, item_id)
    return RedirectResponse("/listas", status_code=303)


@router.post("/listas/casa/{item_id}/borrar")
def delete(item_id: int, db: Session = Depends(get_db)):
    lists.delete_home_item(db, item_id)
    return RedirectResponse("/listas", status_code=303)


@router.post("/listas/casa/limpiar")
def clear(db: Session = Depends(get_db)):
    lists.clear_done(db)
    return RedirectResponse("/listas", status_code=303)


@router.get("/mercado")
def market_page(request: Request, db: Session = Depends(get_db)):
    trip = lists.open_trip(db)
    if trip is None:
        return RedirectResponse("/listas", status_code=303)
    return render(
        request, "pages/market.html", trip=trip,
        state={
            "tripId": trip.id,
            "budget": _plain(trip.budget) if trip.budget else "",
            "items": [{"name": i.name, "price": _plain(i.price) if i.price else "", "qty": _plain(i.qty)} for i in trip.items],
            "lastPrices": {k: str(v) for k, v in lists.last_prices(db).items()},
        },
        error=request.query_params.get("error"),
    )


@router.post("/mercado/empezar")
def start(db: Session = Depends(get_db)):
    lists.start_trip(db)
    return RedirectResponse("/mercado", status_code=303)


@router.put("/mercado/{trip_id}")
def save(trip_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        trip = lists.save_trip(db, trip_id, payload.get("items", []), payload.get("budget"))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"total": str(trip.total)}


@router.post("/mercado/{trip_id}/cerrar")
def close(trip_id: int, db: Session = Depends(get_db)):
    try:
        lists.close_trip(db, trip_id)
    except ValueError as exc:
        return RedirectResponse(f"/mercado?error={exc}", status_code=303)
    return RedirectResponse("/plata", status_code=303)


@router.post("/mercado/{trip_id}/descartar")
def discard(trip_id: int, db: Session = Depends(get_db)):
    lists.discard_trip(db, trip_id)
    return RedirectResponse("/listas", status_code=303)
