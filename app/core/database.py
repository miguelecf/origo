from collections.abc import Iterator

import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def init_db(bind=engine) -> None:
    import app.models  # noqa: F401  registra las tablas

    # Migración aditiva para instalaciones existentes (no borra datos).
    os.umask(0o077)
    Base.metadata.create_all(bind=bind)
    if "expires_at" not in {column["name"] for column in inspect(bind).get_columns("guests")}:
        with bind.begin() as connection:
            connection.execute(text("ALTER TABLE guests ADD COLUMN expires_at DATETIME"))
    if bind.url.database and bind.url.database != ":memory:" and os.path.isfile(bind.url.database):
        os.chmod(bind.url.database, 0o600)
