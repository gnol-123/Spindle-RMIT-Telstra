"""app.environments.e2b.build(): the four agent facing tools.

Every tool must return a string and never raise. RecordingToolset depends on
that: a raised exception there is recorded as a tool error and interrupts the
turn, whereas a returned string describing a failure lets the model continue.
"""

import pytest
from e2b import CommandExitException, FileNotFoundException, FileType, TimeoutException

from app.config import settings
from app.environments import e2b as e2b_env
from app.environments.assembly import ENV_TOOL_NAMES
from app.environments.base import EnvContext
from tests.fakes_e2b import FakeEntry, FakeSandbox

_NODE = "11111111-1111-1111-1111-111111111111"
_PROJECT = "22222222-2222-2222-2222-222222222222"
_AGENT = "33333333-3333-3333-3333-333333333333"


def _ctx(**over) -> EnvContext:
    status_calls: list[tuple[str, str | None]] = []

    async def set_status(status: str, detail: str | None) -> None:
        status_calls.append((status, detail))

    base = {
        "node_id": _NODE,
        "project_id": _PROJECT,
        "name": "Coding Environment",
        "config": {"runtime": "e2b", "role": "user", "sandbox_id": "sbx_1"},
        "status": "ready",
        "agent_node_id": _AGENT,
        "set_status": set_status,
    }
    base.update(over)
    ctx = EnvContext(**base)
    ctx.__dict__["_status_calls"] = status_calls  # test-only backdoor, frozen dataclass
    return ctx


def _tool(toolset, name):
    """The underlying function behind a FunctionToolset entry."""
    return toolset.tools[name].function


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setattr(e2b_env.settings, "e2b_api_key", "test-key")


def _use_sandbox(monkeypatch, sbx):
    async def _connect(ctx):
        return sbx

    monkeypatch.setattr(e2b_env, "connect", _connect)


def _result(exit_code: int = 0, stdout: str = "", stderr: str = ""):
    return type("R", (), {"exit_code": exit_code, "stdout": stdout, "stderr": stderr})()


# -- run_command ---------------------------------------------------------


@pytest.mark.anyio
async def test_run_command_success_reports_exit_code_and_output(monkeypatch):
    sbx = FakeSandbox()
    sbx.run_result = _result(stdout="hi\n")
    _use_sandbox(monkeypatch, sbx)

    ctx = _ctx()
    result = await _tool(e2b_env.build(ctx), "run_command")("echo hi")

    assert "exit_code: 0" in result
    assert "hi" in result
    assert ("run", "echo hi", ctx.agent_dir, settings.environment_command_timeout_s) in sbx.calls


@pytest.mark.anyio
async def test_run_command_nonzero_exit_is_a_result_not_a_raise(monkeypatch):
    """The confirmed live behaviour: CommandExitException carries the result."""
    sbx = FakeSandbox()
    sbx.raise_on_run = CommandExitException(stdout="", stderr="boom", exit_code=3, error=None)
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(_ctx()), "run_command")("exit 3")

    assert "exit_code: 3" in result
    assert "boom" in result


@pytest.mark.anyio
async def test_run_command_timeout_explains_backgrounding(monkeypatch):
    sbx = FakeSandbox()
    sbx.raise_on_run = TimeoutException("too slow")
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(_ctx()), "run_command")("sleep 999")

    assert "timed out" in result.lower()
    assert "nohup" in result.lower()


@pytest.mark.anyio
async def test_run_command_unavailable_when_connect_fails(monkeypatch):
    async def _connect(ctx):
        raise ConnectionError("network down")

    monkeypatch.setattr(e2b_env, "connect", _connect)

    ctx = _ctx(status="ready")
    result = await _tool(e2b_env.build(ctx), "run_command")("echo hi")

    assert "unavailable" in result.lower()
    assert ctx.__dict__["_status_calls"] == [("error", "ConnectionError: network down")]


