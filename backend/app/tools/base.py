"""Shared types for the tool registry."""

import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic_ai.toolsets import AbstractToolset


def is_public_url(url: str) -> bool:
    """False for anything that resolves to loopback, private, link-local or reserved space."""
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return bool(infos)


@dataclass(frozen=True)
class ToolContext:
    """One configured tool node, ready to build a toolset from."""

    node_id: str
    name: str
    config: dict[str, Any]
    # Decrypted. Not logged, not persisted, not sent to the frontend.
    secrets: dict[str, str]


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    detail: str | None = None
    # MCP servers report their tools at connect time, so a client can list them.
    discovered_tools: list[str] | None = None


@dataclass(frozen=True)
class ToolSpec:
    #
    kind: Literal["api", "mcp", "skill", "canvas"]
    build: Callable[[ToolContext], AbstractToolset]
    verify: Callable[[ToolContext], Awaitable[VerifyResult]]
