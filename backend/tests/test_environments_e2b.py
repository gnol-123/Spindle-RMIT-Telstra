"""The E2B control plane: provision, connect, verify, teardown.

No network: AsyncSandbox is monkeypatched. The one real sandbox check is a
manual step in the plan, not a test.
"""

import pytest
from e2b import NotFoundException, SandboxException

from app.environments import e2b as e2b_env
from app.environments.base import WORKSPACE_ROOT, EnvContext, EnvSpec
from app.environments.registry import get_spec
from tests.fakes_e2b import FakeSandbox

_NODE = "11111111-1111-1111-1111-111111111111"
_PROJECT = "22222222-2222-2222-2222-222222222222"
_AGENT = "33333333-3333-3333-3333-333333333333"


def _ctx(**over) -> EnvContext:
    base = {
        "node_id": _NODE,
        "project_id": _PROJECT,
        "name": "Scratch Space",
        "config": {"runtime": "e2b", "role": "scratch", "sandbox_id": "sbx_1"},
        "status": "ready",
    }
    base.update(over)
    return EnvContext(**base)


# -- EnvContext --------------------------------------------------------------


def test_agent_dir_is_the_agent_subdirectory():
    ctx = _ctx(agent_node_id=_AGENT)
    assert ctx.agent_dir == f"{WORKSPACE_ROOT}/{_AGENT}"


def test_agent_dir_without_an_agent_is_the_workspace_root():
    """Browsing endpoints have no agent, so they see the whole workspace."""
    assert _ctx().agent_dir == WORKSPACE_ROOT


def test_sandbox_id_absent_or_blank_is_none():
    assert _ctx(config={"runtime": "e2b"}).sandbox_id is None
    assert _ctx(config={"sandbox_id": ""}).sandbox_id is None


def test_idle_timeout_falls_back_to_the_setting():
    from app.config import settings

    assert _ctx().idle_timeout_s == settings.environment_idle_timeout_s
    assert _ctx(config={"idle_timeout_s": 900}).idle_timeout_s == 900


def test_template_falls_back_to_the_setting():
    from app.config import settings

    assert _ctx().template == settings.e2b_template
    assert _ctx(config={"template": "custom"}).template == "custom"


# -- registry ----------------------------------------------------------------


def test_registry_resolves_e2b():
    spec = get_spec("e2b")
    assert isinstance(spec, EnvSpec)
    assert spec.runtime == "e2b"


def test_registry_returns_none_for_an_unknown_runtime():
    """A 'local' node must degrade, not crash a turn."""
    assert get_spec("local") is None
    assert get_spec("") is None


# -- provision ---------------------------------------------------------------


@pytest.mark.anyio
async def test_provision_creates_the_workspace_and_returns_the_id(monkeypatch):
    fake = FakeSandbox("sbx_new")
    created: dict = {}

    async def _create(**kwargs):
        created.update(kwargs)
        return fake

    monkeypatch.setattr(e2b_env.AsyncSandbox, "create", _create)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")

    sandbox_id = await e2b_env.provision(_ctx(config={"runtime": "e2b", "role": "user"}))

    assert sandbox_id == "sbx_new"
    assert ("make_dir", WORKSPACE_ROOT) in fake.calls
    assert created["metadata"]["node_id"] == _NODE
    assert created["metadata"]["project_id"] == _PROJECT
    assert created["metadata"]["app"] == "murud"
    assert created["lifecycle"]["on_timeout"] == "pause"
    assert created["api_key"] == "test-key"


@pytest.mark.anyio
async def test_provision_without_a_key_raises_before_calling_e2b(monkeypatch):
    called = False

    async def _create(**_k):
        nonlocal called
        called = True
        return FakeSandbox()

    monkeypatch.setattr(e2b_env.AsyncSandbox, "create", _create)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "")

    with pytest.raises(RuntimeError, match="E2B_API_KEY"):
        await e2b_env.provision(_ctx())
    assert called is False


@pytest.mark.anyio
async def test_provision_kills_the_sandbox_if_setup_fails(monkeypatch):
    """A sandbox we could not finish setting up must not be leaked."""
    fake = FakeSandbox("sbx_doomed")
    fake.raise_on_make_dir = SandboxException("disk full")

    async def _create(**_k):
        return fake

    monkeypatch.setattr(e2b_env.AsyncSandbox, "create", _create)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")

    with pytest.raises(SandboxException):
        await e2b_env.provision(_ctx())
    assert fake.killed is True


@pytest.mark.anyio
async def test_provision_omits_auto_resume_when_disabled(monkeypatch):
    fake = FakeSandbox()
    created: dict = {}

    async def _create(**kwargs):
        created.update(kwargs)
        return fake

    monkeypatch.setattr(e2b_env.AsyncSandbox, "create", _create)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")
    monkeypatch.setattr(e2b_env.settings, "e2b_auto_resume", False)

    await e2b_env.provision(_ctx())
    assert "auto_resume" not in created["lifecycle"]


# -- connect -----------------------------------------------------------------


