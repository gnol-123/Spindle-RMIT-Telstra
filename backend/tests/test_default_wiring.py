import logging
import time

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.project_repo import AgentType, DuplicateEdge, Edge, Node, Project
from app.repositories.tool_repo import ToolNode, ToolPreset, ToolType
from app.routers import projects
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import (
    get_environment_repository,
    get_project_repository,
    get_tool_repository,
)
from app.tools.base import ToolSpec, VerifyResult

_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_AGENT_ID = "22222222-2222-2222-2222-222222222222"
_SCRATCH_ID = "99999999-9999-9999-9999-999999999999"

_SKILL_TYPE = ToolType(
    id="33333333-3333-3333-3333-333333333333",
    slug="skill",
    name="Skill",
    description=None,
    config_schema={"fields": [{"key": "text"}, {"key": "description"}]},
    secret_fields=[],
)
_BRAVE_TYPE = ToolType(
    id="55555555-5555-5555-5555-555555555555",
    slug="brave_search",
    name="Brave Search",
    description=None,
    config_schema={"fields": [{"key": "api_key", "type": "password"}]},
    secret_fields=["api_key"],
)

_PRESETS = {
    "research_method": ToolPreset(
        id="p1",
        slug="research_method",
        name="Research Method",
        description=None,
        tool_type_id=_SKILL_TYPE.id,
        tool_slug="skill",
        config={"text": "Do research.", "description": "Load first."},
    ),
    "brave_search": ToolPreset(
        id="p2",
        slug="brave_search",
        name="Brave Search",
        description=None,
        tool_type_id=_BRAVE_TYPE.id,
        tool_slug="brave_search",
        config={},
    ),
}


def _override_auth():
    return AuthContext(
        user=UserResponse(id="user-1", email="u@example.com"),
        token="fake-token",  # noqa: S106
    )


class _FakeProjectRepo:
    def __init__(self, default_presets):
        self._agent_type = AgentType(
            id="44444444-4444-4444-4444-444444444444",
            slug="market_research",
            name="Market Research",
            description="d",
            system_prompt="x",
            model="m",
            default_presets=default_presets,
        )
        self.edges: list[tuple[str, str, str]] = []

    def get_project(self, project_id):
        return Project(id=project_id, name="P")

    def get_agent_type(self, slug):
        return self._agent_type if slug == self._agent_type.slug else None

    def create_node(
        self,
        project_id,
        agent_type_id,
        name,
        *,
        position_x=0,
        position_y=0,
        tool_policy="ask",
        with_conversation=True,
    ):
        return _AGENT_ID

    def create_edge(self, source_node_id, target_node_id, kind="context"):
        key = (source_node_id, target_node_id, kind)
        if key in self.edges:
            raise DuplicateEdge("dup")
        self.edges.append(key)
        return Edge(
            id="e",
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            kind=kind,
            summary=None,
            summarised_through_seq=None,
            summary_updated_at=None,
            summary_max_words=200,
        )

    def create_conversation(self, node_id, project_id):
        return "conv-1"

    def create_edges(self, edges):
        return [self.create_edge(*e) for e in edges]

    def get_agent_node(self, node_id):
        return Node(
            id=_AGENT_ID,
            project_id=_PROJECT_ID,
            name="Market Research",
            agent_type_id=self._agent_type.id,
            system_prompt="x",
            model="m",
            tool_policy="ask",
            position_x=100,
            position_y=200,
        )


class _FakeToolRepo:
    def __init__(self):
        self.created: list[dict] = []
        self._status: dict[str, tuple[str, str | None]] = {}

    def get_preset(self, slug):
        return _PRESETS.get(slug)

    def get_tool_type(self, slug):
        return {"skill": _SKILL_TYPE, "brave_search": _BRAVE_TYPE}.get(slug)

    def list_presets(self):
        return list(_PRESETS.values())

    def list_tool_types(self):
        return [_SKILL_TYPE, _BRAVE_TYPE]

    def create_tool_node(
        self, project_id, tool_type_id, name, config, *, position_x=0, position_y=0
    ):
        node_id = f"tool-{len(self.created)}"
        self.created.append(
            {
                "id": node_id,
                "tool_type_id": tool_type_id,
                "name": name,
                "config": config,
                "position_x": position_x,
                "position_y": position_y,
            }
        )
        return node_id

    def create_tool_nodes(self, project_id, rows):
        return [
            self.create_tool_node(
                project_id,
                r["tool_type_id"],
                r["name"],
                r["config"],
                position_x=r["position_x"],
                position_y=r["position_y"],
            )
            for r in rows
        ]

    def get_tool_nodes(self, ids):
        return [n for n in map(self.get_tool_node, ids) if n is not None]

    def get_tool_node(self, node_id):
        for row in self.created:
            if row["id"] == node_id:
                slug = "skill" if row["tool_type_id"] == _SKILL_TYPE.id else "brave_search"
                status, detail = self._status.get(node_id, ("pending", None))
                return ToolNode(
                    id=node_id,
                    project_id=_PROJECT_ID,
                    name=row["name"],
                    tool_type_id=row["tool_type_id"],
                    tool_slug=slug,
                    config=row["config"],
                    status=status,
                    status_detail=detail,
                )
        return None

    def set_node_config(self, node_id, config):
        pass

    def set_node_status(self, node_id, status, detail):
        self._status[node_id] = (status, detail)

    def set_nodes_status(self, node_ids, status, detail):
        for i in node_ids:
            self._status[i] = (status, detail)

    def set_secret(self, node_id, key, value):
        raise AssertionError("defaults never write secrets")

    def secret_keys(self, node_id):
        return []


