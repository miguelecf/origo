import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from app.main import app
from app.mcp_server import mcp

client = TestClient(app)


def test_pages_render():
    for path in ["/", "/plata", "/deudas", "/cuerpo", "/listas", "/dia", "/login"]:
        assert client.get(path).status_code == 200, path


def test_full_flow_through_forms():
    assert client.post("/plata", data={"kind": "expense", "amount": "12.500", "category": "Súper"}).status_code == 200
    assert "12.500" in client.get("/plata").text

    client.post("/deudas", data={"kind": "card", "person": "Juan", "card": "Visa", "total": "120000",
                                 "installments": "6", "first_due": "2026-11-10"})
    page = client.get("/deudas").text
    assert "Juan" in page and "Visa" in page and "(0/6)" in page

    client.post("/cuerpo/peso", data={"kg": "85,4"})
    client.post("/cuerpo/comida", data={"text": "milanesa con puré"})
    assert "milanesa con puré" in client.get("/cuerpo").text

    client.post("/dia", data={"sleep_hours": "7,5", "mood": "4", "movement_min": "30", "note": "bien"})
    assert "Check-in de hoy" not in client.get("/").text

    client.post("/listas/casa", data={"text": "leche, pan"})
    assert "wa.me" in client.get("/listas").text
    client.post("/mercado/empezar")
    page = client.get("/mercado")
    assert page.status_code == 200 and "trip-state" in page.text


def test_login_required_when_password_set(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "APP_PASSWORD", "secreto")
    fresh = TestClient(app)
    assert fresh.get("/", follow_redirects=False).headers["location"] == "/login"
    fresh.post("/login", data={"password": "mal"})
    assert fresh.get("/", follow_redirects=False).status_code == 303
    fresh.post("/login", data={"password": "secreto"})
    assert fresh.get("/").status_code == 200


@pytest.mark.anyio
async def test_mcp_tools():
    async with Client(mcp) as mcp_client:
        names = {t.name for t in await mcp_client.list_tools()}
        assert {"get_overview", "get_debts", "add_transaction", "log_food"} <= names
        await mcp_client.call_tool("add_transaction", {"kind": "expense", "amount": 8500, "category": "Transporte", "note": "nafta"})
        overview = (await mcp_client.call_tool("get_overview", {})).data
        assert overview["finance"]["expense_by_category"]["Transporte"] >= 8500
        prompt = await mcp_client.get_prompt("weekly_review")
        assert "get_overview" in prompt.messages[0].content.text


@pytest.fixture
def anyio_backend():
    return "asyncio"
