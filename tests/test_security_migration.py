from sqlalchemy import create_engine, inspect, text

from app.core.database import init_db


def test_existing_database_gets_guest_expiration_without_data_loss(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE guests (id INTEGER PRIMARY KEY, name VARCHAR(80), person VARCHAR(80), token_hash VARCHAR(64) UNIQUE, can_lists BOOLEAN, can_debts BOOLEAN, created_at DATETIME, last_seen_at DATETIME, revoked_at DATETIME)"))
        connection.execute(text("INSERT INTO guests (id, name, token_hash) VALUES (1, 'Existing', 'hash')"))
    init_db(engine)
    init_db(engine)
    assert "expires_at" in {column["name"] for column in inspect(engine).get_columns("guests")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT name, token_hash, expires_at FROM guests")).one() == ("Existing", "hash", None)
    engine.dispose()
