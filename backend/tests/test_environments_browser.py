"""Browser tools on an mcp environment: assembly, screenshots, session lifetime.

The Playwright MCP server is faked at app.tools.mcp.base.toolset. No live E2B.
"""

from dataclasses import replace

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import BinaryContent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from app.environments import browser
from app.environments import e2b as e2b_env
from app.environments.assembly import ENV_TOOL_NAMES, assemble_environments, env_prefix
from app.environments.base import WORKSPACE_ROOT, EnvContext
from app.environments.browser import BROWSER_TOOL_NAMES
from app.repositories.environment_repo import EnvNode
from tests.fakes_e2b import FakeSandbox

_AGENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_ENV = "11111111-2222-3333-4444-555555555555"
_PROJECT = "99999999-9999-9999-9999-999999999999"


def _auto(_node_id):
    return "auto"


_MCP_CONFIG = {
    "runtime": "e2b",
    "role": "user",
    "sandbox_id": "sbx_1",
    "template": "mcp-gateway",
    "mcp": {"playwright": {}},
}


def _run_ctx() -> RunContext:
    return RunContext(deps=None, model=TestModel(), usage=RunUsage())


def _node(config: dict) -> EnvNode:
    return EnvNode(
        id=_ENV,
        project_id=_PROJECT,
        name="Coding Environment",
        config=config,
        status="ready",
        status_detail=None,
        tool_policy="auto",
        position_x=0.0,
        position_y=0.0,
    )


def _ctx(config: dict | None = None) -> EnvContext:
    return EnvContext(
        node_id=_ENV,
        project_id=_PROJECT,
        name="Coding Environment",
        config=config or _MCP_CONFIG,
        status="ready",
        agent_node_id=_AGENT,
    )


class _Repo:
    def set_status(self, *_a) -> None:
        pass


class FakeMCP:
    """Stands in for MCPToolset. ready_after counts list_tools failures."""

    def __init__(self, result=None, ready_after: int = 0, never_ready: bool = False):
        self.result = result
        self.ready_after = ready_after
        self.never_ready = never_ready
        self.enters = 0
        self.exits = 0
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        self.enters += 1
        return self

    async def __aexit__(self, *_a):
        self.exits += 1

    async def list_tools(self):
        if self.never_ready or self.ready_after > 0:
            self.ready_after -= 1
            raise RuntimeError("playwright not ready")
        return []

    async def direct_call_tool(self, name: str, args: dict):
        self.calls.append((name, args))
        return self.result


@pytest.fixture
def sbx(monkeypatch):
    fake = FakeSandbox()

    async def _connect(ctx):
        return fake

    monkeypatch.setattr(e2b_env, "connect", _connect)
    monkeypatch.setattr(browser, "_RETRY_S", 0.001)
    monkeypatch.setattr(browser, "_READY_S", 0.2)
    return fake


def _use_mcp(monkeypatch, fake: FakeMCP) -> list[tuple]:
    opened: list[tuple] = []

    def _toolset(url, headers):
        opened.append((url, headers))
        return fake

    monkeypatch.setattr(browser.mcp_base, "toolset", _toolset)
    return opened


def _tools(combined) -> dict:
    """name -> function across the env and browser halves."""
    out = {}
    for ts in combined.toolsets:
        inner = getattr(ts, "wrapped", ts)
        out.update({n: t.function for n, t in inner.tools.items()})
    return out


async def _assembled_names(config: dict) -> tuple[set[str], dict[str, str]]:
    assembled = await assemble_environments(
        _Repo(), [_node(config)], agent_node_id=_AGENT, policy_of=_auto
    )
    assert len(assembled.toolsets) == len(assembled.owner_by_toolset) == 1
    tools = await assembled.toolsets[0].get_tools(_run_ctx())
    return set(tools), assembled.owner_by_tool


# -- assembly ----------------------------------------------------------------


