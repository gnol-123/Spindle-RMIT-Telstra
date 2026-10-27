"""Environment edges, and the hooks that create a scratch space.

Exercises the real routes with fake repositories: no database, no network.
"""

from app.main import app
from app.repositories.environment_repo import EnvNode
from app.repositories.project_repo import Edge, Node, Project
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import (
    get_environment_repository,
    get_project_repository,
    get_tool_repository,
)

_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_AGENT_ID = "22222222-2222-2222-2222-222222222222"
_ENV_ID = "33333333-3333-3333-3333-333333333333"
_TOOL_ID = "44444444-4444-4444-4444-444444444444"
_USER_ID = "55555555-5555-5555-5555-555555555555"


def _override_auth():
    return AuthContext(user=UserResponse(id=_USER_ID, email="test@example.com"), token="test-token")


def _agent_node(node_id: str) -> Node:
    return Node(
        id=node_id,
        project_id=_PROJECT_ID,
        name="Researcher",
        agent_type_id="66666666-6666-6666-6666-666666666666",
        system_prompt="You research.",
        model="gemini-3-flash-preview",
        tool_policy="ask",
        position_x=0.0,
        position_y=0.0,
        kind="agent",
        agent_slug="market_research",
    )


def _env_node(node_id: str = _ENV_ID, role: str = "scratch") -> EnvNode:
    return EnvNode(
        id=node_id,
        project_id=_PROJECT_ID,
        name="Scratch Space" if role == "scratch" else "Coding Environment",
        config={"runtime": "e2b", "role": role, "sandbox_id": None},
        status="pending",
        status_detail=None,
        tool_policy="auto" if role == "scratch" else "ask",
        position_x=0.0,
        position_y=0.0,
    )


