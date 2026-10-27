import datetime as dt
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.database import Base


class Debt(Base):
    __tablename__ = "debts"

    id: Mapped[int] = mapped_column(primary_key=True)
    person: Mapped[str] = mapped_column(String(80))
    direction: Mapped[str] = mapped_column(String(12))  # owed_to_me | i_owe
    # Con quién: una persona, una tarjeta de crédito o una entidad (Mercado Pago, un banco...).
    kind: Mapped[str] = mapped_column(String(12), default="person", server_default="person")
    brand: Mapped[str | None] = mapped_column(String(32))  # logo en static/brands/<brand>.png
    description: Mapped[str] = mapped_column(String(200), default="")
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Une los dos lados de una tarjeta prestada: lo que me debe la persona y lo que le debo al banco.
    group_id: Mapped[str | None] = mapped_column(String(32), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=now)

    installments: Mapped[list["Installment"]] = relationship(
        back_populates="debt", cascade="all, delete-orphan", order_by="Installment.number"
    )


class Installment(Base):
    __tablename__ = "installments"

    id: Mapped[int] = mapped_column(primary_key=True)
    debt_id: Mapped[int] = mapped_column(ForeignKey("debts.id"), index=True)
    number: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    due_date: Mapped[dt.date | None] = mapped_column(index=True)
    paid_on: Mapped[dt.date | None]
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"))

    debt: Mapped[Debt] = relationship(back_populates="installments")
