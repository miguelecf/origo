from decimal import Decimal

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import MarketTrip
from app.services import lists
from app.web.auth import Viewer, require_owner, require_scope
from app.web.templates import render

router = APIRouter(prefix="/super", dependencies=[Depends(require_scope("lists"))])
can_shop = require_scope("lists")


def _plain(value: Decimal) -> str:
    """Decimal('1.000') -> '1', Decimal('1500.00') -> '1500' (sin puntos que parezcan miles)."""
    return f"{value.normalize():f}"


def _own_trip(db: Session, trip_id: int, viewer: Viewer) -> MarketTrip:
    """Cada uno toca solo su compra."""
    trip = db.get(MarketTrip, trip_id)
    if trip is None or trip.guest_id != viewer.guest_id:
        raise HTTPException(status_code=404)
    return trip


@router.get("")
def lists_page(request: Request, viewer: Viewer = Depends(can_shop), db: Session = Depends(get_db)):
    items = lists.home_items(db)
    text = lists.whatsapp_text(items)
    return render(
        request, "pages/lists.html",
        items=items, whatsapp_text=text, whatsapp_url=lists.whatsapp_url(text),
        open_trip=lists.open_trip(db, viewer.guest_id),
        trips=lists.recent_trips(db, 6, guest_id=None if viewer.is_owner else viewer.guest_id),
    )


@router.post("/casa")
def add_items(text: str = Form(""), db: Session = Depends(get_db)):
    lists.add_home_items(db, text)
    return RedirectResponse("/super", status_code=303)


@router.post("/casa/{item_id}/marcar")
def toggle(item_id: int, db: Session = Depends(get_db)):
    lists.toggle_home_item(db, item_id)
    return RedirectResponse("/super", status_code=303)


@router.post("/casa/{item_id}/borrar")
def delete(item_id: int, db: Session = Depends(get_db)):
    lists.delete_home_item(db, item_id)
    return RedirectResponse("/super", status_code=303)


@router.post("/casa/limpiar")
def clear(db: Session = Depends(get_db)):
    lists.clear_done(db)
    return RedirectResponse("/super", status_code=303)


@router.get("/compra")
def trip_page(request: Request, viewer: Viewer = Depends(can_shop), db: Session = Depends(get_db)):
    trip = lists.open_trip(db, viewer.guest_id)
    if trip is None:
        pending = [i for i in lists.home_items(db) if not i.done]
        return render(request, "pages/trip_start.html", pending=pending)
    return render(
        request, "pages/market.html", trip=trip,
        state={
            "tripId": trip.id,
            "isOwner": viewer.is_owner,
            "budget": _plain(trip.budget) if trip.budget else "",
            "items": [
                {"name": i.name, "price": _plain(i.price) if i.price else "", "qty": _plain(i.qty)}
                for i in trip.items
            ],
            "lastPrices": {k: str(v) for k, v in lists.last_prices(db).items()},
        },
        error=request.query_params.get("error"),
    )


@router.post("/compra/empezar")
def start(from_list: bool = Form(True), viewer: Viewer = Depends(can_shop), db: Session = Depends(get_db)):
    trip = lists.start_trip(db, viewer.guest_id)
    if not from_list and trip.items and all(not i.price for i in trip.items):
        lists.save_trip(db, trip.id, [])  # en blanco: solo precios
    return RedirectResponse("/super/compra", status_code=303)


@router.put("/compra/{trip_id}")
def save(trip_id: int, payload: dict = Body(...), viewer: Viewer = Depends(can_shop), db: Session = Depends(get_db)):
    _own_trip(db, trip_id, viewer)
    try:
        trip = lists.save_trip(db, trip_id, payload.get("items", []), payload.get("budget"))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"total": str(trip.total)}


@router.post("/compra/{trip_id}/cerrar")
def close(trip_id: int, viewer: Viewer = Depends(can_shop), db: Session = Depends(get_db)):
    _own_trip(db, trip_id, viewer)
    try:
        lists.close_trip(db, trip_id)
    except ValueError as exc:
        return RedirectResponse(f"/super/compra?error={exc}", status_code=303)
    return RedirectResponse("/plata" if viewer.is_owner else "/super", status_code=303)


@router.post("/compra/{trip_id}/descartar")
def discard(trip_id: int, viewer: Viewer = Depends(can_shop), db: Session = Depends(get_db)):
    _own_trip(db, trip_id, viewer)
    lists.discard_trip(db, trip_id)
    return RedirectResponse("/super", status_code=303)


@router.post("/compra/{trip_id}/cargar", dependencies=[Depends(require_owner)])
def charge(trip_id: int, db: Session = Depends(get_db)):
    try:
        lists.charge_to_me(db, trip_id)
    except ValueError:
        pass
    return RedirectResponse("/super", status_code=303)
