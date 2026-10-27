from app.main import app
from app.repositories.project_repo import Edge, Node, Project
from app.repositories.tool_repo import ToolNode, ToolPreset, ToolType
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import (
    get_environment_repository,
    get_project_repository,
    get_tool_repository,
)
from app.tools.base import ToolContext, ToolSpec, VerifyResult

_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_NODE_ID = "22222222-2222-2222-2222-222222222222"


def test_tool_types_requires_auth(client):
    assert client.get("/tool-types").status_code == 401


def test_verify_requires_auth(client):
    response = client.post(
        "/projects/11111111-1111-1111-1111-111111111111"
        "/nodes/22222222-2222-2222-2222-222222222222/verify"
    )
    assert response.status_code == 401


def test_tool_calls_requires_auth(client):
    response = client.get(
        "/projects/11111111-1111-1111-1111-111111111111"
        "/nodes/22222222-2222-2222-2222-222222222222/tool-calls"
    )
    assert response.status_code == 401


# -- secret leak guard -------------------------------------------------------
#
# A tool node response must expose only secret KEY NAMES, never the value.
# Exercises the real create-node and verify routes end to end with fake
# repositories, so no real network call and no real database is touched.


class _FakeToolRepo:
    """In-memory stand-in for ToolRepository. Mirrors its public surface."""

    def __init__(self):
        self._tool_type = ToolType(
            id="33333333-3333-3333-3333-333333333333",
            slug="mcp_server",
            name="MCP Server",
            description="test",
            config_schema={
                "fields": [
                    {"key": "url", "label": "Server URL", "type": "text", "required": True},
                    {
                        "key": "auth_token",
                        "label": "Auth token",
                        "type": "password",
                        "required": False,
                    },
                ]
            },
            secret_fields=["auth_token"],
        )
        self._config: dict = {}
        self._status = "pending"
        self._status_detail = None
        self._secrets: dict[str, str] = {}

    def get_tool_type(self, slug):
        return self._tool_type if slug == self._tool_type.slug else None

    def get_preset(self, slug):
        if slug != "research_method":
            return None
        return ToolPreset(
            id="88888888-8888-8888-8888-888888888888",
            slug="research_method",
            name="Research Method",
            description="How to research",
            tool_type_id=self._tool_type.id,
            tool_slug=self._tool_type.slug,
            config={"text": "Do research.", "description": "Load first."},
        )

    def list_presets(self):
        preset = self.get_preset("research_method")
        return [preset] if preset else []

    def list_tool_types(self):
        return [self._tool_type]

    def create_tool_node(
        self, project_id, tool_type_id, name, config, *, position_x=0, position_y=0
    ):
        self._config = dict(config)
        return _NODE_ID

    def get_tool_nodes(self, ids):
        return [n for n in map(self.get_tool_node, ids) if n is not None]

    def get_tool_node(self, node_id):
        if node_id != _NODE_ID:
            return None
        return ToolNode(
            id=_NODE_ID,
            project_id=_PROJECT_ID,
            name="GitHub",
            tool_type_id=self._tool_type.id,
            tool_slug=self._tool_type.slug,
            config=self._config,
            status=self._status,
            status_detail=self._status_detail,
        )

    def set_node_config(self, node_id, config):
        self._config = dict(config)

    def set_node_status(self, node_id, status, detail):
        self._status = status
        self._status_detail = detail

    def set_secret(self, node_id, key, value):
        # Real backend stores this only in the vault. Confirm nothing else
        # in this fake needs to remember the plaintext to serve the API.
        self._secrets[key] = value

    def secret_keys(self, node_id):
        return sorted(self._secrets)

    def list_calls(self, tool_node_id, limit=50):
        return []


class _FakeChatRepo:
    def get_project(self, project_id):
        return Project(id=project_id, name="Test project")


def _override_auth():
    return AuthContext(
        user=UserResponse(id="user-1", email="u@example.com"),
        token="fake-token",  # noqa: S106 - test fixture, not a real credential
    )


