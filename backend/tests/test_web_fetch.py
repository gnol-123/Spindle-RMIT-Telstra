import re

import httpx
import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from app.tools.api import web_fetch
from app.tools.base import ToolContext
from app.tools.registry import get_spec

_UUID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"


def _ctx():
    return ToolContext(node_id=_UUID, name="Web Fetch", config={}, secrets={})


def _run_context() -> RunContext:
    return RunContext(deps=None, model=TestModel(), usage=RunUsage())


def test_registered_as_api():
    spec = get_spec("web_fetch")
    assert spec is not None
    assert spec.kind == "api"


def test_tool_name_is_provider_valid_and_suffixed():
    name = web_fetch.tool_name(_ctx())
    assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name)
    assert name.startswith("web_fetch_")
    assert name.endswith(_UUID.replace("-", "")[:8])


async def test_verify_is_ok_without_network():
    result = await web_fetch.verify(_ctx())
    assert result.ok is True


def test_to_text_strips_script_style_and_tags():
    html = (
        "<html><head><style>p{}</style><script>x()</script></head>"
        "<body><h1>Title</h1><p>Hello   <b>world</b></p></body></html>"
    )
    assert web_fetch.to_text(html) == "Title Hello world"


async def test_rejects_non_http_scheme():
    toolset = web_fetch.build(_ctx())
    tools = await toolset.get_tools(_run_context())
    fn = toolset.tools[next(iter(tools))].function
    out = await fn("file:///etc/passwd")
    assert "http" in out.lower()


async def test_fetch_returns_page_text(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<p>Hi <i>there</i></p>", headers={"content-type": "text/html"}
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(web_fetch, "_transport", lambda: transport)
    monkeypatch.setattr(web_fetch, "_is_public", lambda url: True)

    toolset = web_fetch.build(_ctx())
    tools = await toolset.get_tools(_run_context())
    fn = toolset.tools[next(iter(tools))].function
    assert await fn("https://example.invalid/page") == "Hi there"


async def test_fetch_truncates_long_pages(monkeypatch):
    body = "<p>" + ("word " * 10_000) + "</p>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    monkeypatch.setattr(web_fetch, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(web_fetch, "_is_public", lambda url: True)
    toolset = web_fetch.build(_ctx())
    tools = await toolset.get_tools(_run_context())
    fn = toolset.tools[next(iter(tools))].function
    out = await fn("https://example.invalid/long")
    assert len(out) <= web_fetch._MAX_CHARS + 100
    assert out.endswith("[truncated]")


async def test_http_error_is_returned_as_text_not_raised(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope")

    monkeypatch.setattr(web_fetch, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(web_fetch, "_is_public", lambda url: True)
    toolset = web_fetch.build(_ctx())
    tools = await toolset.get_tools(_run_context())
    fn = toolset.tools[next(iter(tools))].function
    out = await fn("https://example.invalid/missing")
    assert "404" in out


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://[::1]/",
    ],
)
async def test_private_addresses_are_refused(url):
    toolset = web_fetch.build(_ctx())
    tools = await toolset.get_tools(_run_context())
    fn = toolset.tools[next(iter(tools))].function
    assert "not reachable" in await fn(url)


async def test_redirect_to_private_address_is_refused(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.invalid":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
        raise AssertionError("must not follow into private space")

    monkeypatch.setattr(web_fetch, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(web_fetch, "_is_public", lambda url: "127.0.0.1" not in url)
    toolset = web_fetch.build(_ctx())
    tools = await toolset.get_tools(_run_context())
    fn = toolset.tools[next(iter(tools))].function
    assert "not reachable" in await fn("http://public.invalid/start")


async def test_redirect_loop_gives_up(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://public.invalid/again"})

    monkeypatch.setattr(web_fetch, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(web_fetch, "_is_public", lambda url: True)
    toolset = web_fetch.build(_ctx())
    tools = await toolset.get_tools(_run_context())
    fn = toolset.tools[next(iter(tools))].function
    assert "too many redirects" in await fn("http://public.invalid/start")


async def test_byte_cap_drops_the_overflowing_chunk(monkeypatch):
    body = b"x" * (web_fetch._MAX_BYTES + 10)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/html"})

    monkeypatch.setattr(web_fetch, "_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(web_fetch, "_is_public", lambda url: True)
    toolset = web_fetch.build(_ctx())
    tools = await toolset.get_tools(_run_context())
    fn = toolset.tools[next(iter(tools))].function
    out = await fn("http://public.invalid/big")
    assert len(out) <= web_fetch._MAX_CHARS + 20
