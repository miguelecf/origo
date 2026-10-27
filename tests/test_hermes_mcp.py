"""Lo que necesita Hermes: MCP solo desde la misma máquina y tools para dar de alta y revisar."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from app.core.clock import today
from app.core.config import settings
from app.core.database import init_db
from app.main import create_app
from app.mcp_server import mcp

TOKEN = "a-secure-static-token-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "hermes", "version": "1"}}}
AUTH = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json, text/event-stream"}


@pytest.fixture
def local_only(monkeypatch):
    monkeypatch.setattr(settings, "MCP_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "MCP_LOCAL_ONLY", True)


def test_local_only_accepts_loopback(local_only):
    with TestClient(create_app(), base_url="http://127.0.0.1:8000", client=("127.0.0.1", 40000)) as client:
        assert client.post("/mcp", headers=AUTH, json=INIT).status_code == 200


@pytest.mark.parametrize("peer, extra", [
    (("203.0.113.9", 40000), {}),
    (("127.0.0.1", 40000), {"CF-Connecting-IP": "203.0.113.9"}),
    (("127.0.0.1", 40000), {"X-Forwarded-For": "203.0.113.9"}),
])
def test_local_only_hides_mcp_from_tunnel(local_only, peer, extra):
    with TestClient(create_app(), base_url="http://127.0.0.1:8000", client=peer) as client:
        for path in ("/mcp", "/mcp/", "/.well-known/oauth-protected-resource"):
            assert client.post(path, headers=AUTH | extra, json=INIT).status_code == 404


def test_local_only_off_keeps_remote_mcp(monkeypatch):
    monkeypatch.setattr(settings, "MCP_TOKEN", TOKEN)
    with TestClient(create_app(), base_url=settings.BASE_URL, client=("203.0.113.9", 40000)) as client:
        assert client.post("/mcp", headers=AUTH, json=INIT).status_code == 200


@pytest.mark.anyio
async def test_hermes_can_register_and_review():
    init_db()
    due = (today() + dt.timedelta(days=3)).isoformat()
    async with Client(mcp) as client:
        async def call(name, **args):
            return (await client.call_tool(name, args)).data

        debt = await call("add_debt", person="", direction="i_owe", total=90000, installments=3,
                          first_due=due, kind="card", brand="naranjax")
        assert debt["person"] == "Naranja X" and len(debt["installments"]) == 3
        assert any(p["debt_id"] == debt["id"] for p in await call("get_due_payments", days=7))

        first = debt["installments"][0]["id"]
        assert (await call("set_installment_paid", installment_id=first))["paid_on"] == today().isoformat()
        assert any(t["category"] == "Deudas" for t in await call("list_transactions"))

        owed, owing = await call("lend_card", person="Ana", card="Brubank", total=30000, installments=2,
                                 first_due=due, brand="brubank")
        assert owed["direction"] == "owed_to_me" and owing["brand"] == "brubank"

        await call("save_checkin", sleep_hours=7.5, mood=4)
        checkin = await call("save_checkin", movement_min=30)
        assert (checkin["sleep_hours"], checkin["mood"], checkin["movement_min"]) == (7.5, 4, 30)

        assert (await call("set_weight_goal", kg=78))["goal_kg"] == 78
        await call("add_to_home_list", items="yerba, pan")
        item = next(i for i in await call("get_home_list") if i["name"] == "yerba")
        toggled = await call("toggle_home_item", item_id=item["id"])
        assert next(i for i in toggled["items"] if i["id"] == item["id"])["done"]

        tx = await call("add_transaction", kind="expense", amount=1500, category="Súper")
        await call("delete_transaction", transaction_id=tx["id"])
        assert all(t["id"] != tx["id"] for t in await call("list_transactions"))


@pytest.mark.anyio
async def test_add_debt_rejects_brand_of_other_kind():
    init_db()
    async with Client(mcp) as client:
        result = await client.call_tool("add_debt", {"person": "", "direction": "i_owe", "total": 1000,
                                                     "kind": "card", "brand": "binance", "first_due": today().isoformat()},
                                        raise_on_error=False)
        assert result.is_error