async def test_config_without_mcp_gets_no_browser_tools():
    names, _ = await _assembled_names({"runtime": "e2b", "role": "user", "sandbox_id": "sbx_1"})
    prefix = env_prefix("Coding Environment", _ENV)
    assert names == {f"{prefix}_{n}" for n in ENV_TOOL_NAMES}


async def test_config_with_mcp_exposes_browser_tools_with_owners():
    names, owners = await _assembled_names(_MCP_CONFIG)
    prefix = env_prefix("Coding Environment", _ENV)
    expected = {f"{prefix}_{n}" for n in (*ENV_TOOL_NAMES, *BROWSER_TOOL_NAMES)}
    assert len(BROWSER_TOOL_NAMES) == 7
    assert names == expected
    assert all(owners[n] == _ENV for n in expected)


async def test_note_mentions_browser_only_for_mcp():
    with_mcp = await assemble_environments(
        _Repo(), [_node(_MCP_CONFIG)], agent_node_id=_AGENT, policy_of=_auto
    )
    plain = await assemble_environments(
        _Repo(),
        [_node({"runtime": "e2b", "sandbox_id": "sbx_1"})],
        agent_node_id=_AGENT,
        policy_of=_auto,
    )
    assert "172.17.0.1" in with_mcp.notes[0]
    assert "screenshots/" in with_mcp.notes[0]
    assert "172.17.0.1" not in plain.notes[0]


# -- screenshot --------------------------------------------------------------


async def test_screenshot_writes_png_as_user(monkeypatch, sbx):
    fake = FakeMCP(result=["Took screenshot", BinaryContent(data=b"png", media_type="image/png")])
    _use_mcp(monkeypatch, fake)
    ts = e2b_env.build(_ctx())

    async with ts:
        out = await _tools(ts)["browser_screenshot"]("Landing Page!")

    path = f"{WORKSPACE_ROOT}/{_AGENT}/screenshots/landing-page.png"
    assert out.startswith("Saved screenshot:")
    assert path in out
    assert sbx.stored[path] == b"png"
    assert sbx.users[sbx.calls.index(("write", path))] == "user"
    name, args = fake.calls[-1]
    assert name == "playwright-browser_take_screenshot"
    assert "filename" not in args


async def test_screenshot_default_name(monkeypatch, sbx):
    fake = FakeMCP(result=[BinaryContent(data=b"x", media_type="image/png")])
    _use_mcp(monkeypatch, fake)
    ts = e2b_env.build(_ctx())
    async with ts:
        out = await _tools(ts)["browser_screenshot"]("")
    assert out.endswith("/screenshots/shot-1.png")


def test_safe_name():
    assert browser.safe_name("A b/../C", 3) == "a-b-c"
    assert browser.safe_name("", 2) == "shot-2"
    assert len(browser.safe_name("x" * 100, 1)) == 40


# -- session lifetime --------------------------------------------------------


async def test_never_ready_returns_unavailable_and_env_tools_still_work(monkeypatch, sbx):
    _use_mcp(monkeypatch, FakeMCP(never_ready=True))
    sbx.stored[f"{WORKSPACE_ROOT}/{_AGENT}/a.txt"] = "hello"
    ts = e2b_env.build(_ctx())

    async with ts:
        tools = _tools(ts)
        out = await tools["browser_navigate"]("http://172.17.0.1:3000")
        again = await tools["browser_snapshot"]()
        read = await tools["read_file"]("a.txt")

    assert out.startswith("Browser unavailable")
    assert again.startswith("Browser unavailable")
    assert read == "hello"