def test_tool_node_response_never_contains_secret_value(client, monkeypatch):
    secret_value = "ghp_super_secret_value"  # noqa: S105 - test fixture, not a real credential
    fake_repo = _FakeToolRepo()

    async def fake_verify(ctx: ToolContext) -> VerifyResult:
        # Confirm the plaintext did reach verify (it must, to connect) while
        # asserting the HTTP response never carries it.
        assert ctx.secrets.get("auth_token") == secret_value
        return VerifyResult(ok=True, detail="Connected.", discovered_tools=["list_issues"])

    fake_spec = ToolSpec(kind="mcp", build=lambda ctx: None, verify=fake_verify)
    monkeypatch.setattr("app.routers.projects.get_spec", lambda slug: fake_spec)
    monkeypatch.setattr(
        "app.routers.projects.load_node_secrets",
        lambda node_id, keys: {"auth_token": secret_value} if "auth_token" in keys else {},
    )

    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_tool_repository] = lambda: fake_repo
    app.dependency_overrides[get_project_repository] = lambda: _FakeChatRepo()
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepoForEdges()
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={
                "kind": "tool",
                "tool_slug": "mcp_server",
                "name": "GitHub",
                "config": {"url": "https://example.invalid/mcp", "auth_token": secret_value},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()

    assert body["status"] == "ready"
    assert body["secrets_set"] == ["auth_token"]
    assert body["config"].get("url") == "https://example.invalid/mcp"
    assert "auth_token" not in body["config"]


def test_platform_provided_lists_keys_the_user_has_not_set(client, monkeypatch):
    fake_repo = _FakeToolRepo()
    fake_repo._tool_type = ToolType(
        id="33333333-3333-3333-3333-333333333333",
        slug="brave_search",
        name="Brave Search",
        description="test",
        config_schema={"fields": [{"key": "api_key", "label": "API key", "type": "password"}]},
        secret_fields=["api_key"],
    )

    async def fake_verify(ctx: ToolContext) -> VerifyResult:
        assert ctx.secrets.get("api_key") == "platform-key"
        return VerifyResult(ok=True, detail="Connected.")

    monkeypatch.setattr(
        "app.routers.projects.get_spec",
        lambda slug: ToolSpec(kind="api", build=lambda ctx: None, verify=fake_verify),
    )
    monkeypatch.setattr("app.routers.projects.load_node_secrets", lambda node_id, keys: {})
    monkeypatch.setattr(
        "app.routers.projects.platform_secrets", lambda slug: {"api_key": "platform-key"}
    )

    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_tool_repository] = lambda: fake_repo
    app.dependency_overrides[get_project_repository] = lambda: _FakeChatRepo()
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepoForEdges()
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "tool", "tool_slug": "brave_search", "name": "Brave"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    assert body["secrets_set"] == []
    assert body["platform_provided"] == ["api_key"]
    assert "platform-key" not in response.text


# -- delete works for any node kind ------------------------------------------
#
# Regression: DELETE /projects/{id}/nodes/{node_id} called repo.delete_agent_node,
# which filters kind='agent'. A tool node could never be removed through the API.


class _FakeChatRepoWithDelete(_FakeChatRepo):
    def __init__(self, *, node_exists: bool):
        self._node_exists = node_exists
        self.deleted_node_id: str | None = None

    def delete_node(self, node_id: str) -> list[str]:
        self.deleted_node_id = node_id
        return [node_id] if self._node_exists else []

    def get_conversation_for_node(self, node_id: str) -> str | None:
        return None


