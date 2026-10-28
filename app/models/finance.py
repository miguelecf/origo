import datetime as dt
from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(10))  # income | expense
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    category: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | market | installment | subscription
    created_at: Mapped[dt.datetime] = mapped_column(default=now)