async def test_one_session_per_run_closed_on_exit(monkeypatch, sbx):
    fake = FakeMCP(result="ok", ready_after=2)
    opened = _use_mcp(monkeypatch, fake)
    ts = e2b_env.build(_ctx())

    async with ts:
        tools = _tools(ts)
        assert await tools["browser_navigate"]("http://172.17.0.1:3000") == "ok"
        assert await tools["browser_click"]("Save button", "e12") == "ok"
        assert fake.exits == 0

    assert len(opened) == 1
    assert opened[0][1] == {"Authorization": "Bearer mcp-token"}
    assert fake.enters == 1
    assert fake.exits == 1
    assert [c[0] for c in fake.calls] == [
        "playwright-browser_navigate",
        "playwright-browser_click",
    ]
    # Playwright MCP names the snapshot ref "target".
    assert fake.calls[1][1] == {"element": "Save button", "target": "e12"}
    # Containers pruned as root on open and again on close: the gateway leaves them running.
    runs = [(c, sbx.users[i]) for i, c in enumerate(sbx.calls) if c[0] == "run"]
    assert [("docker" in c[1], u) for c, u in runs] == [(True, "root"), (True, "root")]


async def test_tool_error_is_returned_as_text(monkeypatch, sbx):
    fake = FakeMCP()

    async def _boom(name, args):
        raise RuntimeError("no such ref")

    fake.direct_call_tool = _boom
    _use_mcp(monkeypatch, fake)
    ts = e2b_env.build(_ctx())
    async with ts:
        out = await _tools(ts)["browser_click"]("x", "e1")
    assert "no such ref" in out


# -- user consistency --------------------------------------------------------


async def test_env_calls_run_as_user(monkeypatch, sbx):
    sbx.run_result = type("R", (), {"exit_code": 0, "stdout": "", "stderr": ""})()
    ts = e2b_env.build(_ctx({"runtime": "e2b", "sandbox_id": "sbx_1"}))
    t = {n: x.function for n, x in ts.tools.items()}
    await t["run_command"]("ls")
    await t["read_file"]("a")
    await t["write_file"]("a", "b")
    await t["list_files"]()
    assert sbx.users and all(u == "user" for u in sbx.users)


async def test_provision_passes_mcp_and_makes_root_as_user(monkeypatch):
    fake = FakeSandbox("sbx_new")
    created: dict = {}

    async def _create(**kwargs):
        created.update(kwargs)
        return fake

    monkeypatch.setattr(e2b_env.AsyncSandbox, "create", _create)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")
    await e2b_env.provision(_ctx({"runtime": "e2b", **_MCP_CONFIG, "sandbox_id": None}))

    assert created["mcp"] == {"playwright": {}}
    assert created["template"] == "mcp-gateway"
    assert fake.users == ["user"]


async def test_provision_falls_back_without_mcp_and_drops_browser(monkeypatch):
    fake = FakeSandbox("sbx_plain")
    calls: list[dict] = []

    async def _create(**kwargs):
        calls.append(kwargs)
        if kwargs.get("mcp"):
            raise RuntimeError("Failed to start MCP gateway")
        return fake

    monkeypatch.setattr(e2b_env.AsyncSandbox, "create", _create)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")
    ctx = _ctx({"runtime": "e2b", **_MCP_CONFIG, "sandbox_id": None})

    assert await e2b_env.provision(ctx) == "sbx_plain"
    assert len(calls) == 2
    assert calls[1]["mcp"] is None
    assert calls[1]["template"] == e2b_env.settings.e2b_template
    # Recorded on the config lifecycle persists, so no browser tools are offered.
    assert "mcp" not in ctx.config
    assert ctx.config["template"] == e2b_env.settings.e2b_template
    assert not hasattr(e2b_env.build(ctx), "toolsets")


async def test_lifecycle_persists_the_mcp_fallback(monkeypatch):
    from app.environments import lifecycle

    async def _create(**kwargs):
        if kwargs.get("mcp"):
            raise RuntimeError("Failed to start MCP gateway")
        return FakeSandbox("sbx_plain")

    monkeypatch.setattr(e2b_env.AsyncSandbox, "create", _create)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")

    class _EnvRepo:
        def __init__(self, node):
            self.node = node

        def try_begin_provisioning(self, _id):
            return True

        def set_config(self, _id, config):
            self.saved = config

        def set_status(self, *_a):
            pass

        def get_environment_nodes(self, ids):
            return [n for n in map(self.get_environment_node, ids) if n is not None]

        def get_environment_node(self, _id):
            return self.node

    node = _node({**_MCP_CONFIG, "sandbox_id": None})
    node = replace(node, status="pending")
    repo = _EnvRepo(node)
    await lifecycle.ensure_provisioned(repo, node)
    assert repo.saved["sandbox_id"] == "sbx_plain"
    assert "mcp" not in repo.saved


