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

    os.umask(0o077)
    Base.metadata.create_all(bind=bind)
    _add_missing_columns(bind)
    if bind.url.database and bind.url.database != ":memory:" and os.path.isfile(bind.url.database):
        os.chmod(bind.url.database, 0o600)


def _add_missing_columns(bind) -> None:
    """Sin migraciones: create_all no toca tablas que ya existen, así que las columnas nuevas
    se agregan acá. Solo sirve para columnas que admiten NULL o tienen server_default."""
    existing = inspect(bind)
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in existing.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(bind.dialect)}"
                if column.server_default is not None:
                    ddl += f" DEFAULT {column.server_default.arg!r}"
                conn.execute(text(ddl))
