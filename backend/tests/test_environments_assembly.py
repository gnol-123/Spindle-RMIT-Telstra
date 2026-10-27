"""Environment nodes to toolsets, and the note that describes them.

No E2B and no database: the spec is faked at the registry boundary and the
repository holds nodes in memory.
"""

import dataclasses
from types import SimpleNamespace

import pytest
from pydantic_ai import ApprovalRequired
from pydantic_ai.toolsets import FunctionToolset, PrefixedToolset

from app.environments import assembly as env_assembly
from app.environments.assembly import (
    ENV_TOOL_NAMES,
    assemble_environments,
    env_prefix,
    environment_note,
    merge_assembled,
)
from app.environments.base import EnvSpec
from app.repositories.environment_repo import EnvNode
from app.tools.assembly import AssembledTools, LivePolicyToolset
from app.tools.base import VerifyResult

_AGENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_ENV = "11111111-2222-3333-4444-555555555555"
_PROJECT = "99999999-9999-9999-9999-999999999999"


def _auto(_node_id):
    return "auto"


def _ask(_node_id):
    return "ask"


def _node(**over) -> EnvNode:
    base = {
        "id": _ENV,
        "project_id": _PROJECT,
        "name": "Coding Environment",
        "config": {"runtime": "e2b", "role": "user", "sandbox_id": "sbx_1"},
        "status": "ready",
        "status_detail": None,
        "tool_policy": "ask",
        "position_x": 0.0,
        "position_y": 0.0,
    }
    base.update(over)
    return EnvNode(**base)


class _FakeEnvRepo:
    def __init__(self, node: EnvNode | None = None):
        self.node = node
        self.status_writes: list[tuple] = []

    def get_environment_nodes(self, ids):
        return [n for n in map(self.get_environment_node, ids) if n is not None]

    def get_environment_node(self, node_id: str):
        return self.node

    def set_status(self, node_id: str, status: str, detail: str | None) -> None:
        self.status_writes.append((node_id, status, detail))


def _install_spec(monkeypatch, *, build_error: Exception | None = None):
    """A spec whose build returns a real FunctionToolset with the four names."""

    def _build(ctx):
        if build_error is not None:
            raise build_error
        ts = FunctionToolset()
        for name in ENV_TOOL_NAMES:

            async def _tool(_name=name) -> str:
                return _name

            ts.add_function(_tool, name=name, description=name)
        return ts

    async def _provision(ctx):
        return "sbx_new"

    async def _verify(ctx):
        return VerifyResult(ok=True, detail="Sandbox running")

    async def _teardown(sandbox_id):
        return None

    spec = EnvSpec(
        runtime="e2b",
        provision=_provision,
        build=_build,
        verify=_verify,
        teardown=_teardown,
    )
    monkeypatch.setattr(
        env_assembly, "get_spec", lambda runtime: spec if runtime == "e2b" else None
    )
    return spec


# -- env_prefix --------------------------------------------------------------


def test_env_prefix_sanitises_and_suffixes():
    assert env_prefix("Coding Environment", _ENV) == f"coding_environment_{_ENV[:8]}"


def test_env_prefix_handles_punctuation_and_case():
    assert env_prefix("My-Env!! (v2)", _ENV) == f"my_env_v2_{_ENV[:8]}"


def test_env_prefix_falls_back_when_the_name_has_no_usable_characters():
    assert env_prefix("!!!", _ENV) == f"env_{_ENV[:8]}"


def test_env_prefix_stays_under_the_function_name_cap():
    """Gemini caps function names at 64 chars, prefix plus the longest tool."""
    prefix = env_prefix("x" * 200, _ENV)
    longest = max(len(f"{prefix}_{name}") for name in ENV_TOOL_NAMES)
    assert longest <= 64


# -- assemble_environments ---------------------------------------------------


@pytest.mark.anyio
async def test_assemble_builds_a_prefixed_toolset(monkeypatch):
    _install_spec(monkeypatch)
    node = _node(tool_policy="auto")
    repo = _FakeEnvRepo(node)

    result = await assemble_environments(repo, [node], agent_node_id=_AGENT, policy_of=_auto)

    assert len(result.toolsets) == 1
    assert isinstance(result.toolsets[0].wrapped, PrefixedToolset)
    assert result.owner_by_toolset == [_ENV]
    assert result.unavailable == []


