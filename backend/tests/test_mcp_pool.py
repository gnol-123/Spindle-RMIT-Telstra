"""MCP session pool. In-memory FastMCP server, no network."""

import asyncio
import contextlib

import anyio
import httpx
import pytest
from fastmcp.client.transports.memory import FastMCPTransport
from fastmcp.exceptions import McpError
from mcp.server.fastmcp import FastMCP
from mcp.types import ErrorData
from pydantic_ai.mcp import MCPToolset

from app.tools.mcp import base

URL = "https://mcp.example/mcp"
H = {"Authorization": "Bearer a"}


class Counter:
    connects = 0
    lists = 0


def _server() -> FastMCP:
    srv = FastMCP("t")

    @srv.tool()
    def echo(x: str) -> str:
        return x

    @srv.tool()
    def boom() -> str:
        raise ValueError("tool failed")

    orig = srv.list_tools

    async def list_tools():
        Counter.lists += 1
        return await orig()

    srv._mcp_server.list_tools()(list_tools)
    return srv


class CountingTransport(FastMCPTransport):
    @contextlib.asynccontextmanager
    async def connect_session(self, **kw):
        Counter.connects += 1
        async with super().connect_session(**kw) as s:
            yield s


@pytest.fixture(autouse=True)
def pool(monkeypatch):
    Counter.connects = Counter.lists = 0
    srv = _server()
    monkeypatch.setattr(base, "_transport", lambda url, headers: CountingTransport(srv))
    base._POOL.clear()
    yield
    base._POOL.clear()


async def _turn(ts, tool: str | None = None):
    async with ts:
        await ts.list_tools()
        if tool:
            return await ts.direct_call_tool(tool, {"x": "hi"})


async def _settle():
    for _ in range(5):
        await asyncio.sleep(0)
    if base._CLOSING:
        await asyncio.gather(*base._CLOSING)


async def test_reused_across_turns():
    a = base.pooled(URL, H)
    await _turn(a, "echo")
    b = base.pooled(URL, H)
    assert b is a
    assert await _turn(b, "echo") == "hi"
    assert Counter.connects == 1
    assert Counter.lists == 1
    assert a.is_running  # pool still holds it
    await base.close_pool()
    assert not a.is_running


async def test_headers_split_sessions_and_key_has_no_secret():
    a = base.pooled(URL, H)
    b = base.pooled(URL, {"Authorization": "Bearer b"})
    assert a is not b
    await _turn(a)
    await _turn(b)
    assert Counter.connects == 2
    assert all("Bearer" not in k[1] for k in base._POOL)
    await base.close_pool()


async def test_idle_eviction_closes(monkeypatch):
    a = base.pooled(URL, H)
    await _turn(a)
    monkeypatch.setattr(base, "POOL_IDLE_S", -1.0)
    b = base.pooled(URL, H)
    await _settle()
    assert b is not a
    assert not a.is_running
    await base.close_pool()


def _failing(exc, calls):
    async def fail(*_a, **_k):
        calls.append(1)
        raise exc

    return fail


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("down"),
        McpError(ErrorData(code=32600, message="Session terminated")),
    ],
)
async def test_unsent_failure_evicts_and_reconnects(monkeypatch, exc):
    a = base.pooled(URL, H)
    await _turn(a)
    calls = []
    monkeypatch.setattr(a.client, "call_tool", _failing(exc, calls))
    # Next turn: same pooled object, call fails, one transparent reconnect.
    assert base.pooled(URL, H) is a
    assert await _turn(a, "echo") == "hi"
    assert calls == [1]
    assert Counter.connects == 2
    assert not a.is_running
    fresh = base.pooled(URL, H)
    assert fresh is not a and fresh is a._next
    assert await _turn(fresh, "echo") == "hi"
    assert Counter.connects == 2
    await base.close_pool()


@pytest.mark.parametrize(
    "exc", [httpx.ReadError("cut"), httpx.ReadTimeout("slow"), anyio.ClosedResourceError()]
)
async def test_ambiguous_failure_evicts_without_retry(monkeypatch, exc):
    a = base.pooled(URL, H)
    await _turn(a)
    calls = []
    monkeypatch.setattr(a.client, "call_tool", _failing(exc, calls))
    with pytest.raises(type(exc)):
        await _turn(a, "echo")
    assert calls == [1]
    assert Counter.connects == 1
    assert not base._POOL
    assert not a.is_running
    # Next turn reconnects.
    b = base.pooled(URL, H)
    assert b is not a
    assert await _turn(b, "echo") == "hi"
    assert Counter.connects == 2
    await base.close_pool()


async def test_reconnect_failure_does_not_loop(monkeypatch):
    a = base.pooled(URL, H)
    await _turn(a)
    calls = []
    fail = _failing(httpx.ConnectError("down"), calls)
    monkeypatch.setattr(MCPToolset, "direct_call_tool", lambda *a, **k: fail())
    with pytest.raises(httpx.ConnectError):
        await _turn(a, "echo")
    assert calls == [1, 1]
    assert Counter.connects == 2
    assert not base._POOL
    await _settle()


async def test_tool_error_keeps_session():
    from pydantic_ai import ModelRetry

    a = base.pooled(URL, H)
    with pytest.raises(ModelRetry):
        async with a:
            await a.direct_call_tool("boom", {})
    assert base.pooled(URL, H) is a
    assert Counter.connects == 1
    await base.close_pool()


async def test_cap_evicts_lru(monkeypatch):
    monkeypatch.setattr(base, "POOL_MAX", 2)
    first = base.pooled(URL, {"k": "1"})
    await _turn(first)
    await _turn(base.pooled(URL, {"k": "2"}))
    await _turn(base.pooled(URL, {"k": "3"}))
    await _settle()
    assert len(base._POOL) == 2
    assert not first.is_running
    await base.close_pool()


async def test_verify_uses_fresh_connection(monkeypatch):
    seen = []

    def build():
        ts = base.pooled(URL, H)
        seen.append(ts)
        return ts

    monkeypatch.setattr(
        base, "toolset", lambda url, headers: MCPToolset(CountingTransport(_server()))
    )
    # URL is fake and won't resolve; skip the SSRF DNS check.
    monkeypatch.setattr(base, "is_public_url", lambda url: True)
    res = await base.verify_toolset(URL, build)
    assert res.ok
    assert not isinstance(seen[0], base._Pooled)
    assert not base._POOL


def test_no_loop_falls_back_to_plain():
    assert not isinstance(base.pooled(URL, H), base._Pooled)