@pytest.mark.anyio
async def test_run_command_self_heals_status_from_error(monkeypatch):
    """A previously errored node that connects again is reported ready."""
    sbx = FakeSandbox()
    sbx.run_result = _result()
    _use_sandbox(monkeypatch, sbx)

    ctx = _ctx(status="error")
    await _tool(e2b_env.build(ctx), "run_command")("echo hi")

    assert ("ready", "Sandbox running") in ctx.__dict__["_status_calls"]


@pytest.mark.anyio
async def test_run_command_pushes_the_deadline_after_running(monkeypatch):
    sbx = FakeSandbox()
    sbx.run_result = _result()
    _use_sandbox(monkeypatch, sbx)

    ctx = _ctx(config={"sandbox_id": "sbx_1", "idle_timeout_s": 300})
    await _tool(e2b_env.build(ctx), "run_command")("echo hi")

    assert sbx.timeouts == [300]


@pytest.mark.anyio
async def test_run_command_clamps_timeout_seconds(monkeypatch):
    """600s is the ceiling regardless of what the model asks for."""
    sbx = FakeSandbox()
    sbx.run_result = _result()
    _use_sandbox(monkeypatch, sbx)

    tool = _tool(e2b_env.build(_ctx()), "run_command")
    await tool("echo hi", timeout_seconds=99999)

    assert sbx.calls[-1][3] == 600


@pytest.mark.anyio
async def test_run_command_treats_zero_timeout_as_unset(monkeypatch):
    """0 reads as 'no preference', not 'time out instantly'."""
    sbx = FakeSandbox()
    sbx.run_result = _result()
    _use_sandbox(monkeypatch, sbx)

    tool = _tool(e2b_env.build(_ctx()), "run_command")
    await tool("echo hi", timeout_seconds=0)

    assert sbx.calls[-1][3] == settings.environment_command_timeout_s


@pytest.mark.anyio
async def test_run_command_rejects_a_negative_timeout(monkeypatch):
    """Silently flooring to 1s would report a confusing timeout instead."""
    sbx = FakeSandbox()
    sbx.run_result = _result()
    _use_sandbox(monkeypatch, sbx)

    tool = _tool(e2b_env.build(_ctx()), "run_command")
    result = await tool("echo hi", timeout_seconds=-5)

    assert "invalid timeout_seconds" in result.lower()
    assert not any(call[0] == "run" for call in sbx.calls)


@pytest.mark.anyio
async def test_run_command_output_is_clipped(monkeypatch):
    sbx = FakeSandbox()
    huge = "x" * (settings.environment_max_output_chars + 500)
    sbx.run_result = _result(stdout=huge)
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(_ctx()), "run_command")("cat big.txt")

    assert "truncated" in result
    assert len(result) < len(huge)


# -- read_file -------------------------------------------------------------


@pytest.mark.anyio
async def test_read_file_relative_path_resolves_under_agent_dir(monkeypatch):
    sbx = FakeSandbox()
    ctx = _ctx()
    sbx.stored[f"{ctx.agent_dir}/notes.md"] = "hello"
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(ctx), "read_file")("notes.md")
    assert result == "hello"


@pytest.mark.anyio
async def test_read_file_absolute_path_passes_through(monkeypatch):
    sbx = FakeSandbox()
    sbx.stored["/etc/hostname"] = "sandbox-1"
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(_ctx()), "read_file")("/etc/hostname")
    assert result == "sandbox-1"


@pytest.mark.anyio
async def test_read_file_missing_reports_plainly(monkeypatch):
    sbx = FakeSandbox()
    sbx.raise_on_read = FileNotFoundException("nope")
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(_ctx()), "read_file")("ghost.md")
    assert "no such file" in result.lower()


@pytest.mark.anyio
async def test_read_file_rejects_a_null_byte(monkeypatch):
    sbx = FakeSandbox()
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(_ctx()), "read_file")("a\x00b")
    assert "invalid path" in result.lower()
    assert not any(call[0] == "read" for call in sbx.calls)


