"""Identidades, sesiones revocables y límites persistentes. Nunca registra credenciales."""
import datetime as dt
import hashlib
import re
import secrets
import time

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import settings
from app.models import LoginAttempt, User, WebSession
from app.services import guests

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def username_key(username: str) -> str:
    return username.strip().casefold()[:80]


def find_user(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username_key(username)))


def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 1024:
        raise ValueError("La contraseña debe tener entre 12 y 1024 caracteres")


def create_user(db: Session, username: str, password: str) -> User:
    username = username_key(username)
    if not re.fullmatch(r"[a-z0-9_.-]{1,80}", username):
        raise ValueError("Usá letras, números, puntos, guiones o guiones bajos para el usuario")
    validate_password(password)
    if find_user(db, username):
        raise ValueError("Ese usuario ya existe")
    user = User(username=username, password_hash=hasher.hash(password))
    db.add(user)
    db.commit()
    return user


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


def set_password(db: Session, user: User, password: str) -> None:
    validate_password(password)
    user.password_hash = hasher.hash(password)
    db.execute(delete(WebSession).where(WebSession.user_id == user.id))
    db.commit()


def set_totp(db: Session, user: User, secret: str | None) -> None:
    user.totp_secret, user.totp_last_step = secret, -1
    db.execute(delete(WebSession).where(WebSession.user_id == user.id))
    db.commit()


def attempt_keys(ip: str, username: str | None = None, *, guest: bool = False) -> list[str]:
    keys = [("guest:" if guest else "ip:") + digest(ip)]
    if username is not None:
        keys.append("user:" + digest(username_key(username)))
    return keys


def consume_attempt(db: Session, keys: list[str], limit: int = 5) -> bool:
    """Reserva el intento antes del hash; SQLite serializa los incrementos concurrentes."""
    from sqlalchemy.dialects.sqlite import insert

    current = now()
    # Limpiar los contadores cuyo bloqueo ya no puede estar activo.
    db.execute(delete(LoginAttempt).where(LoginAttempt.updated_at < current - dt.timedelta(days=1)))
    db.commit()
    # No crear filas arbitrarias de usuario mientras la IP ya está bloqueada.
    existing = db.get(LoginAttempt, keys[0], populate_existing=True)
    if existing and existing.blocked_until and existing.blocked_until > current:
        return False
    for key in keys:
        db.execute(insert(LoginAttempt).values(key=key, failures=0, updated_at=current).on_conflict_do_nothing())
    rows = [db.get(LoginAttempt, key, populate_existing=True) for key in keys]
    if any(row.blocked_until and row.blocked_until > current for row in rows):
        db.commit()
        return False
    for row in rows:
        if current - row.updated_at > dt.timedelta(days=1):
            row.failures = 0
        row.failures += 1
        row.updated_at = current
        if row.failures >= limit:
            row.blocked_until = current + dt.timedelta(seconds=min(3600, 30 * 2 ** min(row.failures - limit, 7)))
    db.commit()
    return True


def authenticate(db: Session, username: str, password: str, code: str, ip: str) -> tuple[User | None, bool]:
    keys = attempt_keys(ip, username)
    if not consume_attempt(db, keys):
        return None, True
    user = find_user(db, username)
    valid = False
    try:
        valid = hasher.verify(user.password_hash if user else DUMMY_HASH, password[:1024]) and len(password) <= 1024
    except (VerificationError, InvalidHashError):
        pass
    if not valid or not user or user.role != "owner":
        return None, False
    if user.totp_secret:
        code = code.strip()
        if not re.fullmatch(r"[0-9]{6}", code):
            return None, False
        step = int(time.time()) // 30
        totp = pyotp.TOTP(user.totp_secret)
        accepted = next((s for s in (step - 1, step, step + 1) if secrets.compare_digest(totp.at(s * 30), code.strip())), None)
        if accepted is None:
            return None, False
        result = db.execute(update(User).where(User.id == user.id, User.totp_last_step < accepted).values(totp_last_step=accepted))
        db.commit()
        if not result.rowcount:
            return None, False
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(password)
    # No borrar la cuota por IP: solo descontar el login válido que no fue un fallo.
    ip_attempt = db.get(LoginAttempt, keys[0], populate_existing=True)
    if ip_attempt:
        ip_attempt.failures = max(0, ip_attempt.failures - 1)
        if ip_attempt.failures < 5:
            ip_attempt.blocked_until = None
    db.execute(delete(LoginAttempt).where(LoginAttempt.key == keys[1]))
    db.commit()
    return user, False


def revoke_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(WebSession).where(WebSession.token_hash == digest(token)))
        db.commit()


def new_session(db: Session, *, previous: str | None = None, user: User | None = None, guest=None) -> str:
    revoke_session(db, previous)
    token = secrets.token_urlsafe(32)
    db.add(WebSession(token_hash=digest(token), user_id=user.id if user else None,
                      guest_id=guest.id if guest else None, guest_token_hash=guest.token_hash if guest else None))
    db.commit()
    return token


def session_identity(db: Session, token: str | None):
    if not token or len(token) > 128:
        return None
    session = db.get(WebSession, digest(token))
    if not session:
        return None
    current = now()
    if ((current - session.last_seen_at).total_seconds() >= settings.SESSION_IDLE_SECONDS
            or (current - session.created_at).total_seconds() >= settings.SESSION_ABSOLUTE_SECONDS):
        revoke_session(db, token)
        return None
    identity = db.get(User, session.user_id) if session.user_id else guests.active(db, session.guest_id)
    if identity is None or (session.user_id and identity.role != "owner") or (session.guest_id and identity.token_hash != session.guest_token_hash):
        revoke_session(db, token)
        return None
    session.last_seen_at = current
    db.commit()
    return identity