@pytest.mark.anyio
async def test_assemble_registers_full_tool_names_for_the_approval_backfill(monkeypatch):
    """_record_pending_calls looks up the prefixed name pydantic-ai reports."""
    _install_spec(monkeypatch)
    node = _node(tool_policy="auto")
    repo = _FakeEnvRepo(node)

    result = await assemble_environments(repo, [node], agent_node_id=_AGENT, policy_of=_auto)

    prefix = env_prefix(node.name, node.id)
    assert result.owner_by_tool[prefix] == _ENV
    for name in ENV_TOOL_NAMES:
        assert result.owner_by_tool[f"{prefix}_{name}"] == _ENV


@pytest.mark.anyio
async def test_assemble_gates_an_ask_environment_for_approval(monkeypatch):
    _install_spec(monkeypatch)
    node = _node(tool_policy="ask")
    repo = _FakeEnvRepo(node)

    result = await assemble_environments(repo, [node], agent_node_id=_AGENT, policy_of=_ask)

    assert isinstance(result.toolsets[0], LivePolicyToolset)
    assert await result.toolsets[0]._asks() is True


@pytest.mark.anyio
async def test_assemble_does_not_gate_an_auto_environment(monkeypatch):
    """The environment's own policy governs, read per call."""
    _install_spec(monkeypatch)
    node = _node(tool_policy="auto")
    repo = _FakeEnvRepo(node)

    result = await assemble_environments(repo, [node], agent_node_id=_AGENT, policy_of=_auto)

    assert await result.toolsets[0]._asks() is False


@pytest.mark.anyio
async def test_assemble_provisions_a_pending_node(monkeypatch):
    """First use of a scratch space pays for the sandbox inline."""
    _install_spec(monkeypatch)
    pending = _node(status="pending", config={"runtime": "e2b", "role": "scratch"})
    ready = _node(
        status="ready",
        config={"runtime": "e2b", "role": "scratch", "sandbox_id": "sbx_new"},
    )
    repo = _FakeEnvRepo(pending)

    async def _ensure(env_repo, node, *, force=False):
        return ready

    monkeypatch.setattr(env_assembly, "ensure_provisioned", _ensure)

    result = await assemble_environments(repo, [pending], agent_node_id=_AGENT, policy_of=_auto)

    assert len(result.toolsets) == 1
    assert result.unavailable == []


@pytest.mark.anyio
async def test_assemble_reports_a_node_that_failed_to_provision(monkeypatch):
    _install_spec(monkeypatch)
    pending = _node(status="pending", config={"runtime": "e2b", "role": "scratch"})
    failed = _node(
        status="error",
        status_detail="RuntimeError: no key",
        config={"runtime": "e2b", "role": "scratch"},
    )
    repo = _FakeEnvRepo(pending)

    async def _ensure(env_repo, node, *, force=False):
        return failed

    monkeypatch.setattr(env_assembly, "ensure_provisioned", _ensure)

    result = await assemble_environments(repo, [pending], agent_node_id=_AGENT, policy_of=_auto)

    assert result.toolsets == []
    assert result.unavailable == ["Coding Environment"]


@pytest.mark.anyio
async def test_assemble_reports_a_stopped_node_as_unavailable(monkeypatch):
    """A turn must not restart it, so the agent is told it cannot be used."""
    _install_spec(monkeypatch)
    node = _node(status="stopped", config={"runtime": "e2b", "role": "user"})
    repo = _FakeEnvRepo(node)

    result = await assemble_environments(repo, [node], agent_node_id=_AGENT, policy_of=_auto)

    assert result.toolsets == []
    assert result.unavailable == ["Coding Environment"]


@pytest.mark.anyio
async def test_assemble_reports_a_provisioning_node_as_unavailable(monkeypatch):
    _install_spec(monkeypatch)
    node = _node(status="provisioning", config={"runtime": "e2b", "role": "user"})
    repo = _FakeEnvRepo(node)

    result = await assemble_environments(repo, [node], agent_node_id=_AGENT, policy_of=_auto)

    assert result.unavailable == ["Coding Environment"]


