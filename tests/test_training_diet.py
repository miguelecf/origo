import datetime as dt
from decimal import Decimal

import pytest

from app.core.clock import today
from app.services import diet, training


def test_exercise_catalog_reuses_names(db):
    training.add_item(db, 0, "Press banca", 4, 10, Decimal(40))
    training.add_item(db, 3, "  press   BANCA ", 3, 8)
    assert training.exercise_names(db) == ["Press banca"]


@pytest.mark.parametrize("args", [
    (7, "Sentadilla", 4, 10), (0, " ", 4, 10), (0, "Sentadilla", None, 10),
    (0, "Sentadilla", 4, None), (0, "Sentadilla", 0, 10), (0, "Sentadilla", 4, 10, Decimal(-5)),
])
def test_routine_requires_sets_and_reps(db, args):
    with pytest.raises(ValueError):
        training.add_item(db, *args)


def test_done_goes_to_history_and_shows_last_time(db):
    monday = dt.date(2026, 10, 26)
    item = training.add_item(db, 0, "Sentadilla", 4, 12, Decimal(60))
    assert training.toggle_done(db, item.id, monday) is True
    assert training.done_ids(db, monday) == {item.id}
    assert training.toggle_done(db, item.id, monday) is False  # desmarcar
    training.toggle_done(db, item.id, monday)

    later = monday + dt.timedelta(days=7)
    last = training.last_done(db, [item.exercise_id], later)[item.exercise_id]
    assert (last.date, last.kg, last.sets, last.reps) == (monday, Decimal(60), 4, 12)
    assert training.history(db, days=10, until=later)[0][0] == monday

    training.delete_item(db, item.id)  # sacarlo de la rutina no borra lo hecho
    assert training.history(db, days=10, until=later)[0][1][0].exercise.name == "Sentadilla"


def test_order_and_next_training_day(db):
    a = training.add_item(db, 2, "Remo", 4, 10)
    b = training.add_item(db, 2, "Dominadas", 3, 8)
    training.move_item(db, b.id, -1)
    assert [i.exercise.name for i in training.day_plan(db, 2)["items"]] == ["Dominadas", "Remo"]
    training.set_title(db, 2, "  Espalda  ")
    monday = dt.date(2026, 10, 26)
    day, plan = training.next_training_day(db, monday)
    assert day == dt.date(2026, 10, 28) and plan["title"] == "Espalda"
    assert a.id in {i.id for i in plan["items"]}


def test_current_meal_by_hour():
    at = lambda h, m=0: dt.datetime(2026, 10, 28, h, m)
    assert [diet.current_slot(at(h)) for h in (3, 7, 10, 13, 17, 21)] == [
        "cena", "desayuno", "media_manana", "almuerzo", "merienda", "cena"]


def test_diet_search_ignores_accents_and_case(db):
    diet.save(db, "desayuno", "Avena con plátano\nTostadas con queso")
    diet.save(db, "merienda", "Yogur con PLATANO")
    diet.save(db, "almuerzo", "Pollo con arroz")
    found = diet.search(db, "platano")
    assert [(s["key"], s["lines"]) for s in found] == [
        ("desayuno", ["Avena con plátano"]), ("merienda", ["Yogur con PLATANO"])]
    assert diet.search(db, "pollo arroz")[0]["key"] == "almuerzo"
    assert diet.search(db, "pescado") == []
    with pytest.raises(ValueError):
        diet.save(db, "brunch", "x")


def test_training_and_diet_pages(client):
    wd = today().weekday()
    for path in ["/entreno", "/entreno/rutina", "/cuerpo/dieta", "/cuerpo/dieta?q=pollo"]:
        assert client.get(path).status_code == 200, path

    client.post(f"/entreno/rutina/{wd}", data={"name": "Press militar", "sets": "4", "reps": "10", "kg": "25"})
    client.post(f"/entreno/rutina/{wd}/titulo", data={"title": "Hombros"})
    error = client.post(f"/entreno/rutina/{wd}", data={"name": "Vuelos", "sets": "", "reps": "12"}, follow_redirects=False)
    assert "error=" in error.headers["location"]

    page = client.get("/entreno").text
    assert "Hombros" in page and "Press militar" in page and "0 de 1 hechos" in page
    item_id = page.split("/entreno/hecho/")[1].split('"')[0]
    client.post(f"/entreno/hecho/{item_id}")
    assert "1 de 1 hechos" in client.get("/entreno").text
    assert "Press militar" in client.get("/").text or "Hombros" in client.get("/").text

    client.post("/cuerpo/dieta/almuerzo", data={"text": "Pollo con ensalada"})
    assert "Pollo con ensalada" in client.get("/cuerpo/dieta?q=POLLO").text
    assert "Ahora toca" in client.get("/cuerpo").text


def test_tabbar_has_entreno_instead_of_dia(client):
    page = client.get("/dia").text
    assert 'href="/entreno"' in page and '<span>Día</span>' not in page
    assert '<a href="/cuerpo" aria-current="page">' in page  # Día vive dentro de Cuerpo
    assert '<a href="/dia" aria-current="page">☀️ Día</a>' in page