def test_user_env_config_has_playwright():
    from app.tools.canvas import _user_env_config

    cfg = _user_env_config()
    assert cfg["mcp"] == {"playwright": {}}
    assert cfg["template"] == "mcp-gateway"


def test_user_env_config_template_follows_setting(monkeypatch):
    from app.config import settings
    from app.tools.canvas import _user_env_config

    monkeypatch.setattr(settings, "e2b_mcp_template", "custom-mcp")
    assert _user_env_config()["template"] == "custom-mcp"


async def test_agent_run_opens_and_closes_one_session(monkeypatch, sbx):
    """pydantic-ai enters the toolset once per run; tool calls run in other tasks."""
    from pydantic_ai import Agent

    fake = FakeMCP(result="ok")
    _use_mcp(monkeypatch, fake)
    model = TestModel(call_tools=["browser_navigate", "browser_snapshot"])
    await Agent(model, toolsets=[e2b_env.build(_ctx())]).run("go")

    assert fake.enters == 1
    assert fake.exits == 1
    assert {c[0] for c in fake.calls} == {
        "playwright-browser_navigate",
        "playwright-browser_snapshot",
    }


# -- thumbnails --------------------------------------------------------------


async def test_screenshot_saves_thumbnail(monkeypatch, sbx):
    fake = FakeMCP(result=[BinaryContent(data=b"png", media_type="image/png")])
    _use_mcp(monkeypatch, fake)
    got: list[bytes] = []

    async def spy(data: bytes) -> None:
        got.append(data)

    ts = e2b_env.build(replace(_ctx(), save_thumbnail=spy))
    async with ts:
        out = await _tools(ts)["browser_screenshot"]("a")
    assert got == [b"png"]
    assert out.startswith("Saved screenshot:")


async def test_screenshot_thumbnail_failure_is_silent(monkeypatch, sbx):
    fake = FakeMCP(result=[BinaryContent(data=b"png", media_type="image/png")])
    _use_mcp(monkeypatch, fake)

    async def boom(data: bytes) -> None:
        raise RuntimeError("storage down")

    ts = e2b_env.build(replace(_ctx(), save_thumbnail=boom))
    async with ts:
        out = await _tools(ts)["browser_screenshot"]("a")
    assert out.startswith("Saved screenshot:")


async def test_save_thumbnail_without_preview_row_skips_upload(monkeypatch):
    from app.environments import assembly

    class Repo:
        def newest_for_env(self, _env):
            return None

    uploads: list = []
    monkeypatch.setattr(
        assembly.previews_storage, "upload_thumbnail", lambda *a: uploads.append(a) or "p"
    )
    await assembly._thumbnail_saver(Repo(), _PROJECT, _ENV)(b"png")
    assert uploads == []


async def test_save_thumbnail_uploads_and_sets_path(monkeypatch):
    from types import SimpleNamespace

    from app.environments import assembly

    set_calls: list = []

    class Repo:
        def newest_for_env(self, _env):
            return SimpleNamespace(id="pv1")

        def set_thumbnail(self, pid, path):
            set_calls.append((pid, path))

    monkeypatch.setattr(
        assembly.previews_storage, "upload_thumbnail", lambda p, i, d: f"{p}/{i}.png"
    )
    await assembly._thumbnail_saver(Repo(), _PROJECT, _ENV)(b"png")
    assert set_calls == [("pv1", f"{_PROJECT}/pv1.png")]