class _FakeChatRepo:
    """Chat repo stand-in. Records the edges it is asked to create."""

    def __init__(self, agent_ids: set[str] | None = None):
        self._agent_ids = agent_ids or set()
        self.created_edges: list[tuple[str, str, str]] = []
        self.created_projects: list[str] = []

    def get_project(self, project_id):
        return Project(id=project_id, name="Test Project")

    def get_agent_node(self, node_id):
        return _agent_node(node_id) if node_id in self._agent_ids else None

    def get_agent_type(self, slug):
        from app.repositories.project_repo import AgentType

        return AgentType(
            id="66666666-6666-6666-6666-666666666666",
            slug=slug,
            name="Market Research",
            description="d",
            system_prompt="You research.",
            model="gemini-3-flash-preview",
        )

    def create_project(self, name, description=None):
        self.created_projects.append(name)
        return Project(id=_PROJECT_ID, name=name)

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
        self._agent_ids.add(_AGENT_ID)
        return _AGENT_ID

    def create_edge(self, source_node_id, target_node_id, kind="context"):
        self.created_edges.append((source_node_id, target_node_id, kind))
        return Edge(
            id="77777777-7777-7777-7777-777777777777",
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


class _FakeToolRepo:
    def __init__(self, tool_ids: set[str] | None = None):
        self._tool_ids = tool_ids or set()

    def get_tool_nodes(self, ids):
        return [n for n in map(self.get_tool_node, ids) if n is not None]

    def get_tool_node(self, node_id):
        from app.repositories.tool_repo import ToolNode

        if node_id not in self._tool_ids:
            return None
        return ToolNode(
            id=node_id,
            project_id=_PROJECT_ID,
            name="Brave",
            tool_type_id="88888888-8888-8888-8888-888888888888",
            tool_slug="brave_search",
            config={},
            status="ready",
            status_detail=None,
        )


class _FakeEnvRepo:
    """Environment repo stand-in. Records whether a scratch was ensured."""

    def __init__(self, env_ids: set[str] | None = None, scratch: EnvNode | None = None):
        self._env_ids = env_ids or set()
        self._scratch = scratch
        self.ensure_calls: list[str] = []

    def get_environment_nodes(self, ids):
        return [n for n in map(self.get_environment_node, ids) if n is not None]

    def get_environment_node(self, node_id):
        return _env_node(node_id) if node_id in self._env_ids else None

    def ensure_scratch_node(self, project_id, new_project=False):
        self.ensure_calls.append(project_id)
        if self._scratch is None:
            self._scratch = _env_node()
        return self._scratch


def _kinds(chat, tool, env, ids):
    """node_kinds over the per-kind fakes."""
    out = {}
    for i in ids:
        for kind, n in (
            ("agent", chat.get_agent_node(i)),
            ("tool", tool.get_tool_node(i)),
            ("environment", env.get_environment_node(i)),
        ):
            if n is not None:
                out[i] = (n.project_id, kind)
                break
    return out


def _use(chat_repo, tool_repo=None, env_repo=None):
    tool_repo, env_repo = tool_repo or _FakeToolRepo(), env_repo or _FakeEnvRepo()
    chat_repo.node_kinds = lambda ids: _kinds(chat_repo, tool_repo, env_repo, ids)
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: chat_repo
    app.dependency_overrides[get_tool_repository] = lambda: tool_repo
    app.dependency_overrides[get_environment_repository] = lambda: env_repo


# -- edge kind validation ----------------------------------------------------


def test_environment_edge_environment_to_agent_is_created(client):
    chat = _FakeChatRepo(agent_ids={_AGENT_ID})
    env = _FakeEnvRepo(env_ids={_ENV_ID})
    _use(chat, env_repo=env)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/edges",
            json={
                "source_node_id": _ENV_ID,
                "target_node_id": _AGENT_ID,
                "kind": "environment",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["kind"] == "environment"
    assert (_ENV_ID, _AGENT_ID, "environment") in chat.created_edges


def test_environment_edge_reversed_is_422(client):
    """agent to environment is the wrong direction and must be refused."""
    chat = _FakeChatRepo(agent_ids={_AGENT_ID})
    env = _FakeEnvRepo(env_ids={_ENV_ID})
    _use(chat, env_repo=env)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/edges",
            json={
                "source_node_id": _AGENT_ID,
                "target_node_id": _ENV_ID,
                "kind": "environment",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "environment to agent" in detail
    assert "agent to environment" in detail


def test_environment_edge_between_two_environments_is_422(client):
    chat = _FakeChatRepo()
    env = _FakeEnvRepo(env_ids={_ENV_ID, "99999999-9999-9999-9999-999999999999"})
    _use(chat, env_repo=env)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/edges",
            json={
                "source_node_id": _ENV_ID,
                "target_node_id": "99999999-9999-9999-9999-999999999999",
                "kind": "environment",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_tool_edge_from_environment_source_is_422(client):
    """An environment is not a tool: kind='tool' must not accept one."""
    chat = _FakeChatRepo(agent_ids={_AGENT_ID})
    env = _FakeEnvRepo(env_ids={_ENV_ID})
    _use(chat, env_repo=env)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/edges",
            json={
                "source_node_id": _ENV_ID,
                "target_node_id": _AGENT_ID,
                "kind": "tool",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "tool to agent" in response.json()["detail"]
    assert "environment to agent" in response.json()["detail"]


def test_unknown_edge_kind_is_422(client):
    """The Literal on the request model rejects anything outside the three kinds."""
    _use(_FakeChatRepo())
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/edges",
            json={
                "source_node_id": _ENV_ID,
                "target_node_id": _AGENT_ID,
                "kind": "wormhole",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


# -- scratch hooks -----------------------------------------------------------


def test_create_project_ensures_a_scratch_node(client):
    chat = _FakeChatRepo()
    env = _FakeEnvRepo()
    _use(chat, env_repo=env)
    try:
        response = client.post("/projects", json={"name": "New Project"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert env.ensure_calls == [_PROJECT_ID]


def test_create_agent_node_wires_an_edge_to_the_scratch(client):
    chat = _FakeChatRepo()
    env = _FakeEnvRepo()
    _use(chat, env_repo=env)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "agent", "agent_slug": "market_research"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert env.ensure_calls == [_PROJECT_ID]
    assert (_ENV_ID, _AGENT_ID, "environment") in chat.created_edges


def test_create_agent_node_survives_a_duplicate_scratch_edge(client):
    """A retried create must not 500 because the edge is already there."""
    from app.repositories.project_repo import DuplicateEdge

    chat = _FakeChatRepo()

    def _raise(*_a, **_k):
        raise DuplicateEdge("already linked")

    chat.create_edge = _raise
    env = _FakeEnvRepo()
    _use(chat, env_repo=env)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "agent", "agent_slug": "market_research"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201


def test_create_tool_node_does_not_wire_a_scratch_edge(client):
    """Only agents get a scratch edge. A tool node has nothing to execute."""
    from app.repositories.tool_repo import ToolNode, ToolType

    class _ToolRepoForCreate(_FakeToolRepo):
        def get_tool_type(self, slug):
            return ToolType(
                id="88888888-8888-8888-8888-888888888888",
                slug="skill",
                name="Skill",
                description=None,
                config_schema={"fields": [{"key": "text", "label": "Text", "type": "text"}]},
                secret_fields=[],
            )

        def create_tool_node(self, project_id, tool_type_id, name, config, **_k):
            return _TOOL_ID

        def get_tool_nodes(self, ids):
            return [n for n in map(self.get_tool_node, ids) if n is not None]

        def get_tool_node(self, node_id):
            return ToolNode(
                id=_TOOL_ID,
                project_id=_PROJECT_ID,
                name="Skill",
                tool_type_id="88888888-8888-8888-8888-888888888888",
                tool_slug="skill",
                config={"text": "hi"},
                status="ready",
                status_detail=None,
            )

        def set_secret(self, *_a, **_k):
            return None

        def secret_keys(self, *_a, **_k):
            return []

        def set_node_status(self, *_a, **_k):
            return None

        def set_node_config(self, *_a, **_k):
            return None

    chat = _FakeChatRepo()
    env = _FakeEnvRepo()
    _use(chat, tool_repo=_ToolRepoForCreate(), env_repo=env)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "tool", "tool_slug": "skill", "config": {"text": "hi"}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert env.ensure_calls == []
    assert chat.created_edges == []
