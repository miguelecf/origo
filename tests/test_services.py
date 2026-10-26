import datetime as dt
from decimal import Decimal

from app.core.clock import add_months, month_bounds, today
from app.services import body, debts, finance, lists, overview


def test_add_months_clamps_end_of_month():
    assert add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    assert add_months(dt.date(2026, 11, 15), 3) == dt.date(2027, 2, 15)


def test_split_amount_puts_remainder_in_last():
    assert debts.split_amount(Decimal("100"), 3) == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]


def test_summary(db):
    finance.add_transaction(db, kind="income", amount=Decimal(1000), category="Sueldo")
    finance.add_transaction(db, kind="expense", amount=Decimal(300), category="Súper")
    s = finance.summary(db, *month_bounds(today()))
    assert (s["income"], s["expense"], s["balance"]) == (1000, 300, 700)
    assert s["by_category"] == [("Súper", Decimal(300))]


def test_card_loan_creates_both_sides_and_alerts(db):
    owed, owing = debts.create_card_loan(
        db, person="Juan", card="Visa", total=Decimal(120000), installments=6, first_due=today(),
    )
    assert owed.direction == "owed_to_me" and owing.direction == "i_owe"
    assert owed.group_id == owing.group_id
    assert [i.due_date for i in owed.installments][:2] == [today(), add_months(today(), 1)]
    assert debts.balances(db) == {"owed_to_me": Decimal(120000), "i_owe": Decimal(120000)}

    alerts = debts.card_alerts(db, today() + dt.timedelta(days=7))
    assert len(alerts) == 1 and alerts[0]["person"] == "Juan"

    debts.set_installment_paid(db, owed.installments[0].id, True)
    assert debts.card_alerts(db, today() + dt.timedelta(days=7)) == []


def test_paying_installment_registers_and_unpaying_removes(db):
    debt = debts.create_debt(db, person="Ana", direction="i_owe", total=Decimal(500), installments=2)
    inst = debts.set_installment_paid(db, debt.installments[0].id, True)
    s = finance.summary(db, *month_bounds(today()))
    assert s["expense"] == 250
    debts.set_installment_paid(db, inst.id, False)
    assert finance.summary(db, *month_bounds(today()))["expense"] == 0


def test_deleting_transaction_unpays_installment(db):
    debt = debts.create_debt(db, person="Ana", direction="owed_to_me", total=Decimal(100))
    inst = debts.set_installment_paid(db, debt.installments[0].id, True)
    finance.delete_transaction(db, inst.transaction_id)
    db.refresh(inst)
    assert inst.paid_on is None


def test_market_trip_flow(db):
    lists.add_home_items(db, "Leche, pan\npan")
    assert [i.name for i in lists.home_items(db)] == ["Leche", "pan"]

    trip = lists.start_trip(db)
    assert [i.name for i in trip.items] == ["Leche", "pan"]
    lists.save_trip(db, trip.id, [
        {"name": "Leche", "price": "1500", "qty": "2"},
        {"name": "pan", "price": "", "qty": "1"},
        {"name": "Yerba", "price": "4200,50", "qty": "1"},
    ], budget="10000")
    assert trip.total == Decimal("7200.50")

    lists.close_trip(db, trip.id)
    assert finance.summary(db, *month_bounds(today()))["by_category"] == [("Súper", Decimal("7200.50"))]
    assert lists.last_prices(db) == {"leche": Decimal(1500), "yerba": Decimal("4200.50")}
    # La leche se compró; el pan quedó sin precio, sigue pendiente.
    assert [(i.name, i.done) for i in lists.home_items(db)] == [("pan", False), ("Leche", True)]
    assert lists.open_trip(db) is None


def test_whatsapp_text(db):
    lists.add_home_items(db, "Arroz, Café")
    url = lists.whatsapp_url(lists.whatsapp_text(lists.home_items(db)))
    assert url.startswith("https://wa.me/?text=") and "Arroz" in url


def test_weight_summary_and_overview(db):
    body.log_weight(db, Decimal("90"), today() - dt.timedelta(days=60))
    body.log_weight(db, Decimal("87.5"), today() - dt.timedelta(days=31))
    body.log_weight(db, Decimal("85"))
    body.log_weight(db, Decimal("84.8"))  # mismo día: reemplaza
    body.set_goal(db, Decimal("80"))
    s = body.weight_summary(db)
    assert (s["start"].kg, s["current"].kg, s["month_ago"].kg, s["goal"]) == (90, Decimal("84.8"), Decimal("87.5"), 80)
    body.log_food(db, "2 empanadas y una coca")
    assert overview.overview(db)["today"]["meals"] == 1
