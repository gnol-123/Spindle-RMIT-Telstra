"""Shared MCP plumbing: build a transport, connect and list tools."""

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlparse

import anyio
import httpx
from fastmcp.exceptions import McpError
from pydantic_ai import ModelRetry
from pydantic_ai.mcp import MCPToolset, StreamableHttpTransport

from app.config import settings
from app.tools.base import ToolContext, VerifyResult, is_public_url

_BLOCKED = "That address is not reachable from here."


def _allowed(url: str) -> bool:
    """http(s) only, and public unless running locally (Obsidian-style bridges)."""
    if urlparse(url).scheme not in ("http", "https"):
        return False
    # ponytail: resolve-then-connect leaves a DNS rebinding window; pin the IP if this matters.
    return settings.environment == "development" or is_public_url(url)


log = logging.getLogger(__name__)

POOL_MAX = 64
POOL_IDLE_S = 600.0

# key -> session kept entered across turns. Key holds a header hash, never raw secrets.
_POOL: OrderedDict[tuple[str, str], "_Pooled"] = OrderedDict()
# Strong refs for fire-and-forget closes.
_CLOSING: set[asyncio.Task] = set()
# Set by verify: explicit connectivity checks skip the pool.
_FRESH: ContextVar[bool] = ContextVar("mcp_fresh", default=False)
# Set by background verify of fresh defaults: verify shares the pooled session.
POOLED_VERIFY: ContextVar[bool] = ContextVar("mcp_pooled_verify", default=False)


def toolset(url: str, headers: dict[str, str]) -> MCPToolset:
    return MCPToolset(StreamableHttpTransport(url, headers=headers))


def _transport(url: str, headers: dict[str, str]) -> Any:
    return StreamableHttpTransport(url, headers=headers)


def _key(url: str, headers: dict[str, str]) -> tuple[str, str]:
    digest = hashlib.sha256(json.dumps(sorted(headers.items())).encode()).hexdigest()
    return url, digest


class _Pooled(MCPToolset):
    """MCPToolset the pool holds entered, so the session and tool list outlive a turn."""

    def __init__(self, url: str, headers: dict[str, str], key: tuple[str, str]) -> None:
        super().__init__(_transport(url, headers))
        self._url = url
        self._headers = headers
        self._key = key
        self._loop = asyncio.get_running_loop()
        self._last_used = time.monotonic()
        self._held = False
        self._evicted = False
        # Healthy replacement after this session died mid-turn.
        self._next: _Pooled | None = None

    async def __aenter__(self):
        try:
            await super().__aenter__()
        except BaseException:
            _evict_now(self)
            raise
        if not self._held and not self._evicted:
            # Pool's own ref; flag first so concurrent enters can't double-hold.
            self._held = True
            await super().__aenter__()
        self._last_used = time.monotonic()
        return self

    async def __aexit__(self, *args: Any) -> bool | None:
        self._last_used = time.monotonic()
        return await super().__aexit__(*args)

    async def list_tools(self):
        try:
            return await super().list_tools()
        except Exception:
            await _evict(self)
            raise

    async def direct_call_tool(self, name: str, args: dict[str, Any], **kwargs: Any) -> Any:
        return await self._call(name, args, retry=True, **kwargs)

    async def _call(self, name: str, args: dict[str, Any], *, retry: bool, **kwargs: Any) -> Any:
        if self._next is not None:
            async with self._next:
                return await self._next.direct_call_tool(name, args, **kwargs)
        try:
            return await super().direct_call_tool(name, args, **kwargs)
        except ModelRetry as exc:
            # Tool-level errors are normal; only protocol errors mean a bad session.
            if not isinstance(exc.__cause__, McpError):
                raise
            await _evict(self)
            if not retry:
                raise
        except Exception as exc:
            await _evict(self)
            # Ambiguous failures may have run the tool; surface, next turn reconnects.
            if not retry or not _unsent(exc):
                raise
        # Request provably never ran: one reconnect, the rest of this turn reuses it.
        self._next = pooled(self._url, self._headers)
        async with self._next:
            if isinstance(self._next, _Pooled):
                return await self._next._call(name, args, retry=False, **kwargs)
            return await self._next.direct_call_tool(name, args, **kwargs)