def test_delete_node_removes_a_tool_node(client):
    fake_repo = _FakeChatRepoWithDelete(node_exists=True)
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: fake_repo
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepoForEdges()
    try:
        response = client.delete(f"/projects/{_PROJECT_ID}/nodes/{_NODE_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["deleted_node_ids"] == [_NODE_ID]
    assert fake_repo.deleted_node_id == _NODE_ID


def test_delete_node_missing_reports_node_not_found(client):
    """The 404 detail must not say 'Agent not found' for what may be a tool node."""
    fake_repo = _FakeChatRepoWithDelete(node_exists=False)
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: fake_repo
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepoForEdges()
    try:
        response = client.delete(f"/projects/{_PROJECT_ID}/nodes/{_NODE_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Node not found"


# -- edge kind validation -----------------------------------------------------
#
# EdgeCreateRequest.kind was widened from Literal["context"] to also accept
# "tool". Each edge kind must connect a specific pair of box kinds: context
# runs agent to agent, tool runs tool to agent. The router checks this before
# calling repo.create_edge, in addition to the database trigger.

_AGENT_ID = "44444444-4444-4444-4444-444444444444"
_AGENT_ID_2 = "55555555-5555-5555-5555-555555555555"
_TOOL_ID = "66666666-6666-6666-6666-666666666666"


def _agent_node(node_id: str) -> Node:
    return Node(
        id=node_id,
        project_id=_PROJECT_ID,
        name="Agent",
        agent_type_id="agent-type-1",
        system_prompt="",
        model="test-model",
        tool_policy="auto",
        position_x=0,
        position_y=0,
    )


def _tool_node(node_id: str) -> ToolNode:
    return ToolNode(
        id=node_id,
        project_id=_PROJECT_ID,
        name="Tool",
        tool_type_id="tool-type-1",
        tool_slug="skill",
        config={},
        status="ready",
        status_detail=None,
    )


class _FakeChatRepoForEdges:
    """Chat repo stand-in that knows a fixed set of agent nodes and edges."""

    def __init__(self, agent_ids: set[str]):
        self._agent_ids = agent_ids
        self.created: tuple[str, str, str] | None = None

    def get_project(self, project_id):
        return Project(id=project_id, name="Test project")

    def get_agent_node(self, node_id):
        return _agent_node(node_id) if node_id in self._agent_ids else None

    def create_edge(self, source_node_id, target_node_id, kind="context"):
        self.created = (source_node_id, target_node_id, kind)
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


class _FakeToolRepoForEdges:
    """Tool repo stand-in that knows a fixed set of tool nodes."""

    def __init__(self, tool_ids: set[str]):
        self._tool_ids = tool_ids

    def get_tool_nodes(self, ids):
        return [n for n in map(self.get_tool_node, ids) if n is not None]

    def get_tool_node(self, node_id):
        return _tool_node(node_id) if node_id in self._tool_ids else None


class _FakeEnvRepoForEdges:
    """No environments in these cases: every lookup misses."""

    def get_environment_nodes(self, ids):
        return [n for n in map(self.get_environment_node, ids) if n is not None]

    def get_environment_node(self, node_id):
        return None


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


def _post_edge(client, source_node_id, target_node_id, kind, *, agent_ids, tool_ids):
    chat, tool, env = (
        _FakeChatRepoForEdges(agent_ids),
        _FakeToolRepoForEdges(tool_ids),
        _FakeEnvRepoForEdges(),
    )
    chat.node_kinds = lambda ids: _kinds(chat, tool, env, ids)
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: chat
    app.dependency_overrides[get_tool_repository] = lambda: tool
    app.dependency_overrides[get_environment_repository] = lambda: env
    try:
        return client.post(
            f"/projects/{_PROJECT_ID}/edges",
            json={
                "source_node_id": source_node_id,
                "target_node_id": target_node_id,
                "kind": kind,
            },
        )
    finally:
        app.dependency_overrides.clear()


def test_tool_edge_agent_to_agent_is_422(client):
    """kind='tool' requires a tool source, not two agents."""
    response = _post_edge(
        client,
        _AGENT_ID,
        _AGENT_ID_2,
        "tool",
        agent_ids={_AGENT_ID, _AGENT_ID_2},
        tool_ids=set(),
    )
    assert response.status_code == 422
    assert "tool to agent" in response.json()["detail"]
    assert "agent to agent" in response.json()["detail"]


def test_tool_edge_reversed_endpoints_is_422(client):
    """kind='tool' with source and target swapped (agent to tool) is rejected."""
    response = _post_edge(
        client,
        _AGENT_ID,
        _TOOL_ID,
        "tool",
        agent_ids={_AGENT_ID},
        tool_ids={_TOOL_ID},
    )
    assert response.status_code == 422
    assert "tool to agent" in response.json()["detail"]
    assert "agent to tool" in response.json()["detail"]


def test_context_edge_from_tool_node_is_422(client):
    """kind='context' requires both endpoints to be agents, not a tool source."""
    response = _post_edge(
        client,
        _TOOL_ID,
        _AGENT_ID,
        "context",
        agent_ids={_AGENT_ID},
        tool_ids={_TOOL_ID},
    )
    assert response.status_code == 422
    assert "agent to agent" in response.json()["detail"]
    assert "tool to agent" in response.json()["detail"]


def test_tool_edge_tool_to_agent_succeeds(client):
    """The one valid tool-edge shape: source is a tool node, target is an agent."""
    response = _post_edge(
        client,
        _TOOL_ID,
        _AGENT_ID,
        "tool",
        agent_ids={_AGENT_ID},
        tool_ids={_TOOL_ID},
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "tool"


def test_context_edge_agent_to_agent_still_succeeds(client):
    """Existing context-edge behaviour is unchanged by the widened kind."""
    response = _post_edge(
        client,
        _AGENT_ID,
        _AGENT_ID_2,
        "context",
        agent_ids={_AGENT_ID, _AGENT_ID_2},
        tool_ids=set(),
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "context"


# -- presets -----------------------------------------------------------------


def _skill_type():
    return ToolType(
        id="33333333-3333-3333-3333-333333333333",
        slug="skill",
        name="Skill",
        description="test",
        config_schema={
            "fields": [
                {"key": "text", "label": "Instructions", "type": "textarea", "required": True},
                {"key": "description", "label": "When", "type": "text", "required": False},
            ]
        },
        secret_fields=[],
    )


def _ok_spec():
    async def verify(ctx):
        return VerifyResult(ok=True, detail="Ready.")

    return ToolSpec(kind="skill", build=lambda ctx: None, verify=verify)


def test_create_tool_node_from_preset_copies_config(client, monkeypatch):
    fake_repo = _FakeToolRepo()
    fake_repo._tool_type = _skill_type()
    monkeypatch.setattr("app.routers.projects.get_spec", lambda slug: _ok_spec())
    monkeypatch.setattr("app.routers.projects.load_node_secrets", lambda node_id, keys: {})

    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_tool_repository] = lambda: fake_repo
    app.dependency_overrides[get_project_repository] = lambda: _FakeChatRepo()
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepoForEdges()
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "tool", "preset_slug": "research_method"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["tool_slug"] == "skill"
    assert body["status"] == "ready"
    assert body["config"] == {"text": "Do research.", "description": "Load first."}


def test_create_tool_node_request_config_overrides_preset(client, monkeypatch):
    fake_repo = _FakeToolRepo()
    fake_repo._tool_type = _skill_type()
    monkeypatch.setattr("app.routers.projects.get_spec", lambda slug: _ok_spec())
    monkeypatch.setattr("app.routers.projects.load_node_secrets", lambda node_id, keys: {})

    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_tool_repository] = lambda: fake_repo
    app.dependency_overrides[get_project_repository] = lambda: _FakeChatRepo()
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepoForEdges()
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={
                "kind": "tool",
                "preset_slug": "research_method",
                "config": {"description": "Custom when"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["config"] == {"text": "Do research.", "description": "Custom when"}


def test_create_tool_node_unknown_preset_is_404(client):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_tool_repository] = lambda: _FakeToolRepo()
    app.dependency_overrides[get_project_repository] = lambda: _FakeChatRepo()
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepoForEdges()
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "tool", "preset_slug": "nope"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_create_tool_node_needs_tool_slug_or_preset_slug(client):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_tool_repository] = lambda: _FakeToolRepo()
    app.dependency_overrides[get_project_repository] = lambda: _FakeChatRepo()
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepoForEdges()
    try:
        response = client.post(f"/projects/{_PROJECT_ID}/nodes", json={"kind": "tool"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_create_tool_node_rejects_both_slugs(client):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_tool_repository] = lambda: _FakeToolRepo()
    app.dependency_overrides[get_project_repository] = lambda: _FakeChatRepo()
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepoForEdges()
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "tool", "tool_slug": "skill", "preset_slug": "research_method"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
    assert "not both" in response.json()["detail"]
