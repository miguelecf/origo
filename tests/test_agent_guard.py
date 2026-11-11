"""El agente solo ve y escribe lo que Origo permite, y cada escritura queda registrada."""
import datetime as dt

import pytest
from fastmcp import Client
from sqlalchemy.orm import sessionmaker

from app import mcp_server
from app.core.clock import today
from app.core.config import settings
from app.mcp_server import mcp
from app.models import AgentAction
from app.services import agent, body


@pytest.fixture
def shared(db, monkeypatch):
    monkeypatch.setattr(mcp_server, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    return db


async def _tools():
    async with Client(mcp) as client:
        return {tool.name for tool in await client.list_tools()}


async def _call(name, **args):
    async with Client(mcp) as client:
        return await client.call_tool(name, args, raise_on_error=False)


def test_read_tools_are_classified():
    assert agent.is_read("get_overview") and agent.is_read("weekly_review")
    assert not agent.is_read("add_transaction") and not agent.is_read("delete_food_entry")


@pytest.mark.anyio
async def test_deny_hides_and_blocks(shared, monkeypatch):
    monkeypatch.setattr(settings, "MCP_DENY", "delete_*, clear_meal")
    tools = await _tools()
    assert "delete_transaction" not in tools and "clear_meal" not in tools and "set_meal" in tools
    result = await _call("delete_transaction", transaction_id=1)
    assert result.is_error and "deshabilitada" in result.content[0].text


@pytest.mark.anyio
async def test_read_only_mode(shared, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ACCESS", "read")
    tools = await _tools()
    assert "get_overview" in tools and not any(not agent.is_read(t) for t in tools)
    assert (await _call("log_food", text="Pan")).is_error
    assert body.food_log(shared, today(), today() + dt.timedelta(days=1)) == []


@pytest.mark.anyio
async def test_dates_window_and_amount_cap(shared, monkeypatch):
    monkeypatch.setattr(settings, "MCP_MAX_BACKDATE_DAYS", 10)
    monkeypatch.setattr(settings, "MCP_MAX_AMOUNT", 100000)
    base = {"kind": "expense", "category": "Súper"}
    future = await _call("add_transaction", amount=10, date=(today() + dt.timedelta(days=1)).isoformat(), **base)
    old = await _call("add_transaction", amount=10, date=(today() - dt.timedelta(days=11)).isoformat(), **base)
    big = await _call("add_transaction", amount=100001, **base)
    assert "futuro" in future.content[0].text and "10 días" in old.content[0].text and "tope" in big.content[0].text
    assert not (await _call("add_transaction", amount=100000, date=(today() - dt.timedelta(days=10)).isoformat(), **base)).is_error
    log = agent.recent(shared)
    assert [a.ok for a in log] == [True, False, False, False]
    assert log[1].tool == "add_transaction" and "tope" in log[1].error


@pytest.mark.anyio
async def test_weight_jump_is_rejected(shared):
    body.log_weight(shared, 115)
    assert "se aleja mucho" in (await _call("log_weight", kg=95)).content[0].text
    assert not (await _call("log_weight", kg=114.2)).is_error


@pytest.mark.anyio
async def test_writes_per_hour(shared, monkeypatch):
    monkeypatch.setattr(settings, "MCP_MAX_WRITES_PER_HOUR", 2)
    assert not (await _call("log_food", text="A")).is_error
    assert not (await _call("log_food", text="B")).is_error
    third = await _call("log_food", text="C")
    assert third.is_error and "2 escrituras por hora" in third.content[0].text
    assert not (await _call("get_overview")).is_error  # leer no cuenta


@pytest.mark.anyio
async def test_service_errors_reach_the_agent_and_are_logged(shared):
    result = await _call("set_meal", slot="brunch", text="x", weekdays=[0])
    assert result.is_error and "no existe" in result.content[0].text
    action = shared.query(AgentAction).one()
    assert not action.ok and "brunch" in action.args


def test_agent_page_shows_policy_and_log(client, db):
    agent.record(db, "log_food", {"text": "Pan"}, ok=True)
    agent.record(db, "add_transaction", {"amount": 1}, ok=False, error="supera el tope")
    page = client.get("/agente").text
    assert "log_food" in page and "supera el tope" in page and "por hora" in page


@pytest.mark.anyio
async def test_guard_applies_through_the_mounted_http_server(shared, monkeypatch):
    """Hermes entra por /mcp, que monta este mismo servidor: los límites tienen que valer igual."""
    from fastmcp import FastMCP

    monkeypatch.setattr(settings, "MCP_DENY", "delete_*")
    parent = FastMCP("Origo")
    parent.mount(mcp)
    async with Client(parent) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert "delete_transaction" not in names and "log_food" in names
        assert (await client.call_tool("delete_transaction", {"transaction_id": 1}, raise_on_error=False)).is_error
        await client.call_tool("log_food", {"text": "Pan"})
    assert agent.recent(shared)[0].tool == "log_food"