@pytest.mark.anyio
async def test_assemble_includes_an_errored_node_that_still_has_a_sandbox(monkeypatch):
    """The tools self-heal on a successful connect, so give the agent the chance."""
    _install_spec(monkeypatch)
    node = _node(status="error", config={"runtime": "e2b", "role": "user", "sandbox_id": "sbx_1"})
    repo = _FakeEnvRepo(node)

    result = await assemble_environments(repo, [node], agent_node_id=_AGENT, policy_of=_auto)

    assert len(result.toolsets) == 1
    assert result.unavailable == []


@pytest.mark.anyio
async def test_assemble_reports_an_unknown_runtime(monkeypatch):
    _install_spec(monkeypatch)
    node = _node(config={"runtime": "local", "role": "user", "sandbox_id": "sbx_1"})
    repo = _FakeEnvRepo(node)

    result = await assemble_environments(repo, [node], agent_node_id=_AGENT, policy_of=_auto)

    assert result.toolsets == []
    assert result.unavailable == ["Coding Environment"]


@pytest.mark.anyio
async def test_assemble_survives_a_build_failure(monkeypatch):
    """build is documented as never raising, but a bug there must not kill the turn."""
    _install_spec(monkeypatch, build_error=RuntimeError("boom"))
    node = _node()
    repo = _FakeEnvRepo(node)

    result = await assemble_environments(repo, [node], agent_node_id=_AGENT, policy_of=_auto)

    assert result.toolsets == []
    assert result.unavailable == ["Coding Environment"]


@pytest.mark.anyio
async def test_assemble_two_environments_get_distinct_prefixes(monkeypatch):
    _install_spec(monkeypatch)
    scratch = _node(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        name="Scratch Space",
        tool_policy="auto",
        config={"runtime": "e2b", "role": "scratch", "sandbox_id": "sbx_a"},
    )
    coding = _node(tool_policy="auto")
    repo = _FakeEnvRepo(scratch)

    result = await assemble_environments(
        repo, [scratch, coding], agent_node_id=_AGENT, policy_of=_auto
    )

    assert len(result.toolsets) == 2
    assert result.owner_by_toolset == [scratch.id, coding.id]
    prefixes = {env_prefix(scratch.name, scratch.id), env_prefix(coding.name, coding.id)}
    assert len(prefixes) == 2


@pytest.mark.anyio
async def test_assemble_passes_the_agent_id_into_the_context(monkeypatch):
    """Each agent works in its own directory inside the shared sandbox."""
    seen: dict = {}

    def _build(ctx):
        seen["agent_node_id"] = ctx.agent_node_id
        seen["agent_dir"] = ctx.agent_dir
        return FunctionToolset()

    async def _noop(*_a, **_k):
        return None

    spec = EnvSpec(runtime="e2b", provision=_noop, build=_build, verify=_noop, teardown=_noop)
    monkeypatch.setattr(env_assembly, "get_spec", lambda runtime: spec)

    node = _node(tool_policy="auto")
    await assemble_environments(_FakeEnvRepo(node), [node], agent_node_id=_AGENT, policy_of=_auto)

    assert seen["agent_node_id"] == _AGENT
    assert seen["agent_dir"].endswith(_AGENT)


@pytest.mark.anyio
async def test_assemble_injects_a_status_writer(monkeypatch):
    """A tool marks the node errored without holding a repository."""
    seen: dict = {}

    def _build(ctx):
        seen["set_status"] = ctx.set_status
        return FunctionToolset()

    async def _noop(*_a, **_k):
        return None

    spec = EnvSpec(runtime="e2b", provision=_noop, build=_build, verify=_noop, teardown=_noop)
    monkeypatch.setattr(env_assembly, "get_spec", lambda runtime: spec)

    node = _node(tool_policy="auto")
    repo = _FakeEnvRepo(node)
    await assemble_environments(repo, [node], agent_node_id=_AGENT, policy_of=_auto)

    await seen["set_status"]("error", "gone")
    assert repo.status_writes == [(_ENV, "error", "gone")]


