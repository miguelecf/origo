import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from sqlalchemy import select

from app.core.clock import today
from app.core.database import get_db
from app.main import app
from app.models import Debt
from app.services import debts, guests


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as browser:
        yield browser
    app.dependency_overrides.pop(get_db, None)


def create(db, **kwargs):
    values = dict(person="", kind="card", brand="visa", direction="i_owe",
                  total=Decimal("1234567.50"), installments=3, first_due=today())
    return debts.create_debt(db, **(values | kwargs))


def test_card_and_entity_catalog_names(db):
    card = create(db)
    assert (card.person, card.kind, card.brand) == ("Visa", "card", "visa")
    assert sum(i.amount for i in card.installments) == card.total
    entity = create(db, kind="entity", brand="mercadopago", first_due=None)
    assert entity.person == "Mercado Pago"
    other = create(db, kind="entity", brand=None, person="Cooperativa", first_due=None)
    assert other.person == "Cooperativa" and other.brand is None
    assert create(db, person="Visa Galicia").person == "Visa Galicia"


@pytest.mark.parametrize("change", [
    {"kind": "unknown"}, {"brand": "mercadopago"}, {"kind": "entity", "brand": "visa"},
    {"direction": "owed_to_me"}, {"kind": "entity", "brand": "uala", "direction": "owed_to_me"},
    {"first_due": None}, {"brand": None}, {"kind": "person"},
    {"kind": "entity", "brand": None, "person": " "}, {"installments": 0}, {"installments": None},
    {"total": Decimal("0")}, {"total": Decimal("NaN")}, {"total": Decimal("Infinity")},
])
def test_invalid_debts_do_not_persist(db, change):
    with pytest.raises(ValueError):
        create(db, **change)
    assert db.scalars(select(Debt)).all() == []


def test_card_loan_brand_and_atomic_validation(db):
    with pytest.raises(ValueError):
        debts.create_card_loan(db, person="Ana", card="Visa", brand="uala", total=Decimal(10),
                               installments=1, first_due=today())
    assert db.scalars(select(Debt)).all() == []
    person, card = debts.create_card_loan(db, person="Ana", card="Visa Galicia", brand="visa",
                                        total=Decimal(120), installments=2, first_due=today())
    assert (person.kind, person.brand, card.kind, card.brand) == ("person", None, "card", "visa")
    assert person.group_id == card.group_id


def test_guest_never_sees_same_named_cards_or_entities(db):
    guest, _ = guests.create_guest(db, name="Ana", can_debts=True)
    person = create(db, kind="person", brand=None, person="Ana", direction="owed_to_me")
    card = create(db, person="Ana")
    entity = create(db, person="Ana", kind="entity", brand="uala")
    assert [d.id for d in guests.guest_debts(db, guest)] == [person.id]
    with pytest.raises(ValueError):
        guests.create_claim(db, guest, [card.installments[0].id, entity.installments[0].id])


def test_balances_groups_and_settled(db):
    card = create(db, total=Decimal(300))
    create(db, kind="entity", brand="uala", total=Decimal(60))
    create(db, kind="person", brand=None, person="Ana", total=Decimal(90), direction="owed_to_me")
    create(db, kind="person", brand=None, person="Juan", total=Decimal(30))
    debts.set_installment_paid(db, card.installments[0].id, True)
    result = debts.balances(db)
    assert result["i_owe"] == 290 and result["owed_to_me"] == 90
    assert result["by_kind"] == {
        "person": {"i_owe": Decimal(30), "owed_to_me": Decimal(90)},
        "card": {"i_owe": Decimal(200), "owed_to_me": Decimal(0)},
        "entity": {"i_owe": Decimal(60), "owed_to_me": Decimal(0)},
    }
    assert debts.next_due(card) > today()
    for installment in card.installments:
        debts.set_installment_paid(db, installment.id, True)
    assert debts.next_due(card) is None
    assert debts.debt_groups(db)[1]["debts"] == []
    assert debts.debt_groups(db, settled=True)[1]["debts"] == [card]


def test_form_money_and_new_kinds(client, db):
    response = client.post("/deudas", data={"kind": "card", "direction": "i_owe", "brand": "visa",
                           "total": "1.234.567,5", "first_due": today().isoformat()})
    assert response.status_code == 200
    card = db.scalar(select(Debt))
    assert card.total == Decimal("1234567.50") and card.person == "Visa"
    client.post("/deudas", data={"kind": "entity", "direction": "i_owe", "brand": "mercadopago", "total": "500"})
    client.post("/deudas", data={"kind": "entity", "direction": "i_owe", "person": "Otra entidad", "total": "600"})
    page = client.get("/deudas").text
    assert all(text in page for text in ("Visa", "Mercado Pago", "Otra entidad", "Tarjetas", "Entidades"))
    assert "Visa" not in client.get("/deudas?todas=1").text.split('class="debt-groups"')[1]


def test_form_validation(client, db):
    client.post("/deudas", data={"kind": "card", "direction": "owed_to_me", "brand": "visa", "total": "100"})
    client.post("/deudas", data={"kind": "entity", "direction": "i_owe", "total": "100"})
    client.post("/deudas", data={"kind": "person", "direction": "i_owe", "person": "Ana", "total": "100", "installments": "cuatro"})
    assert db.scalars(select(Debt)).all() == []


@pytest.mark.anyio
async def test_mcp_exposes_kinds(db, monkeypatch):
    from contextlib import contextmanager
    from app import mcp_server

    @contextmanager
    def local_db():
        yield db

    monkeypatch.setattr(mcp_server, "_db", local_db)
    create(db)
    async with Client(mcp_server.mcp) as client:
        data = (await client.call_tool("get_debts", {})).data
        assert data[0]["kind"] == "card" and data[0]["brand"] == "visa"
        overview = (await client.call_tool("get_overview", {})).data
        assert overview["debts"]["by_kind"]["card"]["i_owe"] == 1234567.5
        due = overview["debts"]["due_next_7_days"][0]
        assert due["kind"] == "card" and due["brand"] == "visa"


@pytest.fixture
def anyio_backend():
    return "asyncio"