@pytest.mark.anyio
async def test_read_file_output_is_clipped(monkeypatch):
    sbx = FakeSandbox()
    ctx = _ctx()
    sbx.stored[f"{ctx.agent_dir}/big.txt"] = "y" * (settings.environment_max_file_chars + 500)
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(ctx), "read_file")("big.txt")
    assert "truncated" in result


# -- write_file --------------------------------------------------------------


@pytest.mark.anyio
async def test_write_file_reports_bytes_written(monkeypatch):
    sbx = FakeSandbox()
    ctx = _ctx()
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(ctx), "write_file")("out.md", "hello world")

    assert "11 bytes" in result
    assert sbx.stored[f"{ctx.agent_dir}/out.md"] == "hello world"


@pytest.mark.anyio
async def test_write_file_rejects_a_null_byte(monkeypatch):
    sbx = FakeSandbox()
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(_ctx()), "write_file")("a\x00b", "x")
    assert "invalid path" in result.lower()
    assert sbx.stored == {}


# -- list_files ----------------------------------------------------------


@pytest.mark.anyio
async def test_list_files_separates_dirs_and_files(monkeypatch):
    sbx = FakeSandbox()
    sbx.entries = [
        FakeEntry(name="app", type=FileType.DIR),
        FakeEntry(name="notes.md", type=FileType.FILE, size=42),
    ]
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(_ctx()), "list_files")()

    assert "app/" in result
    assert "notes.md" in result
    assert "42 B" in result


@pytest.mark.anyio
async def test_list_files_missing_directory_reports_plainly(monkeypatch):
    sbx = FakeSandbox()
    sbx.raise_on_list = FileNotFoundException("nope")
    _use_sandbox(monkeypatch, sbx)

    result = await _tool(e2b_env.build(_ctx()), "list_files")("ghost/")
    assert "no such directory" in result.lower()


@pytest.mark.anyio
async def test_list_files_defaults_to_the_agent_directory(monkeypatch):
    sbx = FakeSandbox()
    _use_sandbox(monkeypatch, sbx)

    ctx = _ctx()
    await _tool(e2b_env.build(ctx), "list_files")()

    assert ("list", ctx.agent_dir) in sbx.calls


# -- toolset shape ---------------------------------------------------------


def test_build_registers_exactly_the_env_tools():
    # Assembly maps tool names to owners from ENV_TOOL_NAMES; build must match it.
    names = set(e2b_env.build(_ctx()).tools.keys())
    assert names == set(ENV_TOOL_NAMES)


@pytest.mark.anyio
async def test_two_environments_do_not_share_state(monkeypatch):
    """build() is called fresh per environment node; nothing leaks across."""
    sbx_a = FakeSandbox("sbx_a")
    sbx_b = FakeSandbox("sbx_b")

    async def _connect(ctx):
        return sbx_a if ctx.node_id == _NODE else sbx_b

    monkeypatch.setattr(e2b_env, "connect", _connect)

    ctx_a = _ctx()
    ctx_b = _ctx(node_id="99999999-9999-9999-9999-999999999999")

    await _tool(e2b_env.build(ctx_a), "write_file")("a.txt", "A")
    await _tool(e2b_env.build(ctx_b), "write_file")("b.txt", "B")

    assert list(sbx_a.stored.values()) == ["A"]
    assert list(sbx_b.stored.values()) == ["B"]


@pytest.mark.anyio
async def test_run_command_floors_a_fractional_timeout(monkeypatch):
    """int() would truncate 0.5 to 0, which E2B reads as no timeout at all."""
    sbx = FakeSandbox()
    sbx.run_result = _result()
    _use_sandbox(monkeypatch, sbx)

    tool = _tool(e2b_env.build(_ctx()), "run_command")
    await tool("echo hi", timeout_seconds=0.5)

    assert sbx.calls[-1][3] == 1
