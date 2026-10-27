import datetime as dt
import hashlib
import secrets
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import now
from app.core.logging import event
from app.core.config import settings
from app.models import Debt, Guest, Installment, PaymentClaim
from app.services import debts


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_guest(
    db: Session, *, name: str, person: str = "", can_lists: bool = False, can_debts: bool = False,
    expires_at: dt.datetime | None = None,
) -> tuple[Guest, str]:
    """Devuelve el invitado y su token. El token no se guarda: solo se puede ver ahora."""
    name = name.strip()
    if not name:
        raise ValueError("Poné un nombre")
    if not (can_lists or can_debts):
        raise ValueError("Elegí al menos una cosa que pueda ver")
    if expires_at is not None and expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(ZoneInfo(settings.TIMEZONE)).replace(tzinfo=None)
    token = secrets.token_urlsafe(24)
    guest = Guest(
        name=name, person=(person.strip() or name), token_hash=_hash(token),
        can_lists=can_lists, can_debts=can_debts, expires_at=expires_at,
    )
    db.add(guest)
    db.commit()
    return guest, token


def rotate_token(db: Session, guest_id: int) -> str:
    """Link nuevo: el anterior deja de funcionar."""
    guest = db.get(Guest, guest_id)
    if guest is None:
        raise ValueError("No existe ese invitado")
    token = secrets.token_urlsafe(24)
    guest.token_hash, guest.revoked_at = _hash(token), None
    db.commit()
    event("guest_link_rotated", guest_id=guest.id)
    return token


def revoke(db: Session, guest_id: int) -> None:
    if guest := db.get(Guest, guest_id):
        guest.revoked_at = now()
        db.commit()
        event("guest_link_revoked", guest_id=guest.id)


def by_token(db: Session, token: str) -> Guest | None:
    guest = db.scalar(select(Guest).where(Guest.token_hash == _hash(token), Guest.revoked_at.is_(None)))
    if guest and (guest.expires_at is None or guest.expires_at > now()):
        guest.last_seen_at = now()
        db.commit()
        return guest
    return None


def active(db: Session, guest_id: int | None) -> Guest | None:
    guest = db.get(Guest, guest_id) if guest_id else None
    return guest if guest and guest.revoked_at is None and (guest.expires_at is None or guest.expires_at > now()) else None


def list_guests(db: Session) -> list[Guest]:
    return list(db.scalars(select(Guest).order_by(Guest.revoked_at.is_not(None), Guest.name)))


# --- Deudas vistas por el invitado ---

def guest_debts(db: Session, guest: Guest) -> list[Debt]:
    """Las deudas entre el invitado y yo (sin el lado del banco de una tarjeta prestada)."""
    return list(db.scalars(
        select(Debt).options(selectinload(Debt.installments))
        .where(func.lower(Debt.person) == guest.person.strip().lower())
        .order_by(Debt.created_at.desc())
    ))


def claimed_installment_ids(db: Session) -> set[int]:
    """Cuotas con un aviso de pago todavía sin responder."""
    return {
        inst.id
        for claim in db.scalars(select(PaymentClaim).where(PaymentClaim.status == "pending"))
        for inst in claim.installments
    }


def create_claim(db: Session, guest: Guest, installment_ids: list[int], message: str = "") -> PaymentClaim:
    """'Ya te pagué esta y esta'. Solo cuotas suyas, que me debe, sin pagar y sin otro aviso pendiente."""
    allowed = {
        i.id: i for d in guest_debts(db, guest) if d.direction == "owed_to_me"
        for i in d.installments if i.paid_on is None
    }
    busy = claimed_installment_ids(db)
    chosen = [allowed[i] for i in dict.fromkeys(installment_ids) if i in allowed and i not in busy]
    if not chosen:
        raise ValueError("Marcá al menos una cuota que todavía figure sin pagar")
    claim = PaymentClaim(guest=guest, message=message.strip()[:300], installments=chosen)
    db.add(claim)
    db.commit()
    return claim


def guest_claims(db: Session, guest: Guest, limit: int = 10) -> list[PaymentClaim]:
    return list(db.scalars(
        select(PaymentClaim).where(PaymentClaim.guest_id == guest.id)
        .order_by(PaymentClaim.created_at.desc()).limit(limit)
    ))


# --- Lo que resuelvo yo ---

def pending_claims(db: Session) -> list[PaymentClaim]:
    return list(db.scalars(
        select(PaymentClaim).options(selectinload(PaymentClaim.installments).selectinload(Installment.debt))
        .where(PaymentClaim.status == "pending").order_by(PaymentClaim.created_at)
    ))


def resolve_claim(db: Session, claim_id: int, accept: bool, reply: str = "") -> PaymentClaim:
    """Confirmar marca las cuotas como cobradas (y entra la plata en Finanzas)."""
    claim = db.get(PaymentClaim, claim_id)
    if claim is None or claim.status != "pending":
        raise ValueError("Ese aviso ya está resuelto")
    if accept:
        for inst in claim.installments:
            if inst.paid_on is None:
                debts.set_installment_paid(db, inst.id, True, on=claim.created_at.date())
    claim.status = "confirmed" if accept else "rejected"
    claim.reply, claim.resolved_at = reply.strip()[:300], now()
    db.commit()
    return claim


def claim_total(claim: PaymentClaim):
    return sum(i.amount for i in claim.installments)
