"""Planes por MCP: dieta, objetivos, rutina con rangos, composición e hitos.
Lo que escribe el agente aparece en la web y al revés, sin pisar lo que ya había."""
import datetime as dt
from decimal import Decimal

import pytest
from fastmcp import Client
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app import mcp_server
from app.core.clock import today
from app.mcp_server import mcp
from app.services import body, diet, training

PLAN_TOOLS = {
    "get_diet_plan", "set_meal", "clear_meal", "copy_diet_day", "set_diet_targets", "delete_food_entry",
    "get_routine", "add_routine_item", "update_routine_item", "move_routine_item", "delete_routine_item",
    "set_routine_day_title", "get_workout_history",
    "get_weight_goals", "add_weight_milestone", "delete_weight_milestone",
}


@pytest.fixture
def shared(db, monkeypatch):
    """El MCP y la web usan la misma base de prueba."""
    monkeypatch.setattr(mcp_server, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    return db


async def _call(client, name, **args):
    return (await client.call_tool(name, args)).data


# --- Servicios ---

@pytest.mark.parametrize("raw, expected", [
    ("10", (10, None)), ("8-12", (8, 12)), ("8–12", (8, 12)), (" 8 a 12 ", (8, 12)), ("10-10", (10, None)),
    ("", (None, None)), ("diez", (None, None)), ("8-10-12", (None, None)),
])
def test_parse_reps(raw, expected):
    assert training.parse_reps(raw) == expected


def test_rep_range_is_kept_and_copied_to_history(db):
    item = training.add_item(db, 0, "Sentadilla", 4, 8, Decimal(60), reps_max=12)
    assert (item.reps, item.reps_max) == (8, 12)
    monday = dt.date(2026, 10, 26)
    training.toggle_done(db, item.id, monday)
    log = training.history(db, days=3, until=monday)[0][1][0]
    assert (log.reps, log.reps_max) == (8, 12)


@pytest.mark.parametrize("reps, reps_max", [(12, 8), (10, 10), (8, 600)])
def test_rep_range_must_go_up(db, reps, reps_max):
    with pytest.raises(ValueError):
        training.add_item(db, 0, "Remo", 4, reps, reps_max=reps_max)


def test_legacy_rows_without_range_still_work(db):
    """Filas viejas (sin reps_max) se leen como repeticiones fijas."""
    item = training.add_item(db, 1, "Curl", 3, 10)
    db.execute(text("UPDATE routine_items SET reps_max = NULL WHERE id = :id"), {"id": item.id})
    db.commit()
    db.refresh(item)
    assert item.reps_max is None and training.format_reps(item.reps, item.reps_max) == "10"


def test_duplicate_exercise_in_same_day_is_rejected(db):
    training.add_item(db, 2, "Press banca", 4, 10)
    with pytest.raises(ValueError, match="ya está"):
        training.add_item(db, 2, "press  BANCA", 3, 8)
    training.add_item(db, 2, "Press banca", 2, 15, allow_duplicate=True)
    training.add_item(db, 3, "Press banca", 4, 10)  # otro día, sin problema
    assert len(training.day_plan(db, 2)["items"]) == 2


def test_update_item_keeps_what_is_not_sent_and_history(db):
    item = training.add_item(db, 4, "Peso muerto", 3, 5, Decimal(100))
    monday = dt.date(2026, 10, 30)
    training.toggle_done(db, item.id, monday)
    training.update_item(db, item.id, reps=6, reps_max=8)
    assert (item.sets, item.reps, item.reps_max, item.kg) == (3, 6, 8, Decimal(100))
    training.update_item(db, item.id, reps_max=None, kg=None)
    assert (item.reps_max, item.kg) == (None, None)
    with pytest.raises(ValueError):
        training.update_item(db, item.id, sets=0)
    log = training.history(db, days=3, until=monday)[0][1][0]
    assert (log.reps, log.kg) == (5, Decimal(100))  # lo hecho no cambia


def test_delete_item_reorders_positions(db):
    a, b, c = (training.add_item(db, 5, name, 3, 10) for name in ("A", "B", "C"))
    assert training.delete_item(db, b.id) is True
    assert [(i.exercise.name, i.position) for i in training.day_plan(db, 5)["items"]] == [("A", 0), ("C", 1)]
    assert training.delete_item(db, b.id) is False


def test_one_meal_per_slot_and_day(db):
    previous = diet.set_meal(db, "desayuno", "  Avena   con banana ", [0, 2])
    assert previous == {0: "", 2: ""}
    assert diet.plan(db, 0)[0]["text"] == "Avena con banana" and diet.plan(db, 1)[0]["text"] == ""
    assert diet.set_meal(db, "desayuno", "Solo café", [0]) == {0: "Avena con banana"}
    for bad in ("Avena\nTostadas", "x" * (diet.MAX_MEAL + 1)):
        with pytest.raises(ValueError):
            diet.set_meal(db, "desayuno", bad, [0])
    with pytest.raises(ValueError):
        diet.set_meal(db, "brunch", "x", [0])
    with pytest.raises(ValueError):
        diet.set_meal(db, "cena", "x", [7])
    with pytest.raises(ValueError):
        diet.set_meal(db, "cena", "x", [])
    assert diet.plan(db, 0)[0]["text"] == "Solo café"  # los errores no pisaron nada
    assert diet.clear_meal(db, "desayuno", [0]) == {0: "Solo café"} and diet.plan(db, 0)[0]["lines"] == []


def test_copy_day(db):
    diet.set_meal(db, "almuerzo", "Pollo con arroz", [0])
    diet.set_meal(db, "cena", "Pescado", [3])
    diet.copy_day(db, 0, [3, 4, 0])
    assert diet.plan(db, 3)[2]["text"] == "Pollo con arroz" and diet.plan(db, 3)[4]["text"] == ""
    assert diet.plan(db, 4)[2]["text"] == "Pollo con arroz"
    with pytest.raises(ValueError):
        diet.copy_day(db, 0, [0])


def test_legacy_plan_is_copied_once_to_every_day(db):
    from app.models import MealPlan

    db.add(MealPlan(slot="desayuno", text="Avena\nTostadas"))
    db.add(MealPlan(slot="cena", text="Sopa"))
    db.commit()
    week = diet.week(db)
    assert all(d["meals"][0]["text"] == "Avena / Tostadas" and d["meals"][4]["text"] == "Sopa" for d in week)
    # Vaciar todo no vuelve a traer el plan viejo, y el viejo queda intacto.
    for slot in diet.SLOT_KEYS:
        diet.clear_meal(db, slot, list(range(7)))
    assert all(not m["text"] for d in diet.week(db) for m in d["meals"])
    assert db.get(MealPlan, "desayuno").text == "Avena\nTostadas"


def test_diet_targets_partial_update(db):
    diet.set_targets(db, kcal=2200, protein_g=180, rules="Sin azúcar\nAgua 3 l")
    diet.set_targets(db, supplements="Creatina 5 g")
    t = diet.targets(db)
    assert (t.kcal, t.protein_g, t.carbs_g, t.rules, t.supplements) == (2200, 180, None, "Sin azúcar\nAgua 3 l", "Creatina 5 g")
    diet.set_targets(db, kcal=None)
    assert diet.targets(db).kcal is None and diet.targets(db).protein_g == 180
    with pytest.raises(ValueError):
        diet.set_targets(db, kcal=-1)
    with pytest.raises(ValueError):
        diet.set_targets(db, calories=2000)


def test_targets_are_not_food_log(db):
    diet.set_targets(db, kcal=2200)
    assert body.food_log(db, today(), today() + dt.timedelta(days=1)) == []


def test_composition_is_optional_and_preserved(db):
    day = dt.date(2026, 10, 27)
    body.log_weight(db, Decimal("115.7"), day, fat_pct=Decimal("35.8"), lean_kg=Decimal("74.3"), visceral_fat=27)
    w = body.log_weight(db, Decimal("115.5"), day)  # corrige el peso, no borra la composición
    assert (w.kg, w.fat_pct, w.lean_kg, w.visceral_fat, w.muscle_pct) == (Decimal("115.5"), Decimal("35.8"), Decimal("74.3"), 27, None)
    with pytest.raises(ValueError):
        body.log_weight(db, Decimal(115), day, fat_pct=Decimal(120))
    with pytest.raises(ValueError):
        body.log_weight(db, Decimal(115), day, bmi=Decimal(30))
    assert body.weight_summary(db)["composition"].fat_pct == Decimal("35.8")


def test_milestones_never_touch_final_goal(db):
    body.set_goal(db, Decimal(80))
    body.log_weight(db, Decimal("115.7"))
    hundred_five = body.add_milestone(db, Decimal(105), "Primer escalón")
    body.add_milestone(db, Decimal(95))
    assert body.get_goal(db) == Decimal(80)
    assert body.next_milestone(db, Decimal("115.7")).id == hundred_five.id
    assert body.next_milestone(db, Decimal(100)).kg == Decimal(95)
    with pytest.raises(ValueError):
        body.add_milestone(db, Decimal(105))
    assert body.delete_milestone(db, hundred_five.id) and body.get_goal(db) == Decimal(80)


# --- MCP ---

@pytest.mark.anyio
async def test_plan_tools_are_listed(shared):
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    assert PLAN_TOOLS <= set(tools)
    assert "toggle_workout_done" not in tools  # el agente no marca entrenamientos como hechos
    # Las descripciones solo mencionan parámetros que el esquema acepta.
    assert set(tools["log_weight"].input_schema["properties"]) == {
        "kg", "date", "fat_pct", "muscle_pct", "lean_kg", "water_pct", "visceral_fat"}
    assert "clear" in tools["update_routine_item"].input_schema["properties"]


@pytest.mark.anyio
async def test_diet_round_trip_mcp_and_web(shared, client):
    client.post("/cuerpo/dieta/0/almuerzo", data={"text": "Pollo con arroz"})
    async with Client(mcp) as mcp_client:
        plan = await _call(mcp_client, "get_diet_plan", weekday=0)
        assert "Una comida por momento" in plan["format"]
        assert next(m for m in plan["days"][0]["meals"] if m["slot"] == "almuerzo")["meal"] == "Pollo con arroz"
        assert len((await _call(mcp_client, "get_diet_plan"))["days"]) == 7

        result = await _call(mcp_client, "set_meal", slot="cena", text="Tortilla de papas", weekdays=[0, 1])
        assert result["previous"] == {"0": None, "1": None}
        cleared = await _call(mcp_client, "clear_meal", slot="almuerzo", weekdays=[0])
        assert cleared["previous"] == {"0": "Pollo con arroz"}

        targets = await _call(mcp_client, "set_diet_targets", kcal=2200, protein_g=180, supplements="Creatina 5 g")
        assert targets["previous"]["kcal"] is None and targets["targets"]["kcal"] == 2200
        cleared = await _call(mcp_client, "set_diet_targets", clear=["protein_g"])
        assert cleared["targets"]["protein_g"] is None and cleared["targets"]["kcal"] == 2200

        for name, args in [("set_meal", {"slot": "brunch", "text": "x", "weekdays": [0]}),
                           ("set_meal", {"slot": "cena", "text": "A\nB", "weekdays": [0]}),
                           ("set_meal", {"slot": "cena", "text": "", "weekdays": [0]}),
                           ("set_meal", {"slot": "cena", "text": "x", "weekdays": []})]:
            assert (await mcp_client.call_tool(name, args, raise_on_error=False)).is_error

        entry = await _call(mcp_client, "log_food", text="Una manzana")
        assert (await _call(mcp_client, "delete_food_entry", entry_id=entry["id"]))["deleted"] == entry["id"]
        assert (await mcp_client.call_tool("delete_food_entry", {"entry_id": entry["id"]}, raise_on_error=False)).is_error

    page = client.get("/cuerpo/dieta?dia=1").text
    assert "Tortilla de papas" in page and "2200" in page and "Creatina 5 g" in page
    client.post("/cuerpo/dieta/1/cena", data={"clear": "true"})
    assert "Tortilla de papas" not in client.get("/cuerpo/dieta?dia=1").text
    assert client.get("/cuerpo").status_code == 200


@pytest.mark.anyio
async def test_routine_round_trip_mcp_and_web(shared, client):
    client.post("/entreno/rutina/0", data={"name": "Sentadilla", "sets": "4", "reps": "8-12", "kg": "60"})
    async with Client(mcp) as mcp_client:
        monday = await _call(mcp_client, "get_routine", weekday=0)
        squat = monday["items"][0]
        assert (squat["exercise"], squat["reps"], squat["reps_max"], squat["reps_text"]) == ("Sentadilla", 8, 12, "8–12")

        dup = await mcp_client.call_tool("add_routine_item", {"weekday": 0, "exercise": "sentadilla", "sets": 3, "reps": 10},
                                         raise_on_error=False)
        assert dup.is_error
        row = await _call(mcp_client, "add_routine_item", weekday=0, exercise="Hip thrust", sets=3, reps=10, reps_max=15)
        await _call(mcp_client, "update_routine_item", item_id=squat["id"], kg=62.5)
        day = await _call(mcp_client, "move_routine_item", item_id=row["id"], direction="up")
        assert [i["exercise"] for i in day["items"]] == ["Hip thrust", "Sentadilla"]
        await _call(mcp_client, "set_routine_day_title", weekday=0, title="Rutina A")

        week = await _call(mcp_client, "get_routine")
        assert len(week["days"]) == 7 and week["days"][0]["title"] == "Rutina A"

    page = client.get("/entreno/rutina?dia=0").text
    assert "Rutina A" in page and "Hip thrust" in page and "3 × 10–15" in page and "62,5" in page

    async with Client(mcp) as mcp_client:
        assert (await _call(mcp_client, "delete_routine_item", item_id=row["id"]))["deleted"] == row["id"]
        assert (await _call(mcp_client, "get_workout_history", days=7)) == []  # nada marcado como hecho
    items = client.get("/entreno/rutina?dia=0").text.split('class="lines routine-items"')[1].split("</ul>")[0]
    assert "Hip thrust" not in items and "Sentadilla" in items  # el catálogo lo sigue sugiriendo


@pytest.mark.anyio
async def test_weight_composition_and_milestones_round_trip(shared, client):
    client.post("/cuerpo/meta", data={"kg": "80"})
    async with Client(mcp) as mcp_client:
        w = await _call(mcp_client, "log_weight", kg=115.7, date="2026-10-27", fat_pct=35.8, lean_kg=74.3, visceral_fat=27)
        assert (w["fat_pct"], w["lean_kg"], w["visceral_fat"]) == (35.8, 74.3, 27) and "muscle_pct" not in w
        m = await _call(mcp_client, "add_weight_milestone", kg=105, note="Próximo hito")
        goals = await _call(mcp_client, "get_weight_goals")
        assert goals["goal_kg"] == 80 and goals["next_milestone"]["id"] == m["id"]
        overview = await _call(mcp_client, "get_overview")
        assert overview["weight"]["goal_kg"] == 80 and overview["weight"]["next_milestone"]["kg"] == 105

    page = client.get("/cuerpo").text
    assert "35,8 %" in page and "105" in page and "Próximo hito" in page

    client.post("/cuerpo/peso", data={"kg": "115,5", "date": "2026-10-27"})  # la web no borra la composición
    async with Client(mcp) as mcp_client:
        series = await _call(mcp_client, "get_weight_series")
        assert series[-1]["kg"] == 115.5 and series[-1]["fat_pct"] == 35.8
        await _call(mcp_client, "delete_weight_milestone", milestone_id=m["id"])
        assert (await _call(mcp_client, "get_weight_goals"))["goal_kg"] == 80