@pytest.mark.anyio
async def test_assemble_with_no_nodes_returns_empty(monkeypatch):
    _install_spec(monkeypatch)
    result = await assemble_environments(_FakeEnvRepo(), [], agent_node_id=_AGENT, policy_of=_auto)

    assert result.toolsets == []
    assert result.notes == []


# -- merge_assembled ---------------------------------------------------------


def test_merge_keeps_toolsets_and_owners_parallel():
    """record_calls zips them with strict=True, so a mismatch breaks every turn."""
    a = AssembledTools(
        toolsets=["t1"],
        owner_by_tool={"a": "1"},
        unavailable=["A"],
        owner_by_toolset=["1"],
        notes=["note a"],
    )
    b = AssembledTools(
        toolsets=["t2", "t3"],
        owner_by_tool={"b": "2"},
        unavailable=["B"],
        owner_by_toolset=["2", "3"],
        notes=["note b"],
    )

    merged = merge_assembled(a, b)

    assert merged.toolsets == ["t1", "t2", "t3"]
    assert merged.owner_by_toolset == ["1", "2", "3"]
    assert len(merged.toolsets) == len(merged.owner_by_toolset)
    assert merged.owner_by_tool == {"a": "1", "b": "2"}
    assert merged.unavailable == ["A", "B"]
    assert merged.notes == ["note a", "note b"]


def test_merge_with_empty_sides():
    a = AssembledTools()
    b = AssembledTools(toolsets=["t"], owner_by_toolset=["1"])

    assert merge_assembled(a, b).toolsets == ["t"]
    assert merge_assembled(b, a).toolsets == ["t"]


# -- environment_note --------------------------------------------------------


def test_environment_note_is_none_without_environments():
    assert environment_note([], _AGENT) is None


def test_environment_note_names_each_prefix_and_purpose():
    scratch = _node(name="Scratch Space", config={"runtime": "e2b", "role": "scratch"})
    coding = _node(name="Coding Environment", config={"runtime": "e2b", "role": "user"})

    note = environment_note(
        [(scratch, "scratch_space_11111111"), (coding, "coding_environment_11111111")],
        _AGENT,
    )

    assert note is not None
    assert "scratch_space_11111111" in note
    assert "coding_environment_11111111" in note
    assert "scratch space" in note.lower()
    assert _AGENT in note


def test_environment_note_uses_a_configured_description():
    node = _node(config={"runtime": "e2b", "role": "user", "description": "the API repo"})
    note = environment_note([(node, "p")], _AGENT)
    assert "the API repo" in note


class _Ran:
    async def call_tool(self, name, tool_args, ctx, tool):
        return "ran"


@pytest.mark.anyio
async def test_each_environment_is_gated_on_its_own_live_policy(monkeypatch):
    """Read per call from the environment's own row: a flip mid-run counts both ways."""
    _install_spec(monkeypatch)
    ask = _node(tool_policy="ask")
    auto = _node(id="22222222-3333-4444-5555-666666666666", name="Other", tool_policy="auto")
    live = {ask.id: "ask", auto.id: "auto"}
    reads = []

    def policy_of(node_id):
        reads.append(node_id)
        return live[node_id]

    result = await assemble_environments(
        _FakeEnvRepo(ask), [ask, auto], agent_node_id=_AGENT, policy_of=policy_of
    )
    # Starting policy does not decide the wrapper: both are gated live.
    assert all(isinstance(t, LivePolicyToolset) for t in result.toolsets)
    gates = dict(zip(result.owner_by_toolset, result.toolsets, strict=True))

    async def call(node_id):
        gate = dataclasses.replace(gates[node_id], wrapped=_Ran())
        try:
            return await gate.call_tool("x", {}, SimpleNamespace(tool_call_approved=False), None)
        except ApprovalRequired:
            return "paused"

    assert await call(ask.id) == "paused"
    assert await call(auto.id) == "ran"
    live[ask.id], live[auto.id] = "auto", "ask"
    assert await call(ask.id) == "ran"
    assert await call(auto.id) == "paused"
    assert reads == [ask.id, auto.id, ask.id, auto.id]