class _Scratch:
    id = _SCRATCH_ID


class _FakeEnvRepo:
    def ensure_scratch_node(self, project_id, new_project=False):
        return _Scratch()


def _spec_for(slug):
    async def verify(ctx):
        if slug == "brave_search" and not ctx.secrets.get("api_key"):
            return VerifyResult(ok=False, detail="Missing API key.")
        return VerifyResult(ok=True, detail="Ready.")

    return ToolSpec(
        kind="api" if slug == "brave_search" else "skill",
        build=lambda ctx: None,
        verify=verify,
    )


def _create_agent(client, monkeypatch, default_presets, *, platform=None):
    project_repo = _FakeProjectRepo(default_presets)
    tool_repo = _FakeToolRepo()
    monkeypatch.setattr("app.routers.projects.get_spec", _spec_for)
    monkeypatch.setattr("app.routers.projects.load_node_secrets", lambda node_id, keys: {})
    monkeypatch.setattr("app.routers.projects.platform_secrets", lambda slug: dict(platform or {}))

    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: project_repo
    app.dependency_overrides[get_tool_repository] = lambda: tool_repo
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepo()
    try:
        # Persistent loop so the post-response verify gets to run.
        with TestClient(app) as live:
            response = live.post(
                f"/projects/{_PROJECT_ID}/nodes",
                json={
                    "kind": "agent",
                    "agent_slug": "market_research",
                    "position_x": 100,
                    "position_y": 200,
                },
            )
            # Verify runs after the response; wait for it to land.
            deadline = time.monotonic() + 10
            while projects._background and time.monotonic() < deadline:
                time.sleep(0.01)
    finally:
        app.dependency_overrides.clear()
    return response, project_repo, tool_repo


def test_agent_with_no_defaults_creates_only_scratch_edge(client, monkeypatch):
    response, project_repo, tool_repo = _create_agent(client, monkeypatch, [])
    assert response.status_code == 201
    assert tool_repo.created == []
    assert project_repo.edges == [(_SCRATCH_ID, _AGENT_ID, "environment")]


def test_defaults_create_tool_nodes_and_edges(client, monkeypatch):
    response, project_repo, tool_repo = _create_agent(
        client,
        monkeypatch,
        ["brave_search", "research_method"],
        platform={"api_key": "platform-key"},
    )
    assert response.status_code == 201
    assert response.json()["id"] == _AGENT_ID

    # Presets wire concurrently, so creation order isn't fixed.
    by_name = {c["name"]: c for c in tool_repo.created}
    assert sorted(by_name) == ["Brave Search", "Research Method"]
    assert by_name["Research Method"]["config"] == {
        "text": "Do research.",
        "description": "Load first.",
    }
    assert tool_repo._status["tool-0"] == ("ready", "Ready.")
    assert tool_repo._status["tool-1"] == ("ready", "Ready.")

    assert sorted(project_repo.edges) == sorted(
        [
            (_SCRATCH_ID, _AGENT_ID, "environment"),
            ("tool-0", _AGENT_ID, "tool"),
            ("tool-1", _AGENT_ID, "tool"),
        ]
    )


def test_defaults_are_placed_beside_the_agent(client, monkeypatch):
    _, _, tool_repo = _create_agent(client, monkeypatch, ["brave_search", "research_method"])
    assert tool_repo.created[0]["position_x"] == 100 - 260
    assert tool_repo.created[0]["position_y"] == 200
    assert tool_repo.created[1]["position_y"] == 200 + 90


def test_brave_without_platform_key_is_error_but_still_wired(client, monkeypatch):
    response, project_repo, tool_repo = _create_agent(client, monkeypatch, ["brave_search"])
    assert response.status_code == 201
    assert tool_repo._status["tool-0"] == ("error", "Missing API key.")
    assert ("tool-0", _AGENT_ID, "tool") in project_repo.edges


def test_unknown_preset_is_skipped_and_logged(client, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="app.routers.projects"):
        response, project_repo, tool_repo = _create_agent(
            client, monkeypatch, ["does_not_exist", "research_method"]
        )
    assert response.status_code == 201
    assert [c["name"] for c in tool_repo.created] == ["Research Method"]
    assert "does_not_exist" in caplog.text
    assert "market_research" in caplog.text


def test_preset_whose_type_is_missing_is_skipped(client, monkeypatch):
    broken = ToolPreset(
        id="p3",
        slug="ghost",
        name="Ghost",
        description=None,
        tool_type_id="nope",
        tool_slug="not_a_type",
        config={},
    )
    monkeypatch.setitem(_PRESETS, "ghost", broken)
    response, _, tool_repo = _create_agent(client, monkeypatch, ["ghost", "research_method"])
    assert response.status_code == 201
    assert [c["name"] for c in tool_repo.created] == ["Research Method"]


def test_skipped_preset_does_not_leave_a_gap(client, monkeypatch):
    _, _, tool_repo = _create_agent(
        client, monkeypatch, ["does_not_exist", "brave_search", "research_method"]
    )
    assert [c["position_y"] for c in tool_repo.created] == [200, 200 + 90]