def _unsent(exc: Exception) -> bool:
    """Failed before the server accepted the call: connect errors, session-expired 404."""
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404


async def _release(ts: _Pooled) -> None:
    if not ts._held:
        return
    ts._held = False
    try:
        await MCPToolset.__aexit__(ts)
    except Exception:
        log.warning("mcp pooled session close failed", exc_info=True)


def _drop(ts: _Pooled) -> None:
    """Forget an entry; close it later if it lives on this loop."""
    ts._evicted = True
    if ts._loop.is_closed():
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if ts._loop is running:
        task = running.create_task(_release(ts))
        _CLOSING.add(task)
        task.add_done_callback(_CLOSING.discard)
    # ponytail: another live loop's entry is dropped unclosed; call_soon_threadsafe if seen


def _evict_now(ts: _Pooled) -> None:
    ts._evicted = True
    if _POOL.get(ts._key) is ts:
        del _POOL[ts._key]


async def _evict(ts: _Pooled) -> None:
    _evict_now(ts)
    # The current run still holds its own ref, so this never closes under it.
    await _release(ts)


def _sweep(now: float) -> None:
    for key, ts in list(_POOL.items()):
        if ts._loop.is_closed() or now - ts._last_used > POOL_IDLE_S:
            del _POOL[key]
            _drop(ts)


def pooled(url: str, headers: dict[str, str]) -> MCPToolset:
    """Toolset reused across turns: one handshake and tools/list per process, not per turn."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return toolset(url, headers)
    if _FRESH.get():
        return toolset(url, headers)
    now = time.monotonic()
    _sweep(now)
    key = _key(url, headers)
    ts = _POOL.get(key)
    if ts is not None:
        if ts._loop is not loop:
            return toolset(url, headers)
        _POOL.move_to_end(key)
        ts._last_used = now
        return ts
    ts = _Pooled(url, headers, key)
    _POOL[key] = ts
    while len(_POOL) > POOL_MAX:
        _, old = _POOL.popitem(last=False)
        _drop(old)
    return ts


async def close_pool() -> None:
    """Shutdown: close every pooled session on this loop."""
    entries = list(_POOL.values())
    _POOL.clear()
    loop = asyncio.get_running_loop()
    for ts in entries:
        ts._evicted = True
        if ts._loop is loop:
            await _release(ts)


def toolset_from_ctx(ctx: ToolContext, *, token_key: str = "auth_token") -> MCPToolset:  # noqa: S107
    """Build a toolset from ctx.config['url'] plus a bearer token secret."""
    url = str(ctx.config.get("url") or "")
    if not _allowed(url):
        raise ValueError(_BLOCKED)
    headers: dict[str, str] = dict(ctx.config.get("headers") or {})
    token = ctx.secrets.get(token_key, "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return pooled(url, headers)


async def verify_toolset(url: str, build_toolset) -> VerifyResult:
    """Connect and list tools. Shared by every MCP service's verify.

    Takes a zero-arg builder, not a built toolset, so a missing url is caught
    before StreamableHttpTransport ever gets a chance to reject it.
    """
    if not url.strip():
        return VerifyResult(ok=False, detail="Missing server URL.")
    if not await anyio.to_thread.run_sync(_allowed, url):
        return VerifyResult(ok=False, detail=_BLOCKED)
    token = _FRESH.set(not POOLED_VERIFY.get())
    try:
        built = build_toolset()
    finally:
        _FRESH.reset(token)
    try:
        async with built:
            tools = await built.list_tools()
    except Exception as exc:
        return VerifyResult(ok=False, detail=f"Could not connect: {type(exc).__name__}")
    names = sorted(t.name for t in tools)
    return VerifyResult(
        ok=True,
        detail=f"Connected. {len(names)} tools available.",
        discovered_tools=names,
    )
