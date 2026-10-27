import datetime as dt
import uuid
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import add_months, today
from app.models import Debt, Installment, Transaction
from app.services.finance import new_transaction
from app.services import brands

DIRECTIONS = {"owed_to_me": "Me debe", "i_owe": "Le debo"}


def split_amount(total: Decimal, parts: int) -> list[Decimal]:
    """Reparte en cuotas iguales; los centavos que sobran van a la última."""
    total = Decimal(total)
    base = (total / parts).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    amounts = [base] * parts
    amounts[-1] += total - base * parts
    return amounts


def _build_debt(
    *, person: str, direction: str, total: Decimal, installments: int,
    first_due: dt.date | None, description: str, group_id: str | None = None,
    kind: str = "person", brand: str | None = None,
) -> Debt:
    if kind not in {"person", "card", "entity"}:
        raise ValueError("Elegí persona, tarjeta o entidad")
    brand = brand or None
    if kind == "person" and brand:
        raise ValueError("Una persona no lleva marca")
    if brand and brand not in brands.CATALOGS.get(kind, {}):
        raise ValueError("La marca no corresponde al tipo de deuda")
    if kind != "person" and direction != "i_owe":
        raise ValueError("Tarjetas y entidades solo pueden ser deudas que debés")
    if kind == "card" and (not brand or first_due is None):
        raise ValueError("Elegí la marca y el primer vencimiento de la tarjeta")
    person = person.strip() or brands.label(brand)
    if not person:
        raise ValueError("Poné un nombre")
    if direction not in DIRECTIONS:
        raise ValueError("direction debe ser 'owed_to_me' o 'i_owe'")
    if not isinstance(installments, int) or isinstance(installments, bool) or installments < 1:
        raise ValueError("Tiene que haber al menos una cuota")
    if not Decimal(total).is_finite() or Decimal(total) <= 0:
        raise ValueError("El monto tiene que ser mayor a cero")
    debt = Debt(
        person=person.strip(), direction=direction, total=Decimal(total),
        description=description.strip(), group_id=group_id, kind=kind, brand=brand,
    )
    for i, amount in enumerate(split_amount(total, installments)):
        debt.installments.append(Installment(
            number=i + 1, amount=amount,
            due_date=add_months(first_due, i) if first_due else None,
        ))
    return debt


def create_debt(
    db: Session, *, person: str, direction: str, total: Decimal,
    installments: int = 1, first_due: dt.date | None = None, description: str = "",
    kind: str = "person", brand: str | None = None,
) -> Debt:
    debt = _build_debt(
        person=person, direction=direction, total=total, installments=installments,
        first_due=first_due, description=description, kind=kind, brand=brand,
    )
    db.add(debt)
    db.commit()
    return debt


def create_card_loan(
    db: Session, *, person: str, card: str, total: Decimal, installments: int,
    first_due: dt.date, description: str = "", brand: str | None = None,
) -> tuple[Debt, Debt]:
    """Tarjeta prestada: la persona me debe las cuotas y yo se las debo al banco."""
    group_id = uuid.uuid4().hex
    common = dict(
        total=total, installments=installments, first_due=first_due,
        description=description, group_id=group_id,
    )
    owed = _build_debt(person=person, direction="owed_to_me", **common)
    if not brand:
        brand = next((slug for slug, name in brands.CARDS.items() if card.lower().startswith(name.lower())), None)
    owing = _build_debt(person=card, direction="i_owe", kind="card", brand=brand, **common)
    db.add_all([owed, owing])
    db.commit()
    return owed, owing


def set_installment_paid(db: Session, installment_id: int, paid: bool, on: dt.date | None = None) -> Installment:
    """Marca una cuota y la registra en Finanzas (ingreso si me pagan, gasto si pago yo)."""
    inst = db.get(Installment, installment_id)
    if inst is None:
        raise ValueError("No existe esa cuota")
    if paid and inst.paid_on is None:
        debt = inst.debt
        tx = new_transaction(
            kind="income" if debt.direction == "owed_to_me" else "expense",
            amount=inst.amount, category="Deudas", date=on or today(),
            note=f"Cuota {inst.number}/{len(debt.installments)} de {debt.person}", source="installment",
        )
        db.add(tx)
        db.flush()
        inst.paid_on, inst.transaction_id = tx.date, tx.id
    elif not paid and inst.paid_on is not None:
        if inst.transaction_id:
            tx = db.get(Transaction, inst.transaction_id)
            if tx:
                db.delete(tx)
        inst.paid_on, inst.transaction_id = None, None
    db.commit()
    return inst


