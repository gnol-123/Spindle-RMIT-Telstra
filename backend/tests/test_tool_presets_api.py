from app.main import app
from app.repositories.project_repo import AgentType
from app.repositories.tool_repo import ToolPreset
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import get_project_repository, get_tool_repository


def _override_auth():
    return AuthContext(
        user=UserResponse(id="user-1", email="u@example.com"),
        token="fake-token",  # noqa: S106
    )


def _preset():
    return ToolPreset(
        id="33333333-3333-3333-3333-333333333333",
        slug="research_method",
        name="Research Method",
        description="How to research",
        tool_type_id="tt1",
        tool_slug="skill",
        config={"text": "Do research.", "description": "Load first."},
    )


class _FakeToolRepo:
    def list_presets(self):
        return [_preset()]


class _FakeProjectRepo:
    def list_agent_types(self):
        return [
            AgentType(
                id="44444444-4444-4444-4444-444444444444",
                slug="market_research",
                name="Market Research",
                description="d",
                system_prompt="x",
                model="m",
                default_presets=["brave_search", "research_method"],
            )
        ]


def test_tool_presets_requires_auth(client):
    assert client.get("/tool-presets").status_code == 401


def test_tool_presets_lists_library(client):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_tool_repository] = lambda: _FakeToolRepo()
    try:
        response = client.get("/tool-presets")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "slug": "research_method",
            "name": "Research Method",
            "description": "How to research",
            "tool_slug": "skill",
            "config": {"text": "Do research.", "description": "Load first."},
        }
    ]


def test_agent_types_carry_default_presets(client):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: _FakeProjectRepo()
    try:
        response = client.get("/agent-types")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()[0]["default_presets"] == ["brave_search", "research_method"]
