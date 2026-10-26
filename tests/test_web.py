import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from app.main import app
from app.mcp_server import mcp

client = TestClient(app)


def test_pages_render():
    for path in ["/", "/plata", "/deudas", "/cuerpo", "/super", "/super/compra", "/dia", "/invitados", "/login"]:
        assert client.get(path).status_code == 200, path


def test_full_flow_through_forms():
    assert client.post("/plata", data={"kind": "expense", "amount": "12.500", "category": "Súper"}).status_code == 200
    assert "12.500" in client.get("/plata").text

    client.post("/deudas", data={"kind": "card", "person": "Juan", "card": "Visa", "total": "120000",
                                 "installments": "6", "first_due": "2026-11-10"})
    page = client.get("/deudas").text
    assert "Juan" in page and "Visa" in page and "<small>0/6</small>" in page

    client.post("/cuerpo/peso", data={"kg": "85,4"})
    client.post("/cuerpo/comida", data={"text": "milanesa con puré"})
    assert "milanesa con puré" in client.get("/cuerpo").text

    client.post("/dia", data={"sleep_hours": "7,5", "mood": "4", "movement_min": "30", "note": "bien"})
    assert "Check-in de hoy" not in client.get("/").text

    client.post("/super/casa", data={"text": "leche, pan"})
    assert "wa.me" in client.get("/super").text
    client.post("/super/compra/empezar", data={"from_list": "true"})
    page = client.get("/super/compra")
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


def test_guest_magic_link_permissions():
    import re

    client.post("/deudas", data={"kind": "owed_to_me", "person": "Sofi", "total": "30000", "installments": "3"})
    page = client.post("/invitados", data={"name": "Sofi", "can_lists": "true", "can_debts": "true"}).text
    token = re.search(r"/g/([\w-]+)", page).group(1)

    guest = TestClient(app)
    assert guest.get(f"/g/{token}", follow_redirects=False).headers["location"] == "/super"
    # Lo mío no lo ve.
    for path in ["/", "/plata", "/cuerpo", "/dia", "/invitados"]:
        assert guest.get(path, follow_redirects=False).status_code == 303, path
    page = guest.get("/deudas").text
    assert "Hola, Sofi" in page and "Juan" not in page

    ids = re.findall(r'name="installment_ids" value="(\d+)"', page)
    guest.post("/deudas/avisar", data={"installment_ids": ids[:2], "message": "te transferí"})
    assert "esperando a" in guest.get("/deudas").text
    # Un invitado no puede resolver su propio aviso.
    assert guest.post("/deudas/avisos/1", data={"accept": "true"}, follow_redirects=False).status_code == 303

    home = client.get("/").text
    assert "Sofi" in home and "te transferí" in home
    claim_id = re.search(r'action="/deudas/avisos/(\d+)"', home).group(1)
    client.post(f"/deudas/avisos/{claim_id}", data={"accept": "true", "back": "/"})
    assert "confirmó que le llegó" in guest.get("/deudas").text

    # Su compra va aparte y no se carga como gasto mío.
    guest.post("/super/compra/empezar", data={"from_list": "false"})
    assert guest.get("/super/compra").status_code == 200


def test_guest_without_debts_scope():
    import re

    page = client.post("/invitados", data={"name": "Vecino", "can_lists": "true"}).text
    token = re.search(r"/g/([\w-]+)", page).group(1)
    guest = TestClient(app)
    guest.get(f"/g/{token}")
    assert guest.get("/deudas", follow_redirects=False).headers["location"] == "/super"
    assert "ya no funciona" in guest.get("/g/token-falso").text


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
