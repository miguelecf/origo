import datetime as dt

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.database import Base


class Guest(Base):
    """Alguien con link mágico: puede usar el súper y/o ver sus deudas conmigo."""

    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    # Nombre con el que aparece en Deudas (puede ser distinto: "Ana" vs "Ana López").
    person: Mapped[str] = mapped_column(String(80), default="")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    can_lists: Mapped[bool] = mapped_column(default=False)
    can_debts: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=now)
    last_seen_at: Mapped[dt.datetime | None]
    revoked_at: Mapped[dt.datetime | None]
    expires_at: Mapped[dt.datetime | None]


claim_installments = Table(
    "claim_installments",
    Base.metadata,
    Column("claim_id", ForeignKey("payment_claims.id"), primary_key=True),
    Column("installment_id", ForeignKey("installments.id"), primary_key=True),
)


class PaymentClaim(Base):
    """'Ya te pagué esta y esta': aviso de un invitado que yo confirmo o rechazo."""

    __tablename__ = "payment_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    message: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | confirmed | rejected
    reply: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[dt.datetime] = mapped_column(default=now)
    resolved_at: Mapped[dt.datetime | None]

    guest: Mapped[Guest] = relationship()
    installments: Mapped[list["Installment"]] = relationship(  # noqa: F821
        secondary=claim_installments, order_by="Installment.number"
    )
