"""provision_agent is the agent branch of POST /nodes, shared with the canvas tool."""

import pytest

import app.routers.projects as projects
from app.repositories.project_repo import AgentType


class _Repo:
    def __init__(self):
        self.created = None
        self.edges = []

    def create_node(
        self, project_id, agent_type_id, name, *, position_x, position_y, tool_policy, **_
    ):
        self.created = dict(
            project_id=project_id,
            agent_type_id=agent_type_id,
            name=name,
            position_x=position_x,
            position_y=position_y,
            tool_policy=tool_policy,
        )
        return "node-1"

    def create_edges(self, edges):
        self.edges.extend(edges)

    def create_conversation(self, node_id, project_id):
        return "conv-1"


class _EnvRepo:
    def ensure_scratch_node(self, project_id):
        return type("N", (), {"id": "scratch"})()


@pytest.mark.anyio
async def test_provision_agent_creates_wires_and_returns_id(monkeypatch):
    wired = []

    async def fake_tools(project_id, agent_type, req, tool_repo):
        wired.append((str(project_id), req.position_x, req.position_y))
        return [type("T", (), {"id": "tool-1"})()]

    monkeypatch.setattr(projects, "_create_default_tools", fake_tools)
    monkeypatch.setattr(projects, "_verify_in_background", lambda ids, repo: None)
    repo, env = _Repo(), _EnvRepo()
    agent_type = AgentType(
        id="at1",
        slug="coding",
        name="Coding",
        description="d",
        system_prompt="x",
        model="m",
        default_presets=[],
    )

    node_id = await projects.provision_agent(
        "p1",
        agent_type,
        "Coding",
        position_x=10,
        position_y=20,
        tool_policy="auto",
        repo=repo,
        tool_repo=None,
        env_repo=env,
    )

    assert node_id == "node-1"
    assert repo.created["tool_policy"] == "auto"
    assert repo.created["position_x"] == 10
    assert repo.edges == [("scratch", "node-1", "environment"), ("tool-1", "node-1", "tool")]
    assert wired == [("p1", 10, 20)]
