"""Drop-agent fast path: batched background verify, pooled MCP verify, overlapped writes."""

import threading

import pytest
from pydantic_ai.mcp import MCPToolset
from test_mcp_pool import URL, Counter, CountingTransport, _server, _turn

import app.routers.projects as projects
from app.repositories.project_repo import AgentType
from app.repositories.tool_repo import ToolNode
from app.tools.base import VerifyResult
from app.tools.mcp import base


def _node(i, slug="skill", config=None):
    return ToolNode(
        id=f"t{i}", project_id="p1", name=f"T{i}", tool_type_id="tt", tool_slug=slug,
        config=config or {}, status="pending", status_detail=None,
    )  # fmt: skip


class _ToolRepo:
    def __init__(self, nodes=(), batch_fails=False):
        self.nodes = {n.id: n for n in nodes}
        self.batch_fails = batch_fails
        self.batches = []
        self.singles = []
        self.configs = {}

    def get_tool_node(self, node_id):
        return self.nodes.get(node_id)

    def secret_keys(self, node_id):
        return []

    def set_node_config(self, node_id, config):
        self.configs[node_id] = config

    def set_nodes_status(self, ids, status, detail):
        if self.batch_fails:
            raise RuntimeError("boom")
        self.batches.append((sorted(ids), status, detail))

    def set_node_status(self, node_id, status, detail):
        self.singles.append((node_id, status, detail))


class _NoReads(_ToolRepo):
    def get_tool_node(self, node_id):
        raise AssertionError("no re-read")

    def secret_keys(self, node_id):
        raise AssertionError("no secret read")


class _Spec:
    async def verify(self, ctx):
        if ctx.node_id == "t2":
            raise RuntimeError("verify blew up")
        if ctx.node_id == "t3":
            return VerifyResult(ok=False, detail="Missing key.")
        return VerifyResult(ok=True, detail="Ready.")


@pytest.fixture
def spec(monkeypatch):
    monkeypatch.setattr(projects, "get_spec", lambda slug: _Spec() if slug == "skill" else None)


async def test_defaults_skip_reads_and_batch_by_outcome(spec):
    repo = _NoReads()
    nodes = [_node(0), _node(1), _node(2), _node(3), _node(4, slug="nope")]
    await projects._verify_defaults(nodes, repo)
    assert sorted(repo.batches) == sorted(
        [
            (["t0", "t1"], "ready", "Ready."),
            (["t2"], "error", "Verification failed."),
            (["t3"], "error", "Missing key."),
            (["t4"], "error", "Unknown tool 'nope'"),
        ]
    )
    assert repo.singles == []


async def test_batch_write_failure_falls_back_per_node(spec):
    repo = _NoReads(batch_fails=True)
    await projects._verify_defaults([_node(0), _node(1)], repo)
    assert sorted(repo.singles) == [("t0", "ready", "Ready."), ("t1", "ready", "Ready.")]


@pytest.fixture
def mcp(monkeypatch):
    Counter.connects = Counter.lists = 0
    srv = _server()
    monkeypatch.setattr(base, "_transport", lambda url, headers: CountingTransport(srv))
    monkeypatch.setattr(base, "toolset", lambda url, headers: MCPToolset(CountingTransport(srv)))
    # URL is fake and won't resolve; skip the SSRF DNS check.
    monkeypatch.setattr(base, "is_public_url", lambda url: True)
    base._POOL.clear()
    yield
    base._POOL.clear()


async def test_default_mcp_verify_shares_pool_and_explicit_verify_is_fresh(mcp):
    node = _node(0, slug="mcp_server", config={"url": URL})
    repo = _ToolRepo([node])
    await projects._verify_defaults([node], repo)
    assert repo.batches == [(["t0"], "ready", "Connected. 2 tools available.")]
    assert repo.configs["t0"]["discovered_tools"] == ["boom", "echo"]

    # A later turn reuses the session verify opened.
    await _turn(base.pooled(URL, {}), "echo")
    assert Counter.connects == 1
    assert len(base._POOL) == 1

    # The explicit route still connects fresh, and nothing leaked the flag.
    assert not base.POOLED_VERIFY.get()
    await projects._verify_tool_node("t0", repo)
    assert Counter.connects == 2
    assert repo.singles == [("t0", "ready", "Connected. 2 tools available.")]
    await base.close_pool()


async def test_conversation_insert_overlaps_edge_insert(monkeypatch):
    # Both must be in flight at once, or the barrier times out.
    barrier = threading.Barrier(2, timeout=5)

    class Repo:
        def create_node(self, *a, with_conversation=True, **k):
            assert not with_conversation
            return "node-1"

        def create_conversation(self, node_id, project_id):
            barrier.wait()
            return "conv-1"

        def create_edges(self, edges):
            barrier.wait()

    class Env:
        def ensure_scratch_node(self, project_id):
            return type("N", (), {"id": "scratch"})()

    async def no_tools(*a):
        return []

    monkeypatch.setattr(projects, "_create_default_tools", no_tools)
    agent = AgentType(
        id="a1", slug="x", name="X", description=None, system_prompt="", model="m",
        default_presets=[],
    )  # fmt: skip
    node_id = await projects.provision_agent(
        "p1", agent, "X", position_x=0, position_y=0, tool_policy="ask",
        repo=Repo(), tool_repo=None, env_repo=Env(),
    )  # fmt: skip
    assert node_id == "node-1"
