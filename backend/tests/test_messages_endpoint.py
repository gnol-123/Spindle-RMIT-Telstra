"""Reading a transcript back, for clients that lost the stream."""

from app.main import app
from app.repositories.project_repo import Message, Node
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import TurnRepositories, get_turn_repositories

_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_NODE_ID = "22222222-2222-2222-2222-222222222222"
_OTHER_PROJECT_ID = "33333333-3333-3333-3333-333333333333"


def _override_auth():
    return AuthContext(
        user=UserResponse(id="user-1", email="u@example.com"),
        token="fake-token",  # noqa: S106 - test fixture, not a real credential
    )


class _Repo:
    def get_agent_node(self, node_id):
        if node_id != _NODE_ID:
            return None
        return Node(
            id=_NODE_ID,
            project_id=_PROJECT_ID,
            name="A",
            agent_type_id="at",
            system_prompt="s",
            model="m",
            tool_policy="auto",
            position_x=0,
            position_y=0,
        )

    def get_conversation_for_node(self, node_id):
        return "c1"

    def list_messages_after(self, conversation_id, after_seq=0, limit=500):
        rows = [
            Message(
                id="00000000-0000-0000-0000-000000000001",
                role="user",
                content="hi",
                seq=1,
                status="complete",
                created_at="2026-09-17T00:00:00Z",
            ),
            Message(
                id="00000000-0000-0000-0000-000000000002",
                role="assistant",
                content="yo",
                seq=2,
                status="complete",
                created_at="2026-09-17T00:00:01Z",
            ),
        ]
        return [m for m in rows if m.seq > after_seq]


class _RepoForeignNode(_Repo):
    """A node that belongs to a different project than the path says."""

    def get_agent_node(self, node_id):
        node = super().get_agent_node(node_id)
        if node is None:
            return None
        return Node(
            id=node.id,
            project_id=_OTHER_PROJECT_ID,
            name=node.name,
            agent_type_id=node.agent_type_id,
            system_prompt=node.system_prompt,
            model=node.model,
            tool_policy=node.tool_policy,
            position_x=node.position_x,
            position_y=node.position_y,
        )


def test_lists_after_seq(client):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_turn_repositories] = lambda: TurnRepositories(
        project=_Repo(), tool=None, env=None, user_id="user-1"
    )
    try:
        r = client.get(f"/projects/{_PROJECT_ID}/nodes/{_NODE_ID}/messages?after_seq=1")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert [m["seq"] for m in r.json()] == [2]


def test_node_not_found_is_404(client):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_turn_repositories] = lambda: TurnRepositories(
        project=_Repo(), tool=None, env=None, user_id="user-1"
    )
    try:
        r = client.get(f"/projects/{_PROJECT_ID}/nodes/{_OTHER_PROJECT_ID}/messages")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404


def test_node_from_another_project_is_404(client):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_turn_repositories] = lambda: TurnRepositories(
        project=_RepoForeignNode(), tool=None, env=None, user_id="user-1"
    )
    try:
        r = client.get(f"/projects/{_PROJECT_ID}/nodes/{_NODE_ID}/messages")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404