def delete_debt(db: Session, debt_id: int) -> None:
    """Borra la deuda (y su otro lado si es tarjeta prestada). Los pagos ya registrados quedan en Finanzas."""
    debt = db.get(Debt, debt_id)
    if debt is None:
        return
    targets = [debt]
    if debt.group_id:
        targets = list(db.scalars(select(Debt).where(Debt.group_id == debt.group_id)))
    for d in targets:
        db.delete(d)
    db.commit()


def remaining(debt: Debt) -> Decimal:
    return sum((i.amount for i in debt.installments if i.paid_on is None), Decimal(0))


def list_debts(db: Session, include_settled: bool = False) -> list[Debt]:
    debts = db.scalars(
        select(Debt).options(selectinload(Debt.installments)).order_by(Debt.created_at.desc())
    ).all()
    return [d for d in debts if include_settled or remaining(d) > 0]


def balances(db: Session) -> dict:
    debts = list_debts(db)
    return {
        "owed_to_me": sum((remaining(d) for d in debts if d.direction == "owed_to_me"), Decimal(0)),
        "i_owe": sum((remaining(d) for d in debts if d.direction == "i_owe"), Decimal(0)),
        "by_kind": {
            kind: {
                direction: sum((remaining(d) for d in debts if d.kind == kind and d.direction == direction), Decimal(0))
                for direction in DIRECTIONS
            }
            for kind in ("person", "card", "entity")
        },
    }


def next_due(debt: Debt) -> dt.date | None:
    return min((i.due_date for i in debt.installments if i.paid_on is None and i.due_date), default=None)


def debt_groups(db: Session, settled: bool = False) -> list[dict]:
    visible = [d for d in list_debts(db, include_settled=settled) if (remaining(d) == 0) == settled]
    return [
        {"title": title, "debts": selected, "subtotal": sum((remaining(d) for d in selected), Decimal(0))}
        for title, kind, direction in (
            ("Te deben", "person", "owed_to_me"), ("Tarjetas", "card", "i_owe"),
            ("Entidades", "entity", "i_owe"), ("Le debés a personas", "person", "i_owe"),
        )
        for selected in [[d for d in visible if d.kind == kind and d.direction == direction]]
    ]


def create_from_form(
    db: Session, *, kind: str, direction: str | None, person: str, total: Decimal,
    installments: int, first_due: dt.date | None, description: str, card: str, brand: str | None,
):
    """Acepta también los formularios anteriores, abiertos antes de actualizar la app."""
    if direction is None:
        if kind == "card":
            kind, direction = "person", "card_loan"
        elif kind in DIRECTIONS:
            kind, direction = "person", kind
    if direction == "card_loan":
        if kind != "person":
            raise ValueError("Solo podés prestarle tu tarjeta a una persona")
        return create_card_loan(
            db, person=person, card=card, total=total, installments=installments,
            first_due=first_due, description=description, brand=brand,
        )
    return create_debt(
        db, person=person, direction=direction, kind=kind, brand=brand, total=total,
        installments=installments, first_due=first_due, description=description,
    )


def due_until(db: Session, until: dt.date) -> list[Installment]:
    """Cuotas sin pagar que vencen hasta `until` (incluye las atrasadas)."""
    return list(db.scalars(
        select(Installment).join(Debt)
        .options(selectinload(Installment.debt).selectinload(Debt.installments))
        .where(Installment.paid_on.is_(None), Installment.due_date.is_not(None), Installment.due_date <= until)
        .order_by(Installment.due_date)
    ))


def upcoming_installments(db: Session, limit: int = 3) -> list[Installment]:
    """Primeros vencimientos pendientes, incluyendo atrasados y fechas fuera de esta semana."""
    return list(db.scalars(
        select(Installment).join(Debt)
        .options(selectinload(Installment.debt))
        .where(Installment.paid_on.is_(None), Installment.due_date.is_not(None))
        .order_by(Installment.due_date, Installment.id).limit(limit)
    ))


def card_alerts(db: Session, until: dt.date) -> list[dict]:
    """Cuotas de tarjeta que tengo que pagar hasta `until` y que la otra persona todavía no me pagó."""
    alerts = []
    for inst in due_until(db, until):
        debt = inst.debt
        if debt.direction != "i_owe" or not debt.group_id:
            continue
        other = db.scalar(select(Debt).where(Debt.group_id == debt.group_id, Debt.id != debt.id))
        if other is None:
            continue
        twin = next((i for i in other.installments if i.number == inst.number), None)
        if twin and twin.paid_on is None:
            alerts.append({"person": other.person, "card": debt.person, "installment": inst, "twin": twin})
    return alerts
