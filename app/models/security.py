import datetime as dt

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(default="owner")
    totp_secret: Mapped[str | None]
    totp_last_step: Mapped[int] = mapped_column(default=-1)
    created_at: Mapped[dt.datetime] = mapped_column(default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(default=now, onupdate=now)


class WebSession(Base):
    __tablename__ = "web_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    guest_id: Mapped[int | None] = mapped_column(ForeignKey("guests.id"))
    guest_token_hash: Mapped[str | None]
    created_at: Mapped[dt.datetime] = mapped_column(default=now)
    last_seen_at: Mapped[dt.datetime] = mapped_column(default=now)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    failures: Mapped[int] = mapped_column(default=0)
    blocked_until: Mapped[dt.datetime | None]
    updated_at: Mapped[dt.datetime] = mapped_column(default=now)
