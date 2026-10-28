import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.models import Installment, Transaction

INCOME_CATEGORIES = ["Sueldo", "Extra", "Deudas", "Otros"]
EXPENSE_CATEGORIES = [
    "Súper", "Comida afuera", "Casa", "Servicios", "Transporte",
    "Salud", "Ocio", "Ropa", "Suscripciones", "Deudas", "Otros",
]


def new_transaction(
    *, kind: str, amount: Decimal, category: str, date: dt.date | None = None,
    note: str = "", source: str = "manual",
) -> Transaction:
    if kind not in ("income", "expense"):
        raise ValueError("kind debe ser 'income' o 'expense'")
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("El monto tiene que ser mayor a cero")
    return Transaction(
        kind=kind, amount=amount, category=category.strip() or "Otros",
        date=date or today(), note=note.strip(), source=source,
    )


def add_transaction(db: Session, **fields) -> Transaction:
    tx = new_transaction(**fields)
    db.add(tx)
    db.commit()
    return tx


def delete_transaction(db: Session, transaction_id: int) -> None:
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        return
    # Si era el pago de una cuota, la cuota vuelve a quedar pendiente.
    for inst in db.scalars(select(Installment).where(Installment.transaction_id == tx.id)):
        inst.paid_on = None
        inst.transaction_id = None
    db.delete(tx)
    db.commit()


def list_transactions(
    db: Session, start: dt.date, end: dt.date, category: str | None = None
) -> list[Transaction]:
    """Movimientos con start <= fecha < end, del más nuevo al más viejo."""
    q = select(Transaction).where(Transaction.date >= start, Transaction.date < end)
    if category:
        q = q.where(Transaction.category == category)
    return list(db.scalars(q.order_by(Transaction.date.desc(), Transaction.id.desc())))


def summary(db: Session, start: dt.date, end: dt.date) -> dict:
    rows = db.execute(
        select(Transaction.kind, Transaction.category, func.sum(Transaction.amount))
        .where(Transaction.date >= start, Transaction.date < end)
        .group_by(Transaction.kind, Transaction.category)
    ).all()
    income = sum((Decimal(t) for k, _, t in rows if k == "income"), Decimal(0))
    expense = sum((Decimal(t) for k, _, t in rows if k == "expense"), Decimal(0))
    by_category = sorted(
        ((c, Decimal(t)) for k, c, t in rows if k == "expense"), key=lambda r: r[1], reverse=True
    )
    return {"income": income, "expense": expense, "balance": income - expense, "by_category": by_category}
