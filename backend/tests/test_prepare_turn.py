"""prepare_turn builds one turn's instructions and toolsets; canvas nodes are partitioned out."""

import pytest

import app.services.turns as turns
from app.repositories.project_repo import Inbound, Node
from app.repositories.tool_repo import ToolNode
from app.routers.deps import TurnRepositories
from app.tools.assembly import AssembledTools


def _tool(i, slug):
    return ToolNode(
        id=f"t{i}",
        project_id="p",
        name=slug,
        tool_type_id="tt",
        tool_slug=slug,
        config={},
        status="ready",
        status_detail=None,
    )


def _node(policy="auto"):
    return Node(
        id="orch",
        project_id="p",
        name="Orchestrator",
        agent_type_id="at",
        system_prompt="s",
        model="m",
        tool_policy=policy,
        position_x=0,
        position_y=0,
    )


class _Repo:
    def __init__(self, tools):
        self.tools = {t.id: t for t in tools}

    def list_inbound_context(self, node_id):
        return []

    def list_inbound_tool_node_ids(self, node_id):
        return list(self.tools)

    def list_inbound_environment_node_ids(self, node_id):
        return []

    def get_tool_nodes(self, ids):
        return [n for n in map(self.get_tool_node, ids) if n is not None]

    def get_tool_policy(self, node_id):
        return "auto"

    def get_tool_node(self, node_id):
        return self.tools[node_id]

    def list_inbound(self, node_id):
        return Inbound([], list(self.tools.values()), [])


def _repos(tools):
    r = _Repo(tools)
    return TurnRepositories(project=r, tool=r, env=r, user_id="u")


@pytest.mark.anyio
async def test_canvas_nodes_go_to_assemble_canvas(monkeypatch):
    seen = {}

    async def fake_assemble(repo, nodes, *, policy, start=None):
        seen["assemble"] = [n.tool_slug for n in nodes]
        return AssembledTools()

    async def fake_canvas(repos, orchestrator, nodes, conversation_id, *, policy, start=None):
        seen["canvas"] = ([n.tool_slug for n in nodes], conversation_id, start)
        return AssembledTools()

    monkeypatch.setattr(turns, "assemble", fake_assemble)
    monkeypatch.setattr("app.tools.canvas.assemble_canvas", fake_canvas)

    await turns.prepare_turn(_repos([_tool(1, "canvas"), _tool(2, "skill")]), _node("ask"), "c")

    assert seen["assemble"] == ["skill"]
    assert seen["canvas"] == (["canvas"], "c", "ask")


@pytest.mark.anyio
async def test_nested_turn_marks_canvas_unavailable(monkeypatch):
    async def fake_assemble(repo, nodes, *, policy, start=None):
        return AssembledTools()

    called = []

    async def fake_canvas(*a, **k):
        called.append(1)
        return AssembledTools()

    monkeypatch.setattr(turns, "assemble", fake_assemble)
    monkeypatch.setattr("app.tools.canvas.assemble_canvas", fake_canvas)

    prepared = await turns.prepare_turn(_repos([_tool(1, "canvas")]), _node(), "c", nested=True)

    assert called == []
    assert "canvas" in prepared.tools.unavailable
    assert prepared.instructions and "unavailable" in prepared.instructions