@pytest.mark.anyio
async def test_connect_pushes_the_deadline(monkeypatch):
    """The E2B timeout is wall clock, so every use has to extend it."""
    fake = FakeSandbox()
    seen: dict = {}

    async def _connect(sandbox_id, **kwargs):
        seen["sandbox_id"] = sandbox_id
        seen.update(kwargs)
        return fake

    monkeypatch.setattr(e2b_env.AsyncSandbox, "connect", _connect)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")

    ctx = _ctx(config={"sandbox_id": "sbx_1", "idle_timeout_s": 600})
    sbx = await e2b_env.connect(ctx)

    assert sbx is fake
    assert seen["sandbox_id"] == "sbx_1"
    assert fake.timeouts == [600]


@pytest.mark.anyio
async def test_connect_without_a_sandbox_id_raises_not_found(monkeypatch):
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")
    with pytest.raises(NotFoundException):
        await e2b_env.connect(_ctx(config={"runtime": "e2b"}))


# -- verify ------------------------------------------------------------------


@pytest.mark.anyio
async def test_verify_ok_when_the_sandbox_is_running(monkeypatch):
    fake = FakeSandbox()

    async def _connect(sandbox_id, **_k):
        return fake

    monkeypatch.setattr(e2b_env.AsyncSandbox, "connect", _connect)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")

    result = await e2b_env.verify(_ctx())
    assert result.ok is True
    assert "running" in (result.detail or "").lower()


@pytest.mark.anyio
async def test_verify_reports_a_missing_sandbox_without_raising(monkeypatch):
    async def _connect(sandbox_id, **_k):
        raise NotFoundException("gone")

    monkeypatch.setattr(e2b_env.AsyncSandbox, "connect", _connect)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")

    result = await e2b_env.verify(_ctx())
    assert result.ok is False
    assert "not found" in (result.detail or "").lower()


@pytest.mark.anyio
async def test_verify_with_no_sandbox_id_says_start_it():
    result = await e2b_env.verify(_ctx(config={"runtime": "e2b"}))
    assert result.ok is False
    assert "start" in (result.detail or "").lower()


@pytest.mark.anyio
async def test_verify_reports_an_unexpected_error_as_its_type(monkeypatch):
    async def _connect(sandbox_id, **_k):
        raise ValueError("something odd")

    monkeypatch.setattr(e2b_env.AsyncSandbox, "connect", _connect)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")

    result = await e2b_env.verify(_ctx())
    assert result.ok is False
    assert "ValueError" in (result.detail or "")


@pytest.mark.anyio
async def test_verify_detail_is_capped(monkeypatch):
    """status_detail goes in a text column and into an API response."""

    async def _connect(sandbox_id, **_k):
        raise ValueError("x" * 2000)

    monkeypatch.setattr(e2b_env.AsyncSandbox, "connect", _connect)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")

    result = await e2b_env.verify(_ctx())
    assert len(result.detail or "") <= 500


# -- teardown ----------------------------------------------------------------


@pytest.mark.anyio
async def test_teardown_kills_by_id(monkeypatch):
    killed: list[str] = []

    async def _kill(sandbox_id, **_k):
        killed.append(sandbox_id)
        return True

    monkeypatch.setattr(e2b_env.AsyncSandbox, "kill", _kill)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")

    await e2b_env.teardown("sbx_1")
    assert killed == ["sbx_1"]


@pytest.mark.anyio
async def test_teardown_swallows_a_missing_sandbox(monkeypatch):
    """Already gone is the desired end state, not an error."""

    async def _kill(sandbox_id, **_k):
        raise NotFoundException("already gone")

    monkeypatch.setattr(e2b_env.AsyncSandbox, "kill", _kill)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")

    await e2b_env.teardown("sbx_1")


# -- publish_preview ---------------------------------------------------------


def _answering(monkeypatch, port=3000):
    from app.environments import workspace

    lp = workspace.ListeningPort(port=port, pid=1, command="node", local_only=False)

    async def _listening(_sbx):
        return [lp]

    async def _web(_sbx, ports):
        return ports

    monkeypatch.setattr(workspace, "_HELD", {})
    monkeypatch.setattr(workspace, "listening_ports", _listening)
    monkeypatch.setattr(workspace, "web_ports", _web)


@pytest.mark.anyio
async def test_publish_preview_records_db_row(monkeypatch):
    sbx = FakeSandbox()

    async def _connect(ctx):
        return sbx

    monkeypatch.setattr(e2b_env, "connect", _connect)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")
    _answering(monkeypatch)
    recorded: list[dict] = []

    async def record(entry):
        recorded.append(entry)

    ctx = _ctx(agent_node_id=_AGENT, record_preview=record)
    result = await e2b_env.build(ctx).tools["publish_preview"].function("Todo app", 3000)

    assert result.startswith("Preview published")
    assert recorded == [{"title": "Todo app", "port": 3000, "path": "/", "agent_node_id": _AGENT}]
    assert not any(c[0] == "write" for c in sbx.calls)


@pytest.mark.anyio
async def test_publish_preview_without_recorder_falls_back_to_file(monkeypatch):
    sbx = FakeSandbox()

    async def _connect(ctx):
        return sbx

    monkeypatch.setattr(e2b_env, "connect", _connect)
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")
    _answering(monkeypatch)

    result = (
        await e2b_env.build(_ctx(agent_node_id=_AGENT))
        .tools["publish_preview"]
        .function("Todo app", 3000)
    )

    assert result.startswith("Preview published")
    assert any(c[0] == "write" for c in sbx.calls)
