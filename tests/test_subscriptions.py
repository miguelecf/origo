import datetime as dt
from decimal import Decimal

import pytest
from fastmcp import Client

from app.core.clock import today
from app.core.database import init_db
from app.mcp_server import mcp
from app.services import finance, subscriptions


def test_monthly_totals_split_by_currency_and_period(db):
    subscriptions.create_subscription(db, name="Netflix", amount=Decimal("9000"), category="Streaming")
    subscriptions.create_subscription(db, name="Claude", amount=Decimal("20"), currency="USD", category="IA")
    subscriptions.create_subscription(db, name="Platzi", amount=Decimal("120000"), period="yearly", category="Cursos")
    paused = subscriptions.create_subscription(db, name="Max", amount=Decimal("5000"), category="Streaming")
    subscriptions.set_active(db, paused.id, False)
    totals = subscriptions.monthly_totals(subscriptions.list_subscriptions(db))
    assert totals == {"ARS": Decimal("19000.00"), "USD": Decimal("20.00")}


def test_charge_goes_to_plata_and_moves_next_charge(db):
    start = dt.date(2026, 1, 31)
    sub = subscriptions.create_subscription(db, name="Spotify", amount=Decimal("4500"), next_charge=start,
                                            category="Música", paid_with="mercadopago")
    tx = subscriptions.mark_charged(db, sub.id, on=start)
    assert (tx.kind, tx.category, tx.amount, tx.source) == ("expense", "Suscripciones", Decimal("4500"), "subscription")
    assert sub.next_charge == dt.date(2026, 2, 28)
    assert finance.summary(db, start, start + dt.timedelta(days=1))["expense"] == Decimal("4500")


def test_usd_charge_needs_pesos(db):
    sub = subscriptions.create_subscription(db, name="ChatGPT", amount=Decimal("20"), currency="USD",
                                            period="yearly", category="IA")
    with pytest.raises(ValueError, match="pesos"):
        subscriptions.mark_charged(db, sub.id)
    tx = subscriptions.mark_charged(db, sub.id, amount_ars=Decimal("25000"))
    assert tx.amount == Decimal("25000") and "US$ 20.00" in tx.note
    assert sub.next_charge == today().replace(year=today().year + 1)


@pytest.mark.parametrize("change", [
    {"name": " "}, {"amount": Decimal(0)}, {"currency": "EUR"}, {"period": "weekly"},
    {"category": "Comida"}, {"paid_with": "paypal"},
])
def test_invalid_subscriptions_do_not_persist(db, change):
    with pytest.raises(ValueError):
        subscriptions.create_subscription(db, **({"name": "Netflix", "amount": Decimal(9000)} | change))
    assert subscriptions.list_subscriptions(db) == []


def test_subscriptions_through_forms(client):
    assert client.get("/plata/suscripciones").status_code == 200
    client.post("/plata/suscripciones", data={"name": "Cursor Pro", "amount": "20", "currency": "USD", "period": "monthly",
                                              "category": "IA", "next_charge": today().isoformat(), "paid_with": "lemon"})
    page = client.get("/plata/suscripciones").text
    assert "Cursor Pro" in page and "US$ 20" in page and "Cuánto salió en pesos" in page
    assert "Cursor Pro" in client.get("/").text  # tarjeta de Inicio: se cobra esta semana

    sub_id = page.split('/plata/suscripciones/')[1].split('/')[0]
    error = client.post(f"/plata/suscripciones/{sub_id}/cobrada", data={"amount_ars": ""}, follow_redirects=False)
    assert "error=" in error.headers["location"]
    client.post(f"/plata/suscripciones/{sub_id}/cobrada", data={"amount_ars": "24.800"})
    assert "24.800" in client.get("/plata").text

    client.post(f"/plata/suscripciones/{sub_id}/activa", data={"active": "false"})
    assert "Pausadas" in client.get("/plata/suscripciones").text
    client.post(f"/plata/suscripciones/{sub_id}/borrar")
    assert "Cursor Pro" not in client.get("/plata/suscripciones").text


def test_subscriptions_are_owner_only(anonymous_client):
    assert anonymous_client.get("/plata/suscripciones", follow_redirects=False).status_code in (303, 401)


@pytest.mark.anyio
async def test_hermes_can_manage_subscriptions():
    init_db()
    async with Client(mcp) as client:
        async def call(tool, **args):
            return (await client.call_tool(tool, args)).data

        sub = await call("add_subscription", name="Gemini", amount=22, currency="USD", category="IA")
        assert sub["next_charge"] == today().isoformat()
        listed = await call("get_subscriptions")
        assert any(s["id"] == sub["id"] for s in listed["subscriptions"]) and listed["monthly_cost"]["USD"] >= 22
        charged = await call("mark_subscription_charged", subscription_id=sub["id"], amount_ars=27000)
        assert charged["amount"] == 27000
        assert (await call("set_subscription_active", subscription_id=sub["id"], active=False))["active"] is False
        assert "subscriptions" in await call("get_overview")
