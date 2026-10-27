import os
import tempfile

# Antes de importar la app: nunca tocar mentor.db desde los tests.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["MENTOR_DEV_OPEN"] = "0"
os.environ["BASE_URL"] = "http://localhost:8000"
os.environ["SECRET_KEY"] = "test-only-secret-not-for-deployment-12345"
os.environ["GITHUB_CLIENT_ID"] = ""
os.environ["GITHUB_CLIENT_SECRET"] = ""
os.environ["GITHUB_ALLOWED_LOGIN"] = ""
os.environ["MCP_TOKEN"] = ""

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


@pytest.fixture
def anonymous_client(db):
    from fastapi.testclient import TestClient
    from app.core.database import get_db
    from app.main import create_app

    application = create_app()
    application.dependency_overrides[get_db] = lambda: db
    with TestClient(application, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as client:
        yield client


@pytest.fixture
def owner(db):
    from app.services.security import create_user
    return create_user(db, "owner", "correct horse battery staple")


@pytest.fixture
def client(anonymous_client, owner):
    response = anonymous_client.post("/login", data={"username": owner.username, "password": "correct horse battery staple"}, follow_redirects=False)
    assert response.status_code == 303
    return anonymous_client


@pytest.fixture
def anyio_backend():
    return "asyncio"
