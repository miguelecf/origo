from decimal import Decimal

from app.core.clock import month_bounds, today
from app.models import Debt
from app.services import finance, guests, lists


def test_split_trip_charges_all_and_records_their_share(db):
    trip = lists.start_trip(db)
    lists.save_trip(db, trip.id, [
        {"name": "Yerba", "price": "3000", "my_pct": "100"},    # mío
        {"name": "Aceite", "price": "2000", "my_pct": "60"},    # compartido 60/40
        {"name": "Shampoo", "price": "1500", "my_pct": "0"},    # suyo
        {"name": "Pan", "price": "", "my_pct": "50"},           # sin marcar: no cuenta
    ], split_with="  Ana  ", split_pct="60")
    assert trip.split_with == "Ana" and trip.split_pct == 60
    assert trip.total == Decimal(6500)
    assert trip.my_total == Decimal(4200) and trip.their_total == Decimal(2300)

    lists.close_trip(db, trip.id)
    # Pagué todo: el gasto es el total y su parte queda como que me debe.
    assert finance.summary(db, *month_bounds(today()))["expense"] == 6500
    debt = db.get(Debt, trip.debt_id)
    assert debt.person == "Ana" and debt.direction == "owed_to_me" and debt.total == Decimal(2300)
    assert "Ana" in lists.split_people(db)


def test_without_split_percentages_are_ignored(db):
    trip = lists.start_trip(db)
    lists.save_trip(db, trip.id, [{"name": "Leche", "price": "1000", "my_pct": "0"}], split_with="")
    assert trip.split_with is None and trip.my_total == trip.total == Decimal(1000)
    lists.close_trip(db, trip.id)
    assert trip.debt_id is None and db.query(Debt).count() == 0


def test_invalid_percentages_fall_back_to_mine(db):
    trip = lists.start_trip(db)
    lists.save_trip(db, trip.id, [{"name": "A", "price": "100", "my_pct": "150"},
                                  {"name": "B", "price": "100", "my_pct": "abc"}], split_with="Ana")
    assert [i.my_pct for i in trip.items] == [None, None] and trip.their_total == 0
    lists.close_trip(db, trip.id)
    assert trip.debt_id is None  # nada que deber


def test_guest_trip_cannot_split(db):
    guest, _ = guests.create_guest(db, name="Ana", can_lists=True)
    trip = lists.start_trip(db, guest.id)
    lists.save_trip(db, trip.id, [{"name": "A", "price": "100", "my_pct": "0"}], split_with="Yo")
    assert trip.split_with is None and trip.items[0].my_pct is None


def test_market_page_and_put_with_split(client, db):
    lists.add_home_items(db, "leche, pan")
    client.post("/super/compra/empezar", data={"from_list": "true"})
    page = client.get("/super/compra")
    assert page.status_code == 200 and "Dividir con alguien" in page.text and "ticket" not in page.text
    trip = lists.open_trip(db)
    r = client.put(f"/super/compra/{trip.id}", json={
        "split_with": "Ana", "split_pct": "50",
        "items": [{"name": "leche", "price": "1000", "qty": "2", "my_pct": "50"}, {"name": "pan", "price": ""}],
    })
    assert r.status_code == 200
    client.post(f"/super/compra/{trip.id}/cerrar")
    debt = db.get(Debt, lists.recent_trips(db, 1)[0].debt_id)
    assert debt.total == Decimal(1000)
    # El pan quedó sin marcar: sigue pendiente en la lista de casa.
    assert [i.name for i in lists.home_items(db) if not i.done] == ["pan"]
