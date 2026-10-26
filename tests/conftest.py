import os
import tempfile

# Antes de importar la app: nunca tocar mentor.db desde los tests.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["APP_PASSWORD"] = ""
os.environ["GITHUB_CLIENT_ID"] = ""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import init_db


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
